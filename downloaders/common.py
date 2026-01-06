from io import TextIOWrapper
from typing import Protocol, Self
from dataclasses import dataclass, field
from pathlib import Path

from pathvalidate import sanitize_filename
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

__all__ = (
    "DownloaderException",
    "DownloaderError",
    "AuthenticationException",
    "DownloadNotFoundException",
    "DownloadManager",
    "VideoDownloader",
    "is_video_file",
    "url_to_path",
)

class DownloaderException(Exception):
    """Base exception for downloader exceptions."""
    pass

class DownloaderError(DownloaderException):
    """Exception raised for general download errors."""
    pass

class AuthenticationException(DownloaderException):
    """Exception raised for authentication failures."""
    pass

class DownloadNotFoundException(DownloaderException):
    """Exception raised when a download is not found."""
    pass


class TimeoutHTTPAdapter(HTTPAdapter):
    """HTTPAdapter with default timeout support."""

    def __init__(self, timeout: int = 30, *args, **kwargs):
        self.timeout = timeout
        super().__init__(*args, **kwargs)

    def send(self, request, **kwargs):
        kwargs.setdefault('timeout', self.timeout)
        return super().send(request, **kwargs)

@dataclass
class DownloadManager:
    output: Path = Path("output")
    min_size: int = 0
    max_size: int | None = None
    chunk_size: int = 8192
    timeout: int = 30
    retries: int = 3
    backoff_factor: float = 0.5
    status_forcelist: tuple[int, ...] = (500, 502, 503, 504)
    cache_links_path: Path | None = Path(".link_cache.txt")
    _cache_link_file: TextIOWrapper | None = field(init=False, default=None)
    session: requests.Session | None = field(init=False, default=None)

    def __enter__(self) -> Self:
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        retry = Retry(
            total=self.retries,
            backoff_factor=self.backoff_factor,
            status_forcelist=self.status_forcelist,
        )
        adapter = TimeoutHTTPAdapter(timeout=self.timeout, max_retries=retry)
        self.session.mount("https://", adapter)
        # noinspection HttpUrlsUsage
        self.session.mount("http://", adapter)

        if self.cache_links_path:
            self.cache_links_path.parent.mkdir(parents=True, exist_ok=True)
            self._cache_link_file = open(self.cache_links_path, "a+", encoding="utf-8")

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            self.session.close()
            self.session = None
        if self._cache_link_file:
            self._cache_link_file.close()
            self._cache_link_file = None
        return False

    def cache_link(self, url: str) -> None:
        if self._cache_link_file:
            self._cache_link_file.write(url + "\n")
            self._cache_link_file.flush()

    def is_link_cached(self, url: str) -> bool:
        if self._cache_link_file:
            self._cache_link_file.seek(0)
            return url in (line.strip() for line in self._cache_link_file)
        return False


class VideoDownloader(Protocol):
    """Protocol for video downloader functions."""
    def __call__(self, url: str, manager: DownloadManager, log_prefix: str = "") -> bool:
        ...


ext_map = {
    'video/webm': 'webm',
    'video/x-matroska': 'mkv',
    'video/x-flv': 'flv',
    'video/dvd': 'vob',
    'video/ogg': 'ogv',
    'application/ogg': 'ogg',
    'video/x-mng': 'mng',
    'video/quicktime': 'mov',
    'video/x-msvideo': 'avi',
    'video/x-qt': 'qt',
    'video/x-ms-wmv': 'wmv',
    'video/x-yuv': 'yuv',
    'application/vnd.rn-realmedia': 'rm',
    'video/x-ms-asf': 'asf',
    'video/x-amv': 'amv',
    'video/mp4': 'mp4',
    'video/mpeg': 'mpg',
    'video/3gpp': '3gp',
    'video/3gpp2': '3g2',
    'application/mxf': 'mxf',
    'video/roq': 'roq',
    'application/x-nsv': 'nsv',
    'video/x-f4v': 'f4v',
    'video/x-f4p': 'f4p',
    'audio/x-f4a': 'f4a',
    'video/x-f4b': 'f4b',
    'video/mod': 'mod',
    'video/x-gifv': 'gifv',
    'video/x-m4v': 'm4v',
    'video/mp2t': 'm4p',
    'video/mp2p': 'mp2',
    'video/mpv': 'mpv',
    'video/mpe': 'mpe',
    'video/x-svi': 'svi',
    'video/x-roq': 'roq',
    'video/x-rrc': 'rrc',
}

def is_video_file(filename: str = '', content_type: str = '') -> bool:
    """
    Check if the file is a video based on its filename or content type.

    :param filename: The name of the file.
    :param content_type: The content type of the file.
    :return: True if the file is a video, False otherwise.
    """

    if not filename and not content_type:
        raise DownloaderError("Either filename or content_type must be provided.")

    video_extensions = set(ext_map.values())
    if content_type:
        if content_type in ext_map:
            return True
    if filename:
        file_ext = filename.split('.')[-1].lower()
        if file_ext in video_extensions:
            return True
    return False

def url_to_path(url: str, output_dir: Path | str, to_add: str = '', extension: str = '', content_type: str = '') -> Path:
    """
    Convert a URL to a sanitized file path.
    :param url: The URL to convert.
    :param output_dir: The directory where the file will be saved.
    :param to_add: Optional string to add to the filename.
    :param extension: Optional file extension to use.
    :param content_type: Optional content type to determine the file extension.
    :return: A Path object representing the sanitized filename.
    """
    max_filename_length = 255

    if isinstance(output_dir, str):
        output_dir = Path(output_dir)
    url_cleaned = url.split('#')[0].split('?')[0]

    file_ext = url_cleaned.split('.')[-1] if '.' in url_cleaned else ''
    if file_ext and len(file_ext) > 5:
        file_ext = ''
    url_cleaned = url_cleaned[:-len(file_ext)-1] if file_ext else url_cleaned
    if extension:
        file_ext = extension.lstrip('.')
    if not file_ext and content_type:
        file_ext = ext_map.get(content_type, content_type.split('/')[-1])
    if file_ext:
        file_ext = '.' + file_ext

    # noinspection HttpUrlsUsage
    filename = sanitize_filename(
        url_cleaned
        .replace("https://", "")
        .replace("http://", "")
        .replace('www.', '')
        .replace("/", "_")
        .replace('.', '-')
        + to_add)
    if len(filename) + len(file_ext) > max_filename_length:
        filename = filename[:max_filename_length - len(file_ext)]
    return output_dir / f"{filename}{file_ext}"
