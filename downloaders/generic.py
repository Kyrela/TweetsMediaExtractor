import logging

import requests
from tqdm import tqdm

from downloaders.common import *

__all__ = ("generic_video_downloader",)

logger = logging.getLogger("TweetsMediaExtractor.Generic")

def generic_video_downloader(
        url: str,
        dl_manager: DownloadManager,
        log_prefix: str = "",
        headers: dict | None = None,
) -> bool:
    """
    Download video from the given URL.
    :param url: URL of the video to download.
    :param dl_manager: DownloadManager instance with configuration and session.
    :param headers: Dictionary of cookies to include in the request headers.
    :param log_prefix: Prefix for log messages to indicate nesting level.
    :return bool: True if download was successful, False otherwise.
    """

    if dl_manager.is_link_cached(url):
        logger.info(f"{log_prefix}{url}: Ignoring download, link found in cache")
        return False

    try:
        r = dl_manager.session.head(url, allow_redirects=True, headers=headers or {})
        r.raise_for_status()

        content_type = r.headers.get("Content-Type", "").split(';')[0]
        if not is_video_file(content_type=content_type):
            logger.info(f"{log_prefix}{url}: Ignoring download, unexpected content type {content_type}")
            dl_manager.cache_link(url)
            return False


        filepath = url_to_path(url, dl_manager.output, content_type=content_type)
        total_size = int(r.headers.get("Content-Length", 0))
        if (dl_manager.max_size is not None and total_size > dl_manager.max_size) or total_size < dl_manager.min_size:
            logger.info(f"{log_prefix}{url}: Ignoring download, file size ({total_size} bytes) is outside allowed range [{dl_manager.min_size}, {dl_manager.max_size if dl_manager.max_size is not None else '∞'}]")
            dl_manager.cache_link(url)
            return False
        existing_size = 0
        if filepath.exists() and (existing_size := filepath.stat().st_size) == total_size:
            logger.info(f"{log_prefix}{url}: Ignoring download, file already exists: {filepath}")
            dl_manager.cache_link(url)
            return False

        logger.debug(f"{log_prefix}{url}: Downloading video to {filepath}")

        base_headers = {
            "Range": f"bytes={existing_size}-"
        }
        base_headers.update(headers or {})

        mode = "ab" if existing_size > 0 else "wb"
        with dl_manager.session.get(url, headers=base_headers, stream=True) as r:
            r.raise_for_status()
            with open(filepath, mode) as f, tqdm(
                    total=total_size,
                    initial=existing_size,
                    unit='B',
                    unit_scale=True,
                    desc=filepath.name,
                    leave=False
            ) as pbar:
                for chunk in r.iter_content(chunk_size=dl_manager.chunk_size):
                    if chunk:
                        f.write(chunk)
                        pbar.update(len(chunk))

        logger.info(f"{log_prefix}\x1b[32mDownloaded: {filepath}\x1b[0m")
        dl_manager.cache_link(url)
        return True
    except requests.RequestException as e:
        if isinstance(e, requests.HTTPError) and e.response is not None:
            match e.response.status_code:
                case 403:
                    logger.info(f"{log_prefix}{url}: Skipping download, access forbidden")
                    dl_manager.cache_link(url)
                    return False
                case 404:
                    logger.info(f"{log_prefix}{url}: Skipping download, file not found")
                    dl_manager.cache_link(url)
                    return False
                case 429:
                    logger.warning(f"{log_prefix}{url}: Skipping download, too many requests")
                    return False
                case 400:
                    logger.info(f"{log_prefix}{url}: Skipping download, bad request")
                    dl_manager.cache_link(url)
                    return False
        raise DownloaderError(f"{log_prefix}{url}: Failed to download") from e
