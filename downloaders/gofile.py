"""
This file contains modified code from the following repository:

gofile-dl
https://github.com/rkwyu/gofile-dl

Used here under the MIT License (MIT)

MIT License

Copyright (c) 2024-2025 ray.yukawai

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import logging

import requests

from downloaders.common import *
from downloaders.generic import generic_video_downloader

__all__ = ("gofile_video_downloader", "GoFileProtectedException", "GoFileTokenError")

logger = logging.getLogger("TweetsMediaExtractor.GoFile")

BASE_API_URL = "https://api.gofile.io"
CONFIG_JS_URL = "https://gofile.io/dist/js/config.js"
GOFILE_URL_PREFIX = "https://gofile.io/d/"


class GoFileTokenError(AuthenticationException, DownloaderError):
    """Raised when token cannot be obtained."""
    pass

class GoFileProtectedException(AuthenticationException):
    """Raised when access is restricted (private or protected with password)."""
    pass


def get_token(session: requests.Session) -> str:
    """
    Get account token from GoFile API and store it in the session.

    :param session: requests.Session object for making HTTP requests.
    :return: Account token as a string.
    """
    if not hasattr(session, 'gofile_token') or not session.gofile_token:
        data = session.post(f"{BASE_API_URL}/accounts").json()
        if data["status"] == "ok":
            session.gofile_token = data["data"]["token"]
            logger.debug(f"updated token: {session.gofile_token}")
        else:
            raise GoFileTokenError("cannot get token")
    return session.gofile_token

def get_wt(session: requests.Session) -> str:
    """
    Get website token (wt) from GoFile config.js and store it in the session.

    :param session: requests.Session object for making HTTP requests.
    :return: Website token (wt) as a string.
    """
    if not hasattr(session, 'gofile_wt') or not session.gofile_wt:
        alljs = session.get(CONFIG_JS_URL).text
        if 'appdata.wt = "' in alljs:
            # noinspection PyUnresolvedReferences
            session.gofile_wt = alljs.split('appdata.wt = "')[1].split('"')[0]
            logger.debug(f"updated wt: {session.gofile_wt}")
        else:
            raise GoFileTokenError("cannot get wt")
    return session.gofile_wt


def get_files(
        session: requests.Session,
        url: str | None = None,
        content_id: str | None = None,
        log_prefix: str = "",
) -> list[str]:
    """
    Get files from GoFile URL or content ID.

    :param session: requests.Session object for making HTTP requests.
    :param url: GoFile URL.
    :param content_id: GoFile content ID.
    :param log_prefix: Prefix for log messages to indicate nesting level.
    :return: Dictionary of download links and their corresponding file paths.
    """
    if content_id is None and url is not None:
        if not url.startswith(GOFILE_URL_PREFIX):
            raise DownloaderException(f"Invalid URL: {url}")
        content_id = url.split("/")[-1]

    token = get_token(session)
    wt = get_wt(session)

    data = session.get(
        f"{BASE_API_URL}/contents/{content_id}?cache=true",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Website-Token": wt,
        },
    ).json()

    if data["status"] == "error-notFound":
        raise DownloadNotFoundException(f"content not found for url {url}")
    if data["status"] != "ok":
        raise DownloaderError(f"failed to get content info: {data['status']} - {data.get('message', '')}")
    if data["data"].get("passwordStatus", "passwordOk") != "passwordOk":
        raise GoFileProtectedException(f"invalid password for url {url}: {data['data'].get('passwordStatus')}")
    if data["data"].get("canAccess", True) is False:
        raise GoFileProtectedException(f"content not accessible for url {url}")

    files = []
    if data["data"]["type"] == "folder":
        for child_id, child in data["data"]["children"].items():
            if child["type"] == "folder":
                files.extend(get_files(session, content_id=child_id, url=url))
            elif is_video_file(child["name"]):
                files.append(child["link"])
            else:
                logger.debug(f"{log_prefix}GoFile {url} | Ignoring non-video file: {child['name']}")
    elif is_video_file(data["data"]["name"]):
        files.append(data["data"]["link"])
    else:
        logger.debug(f"{log_prefix}GoFile {url} | Ignoring non-video file: {data['data']['name']}")

    return files


def gofile_video_downloader(
        url: str,
        dl_manager: DownloadManager,
        log_prefix: str = "",
) -> bool:
    """
    Download video from GoFile URL.
    :param url: GoFile URL.
    :param dl_manager: DownloadManager instance. Contains download configuration and session.
    :param log_prefix: Prefix for log messages to indicate nesting level.
    :return: bool: True if download was successful, False otherwise.
    """
    if dl_manager.is_link_cached(url):
        logger.info(f"{log_prefix}{url}: Ignoring download, link found in cache")
        return False
    try:
        logger.debug(f"{log_prefix}{url}: Fetching file list from GoFile")
        files = get_files(dl_manager.session, url, log_prefix=log_prefix)
        logger.debug(f"{log_prefix}{url}: Found {len(files)} video files to download")
        results = []
        for link in files:
            results.append(generic_video_downloader(
                link, dl_manager, f"{log_prefix}GoFile {url} | ",
                headers={"Cookie": f"accountToken={get_token(dl_manager.session)}"},
            ))
        dl_manager.cache_link(url)
        if any(results):
            logger.info(f"{log_prefix}\x1b[32mGoFile folder downloaded: {url}\x1b[0m")
        else:
            logger.info(f"{log_prefix}{url}: No video files were downloaded in the GoFile folder")
        return True
    except GoFileProtectedException:
        logger.info(f"{log_prefix}{url}: Skipping download, content is private or password-protected")
        dl_manager.cache_link(url)
    except DownloadNotFoundException:
        logger.info(f"{log_prefix}{url}: Skipping download, content not found")
        dl_manager.cache_link(url)
    return False
