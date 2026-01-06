import json
from pathlib import Path
import re
import logging
from urllib.parse import urlparse
from datetime import datetime
import time

from yaml import safe_load, YAMLError
# noinspection PyPackageRequirements
from twitter_openapi_python import TwitterOpenapiPython, TwitterOpenapiPythonClient
# noinspection PyPackageRequirements
from twitter_openapi_python_generated.models.tweet import Tweet

from downloaders.common import DownloadManager, VideoDownloader, DownloaderException, DownloaderError
from downloaders.generic import generic_video_downloader
from downloaders.gofile import gofile_video_downloader

logging.basicConfig(level=logging.INFO, format='%(asctime)s   [%(levelname)-8s • %(name)30s]   %(message)s')

logger = logging.getLogger("TweetsMediaExtractor")

website_downloaders: dict[str, VideoDownloader] = {
    "gofile.io": gofile_video_downloader
}


def load_config(file_path: str | Path) -> dict:
    """
    Load configuration from a YAML file.
    :param file_path: Path to the YAML configuration file.
    :return: Configuration dictionary.
    """
    file_path = Path(file_path)
    logger.debug(f"Loading configuration from '{file_path}'")
    if not file_path.exists():
        raise FileNotFoundError(f"Configuration file '{file_path}' not found, please create it.")
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            config_data = safe_load(file)
            logger.debug(f"Configuration loaded: {list(config_data.keys())}")
            return config_data
    except YAMLError as e:
        raise ValueError(f"Error parsing configuration file '{file_path}': {e}") from e

def tweet_scanner(tweet: Tweet, log_prefix="") -> list[str]:
    """
    Scan a tweet for matches based on the configuration.
    :param tweet: Tweet object.
    :param log_prefix: Prefix for log messages to indicate nesting level.
    :return: List of matched strings based on the configuration.
    """
    matches = []
    tweet_text = tweet.legacy.full_text
    logger.debug(f"{log_prefix}Scanning tweet ID {tweet.rest_id}: {tweet_text[:100]!r}...")
    log_prefix += f"[Tweet ID {tweet.rest_id}] "
    real_urls = {url.url: url.expanded_url for url in tweet.legacy.entities.urls}
    logger.debug(f"{log_prefix}Found {len(real_urls)} URLs to expand")
    for t_co_url, real_url in real_urls.items():
        logger.debug(f"{log_prefix}Expanding URL: {t_co_url} -> {real_url}")
        tweet_text = tweet_text.replace(t_co_url, real_url)
    for regex, repl in config['external_links'].items():
        for match in re.finditer(regex, tweet_text):
            matched_str = match.group(0)
            if repl:
                matched_str = re.sub(regex, repl, matched_str)
            logger.debug(f"{log_prefix}Regex '{regex}' matched: {matched_str}")
            matches.append(matched_str)
    return matches

def search_timeline(client: TwitterOpenapiPythonClient, dl_manager: DownloadManager, search_config: dict, cursor: str | None = None) -> tuple[list, str, int | None]:
    """
    Search the Twitter timeline based on the provided configuration.
    :param client: Twitter API client.
    :param dl_manager: DownloadManager instance.
    :param search_config: Search configuration dictionary.
    :param cursor: Cursor for pagination.
    :return: Tuple of list of tweets and next cursor.
    """
    last_exception = None
    for retry in range(dl_manager.retries):
        try:
            extra_params = {}
            if 'count' in search_config:
                extra_params['max_results'] = search_config['count']
            res = client.get_tweet_api().get_search_timeline(**search_config, cursor=cursor, extra_param=extra_params)
            res_data = res.data
            headers = res.header
            reset_time = headers.rate_limit_reset + 1 if headers.rate_limit_remaining <= 1 else None
            return res_data.data, res_data.cursor.bottom.value, reset_time
        except Exception as e:
            logger.error(f"Error fetching search timeline, try {retry + 1} of {dl_manager.retries}", exc_info=e)
            last_exception = e
            sleep_duration = dl_manager.backoff_factor * (2 ** retry)
            logger.debug(f"Sleeping for {sleep_duration} seconds before retrying...")
            time.sleep(sleep_duration)
    raise DownloaderError("Max retries exceeded while fetching search timeline") from last_exception


def tweet_fetch_loop(client: TwitterOpenapiPythonClient) -> None:
    """
    Fetch tweets in a loop based on the configuration.
    :param client: Twitter API client.
    :return: None
    """
    cursor = None
    dl_config = config.get('downloads', {})
    for key in ("output", "cache_links_path"):
        if key in dl_config:
            dl_config[key] = Path(dl_config[key])

    max_searches = config.get('max_search_pages', None)
    logger.debug(f"Starting fetch loop with max_searches={max_searches if max_searches is not None else '∞'}")
    with DownloadManager(**dl_config) as dl_manager:
        logger.debug(f"Download config: output={dl_manager.output}")
        dl_manager.output.mkdir(parents=True, exist_ok=True)
        reset_time = 0
        i = 0
        while max_searches is None or i < max_searches:
            prefix = f"[{i + 1}/{max_searches if max_searches is not None else '∞'}] "
            if reset_time:
                wait_seconds = max(0, reset_time - int(time.time()))
                reset_datetime = datetime.fromtimestamp(reset_time).strftime('%Y-%m-%d %H:%M:%S')
                logger.info(f"{prefix}Waiting for {wait_seconds} seconds until rate limit reset at {reset_datetime}")
                time.sleep(wait_seconds)
            logger.debug(f"{prefix}Fetching page with cursor={cursor}")
            search_res, cursor, reset_time = search_timeline(client, dl_manager, config['search'], cursor=cursor)
            logger.debug(f"New cursor: {cursor}")

            matches = []
            logger.debug(f"{prefix}Fetched {len(search_res)} tweets.")

            for item in search_res:
                matches += tweet_scanner(item.tweet, prefix)
            matches = list(set(matches))
            logger.debug(f"{prefix}Found {len(matches)} matches on this page.")

            for match in matches:
                netloc = urlparse(match).netloc
                dl = website_downloaders.get(netloc, generic_video_downloader)
                logger.debug(f"{prefix}Downloading {match} using {dl.__name__} (netloc: {netloc})")
                try:
                    dl(match, dl_manager, log_prefix=prefix)
                except DownloaderException as e:
                    logger.error(f"{prefix}Error downloading {match}", exc_info=e)
            i += 1
        logger.info("\x1b[32mTweet fetch loop completed.\x1b[0m")


def login() -> TwitterOpenapiPythonClient:
    """
    Log in to Twitter using cookies from a JSON file.
    :return: Twitter API client.
    """
    logger.debug("Attempting to load cookies from 'cookies.json'")
    if not Path("cookies.json").exists():
        raise FileNotFoundError("cookies.json not found. Please create it with your Twitter cookies.")
    with open("cookies.json", "r") as f:
        cookies_dict = json.load(f)
        if isinstance(cookies_dict, list):
            logger.debug(f"Converting cookies list ({len(cookies_dict)} items) to dict")
            cookies_dict = {k["name"]: k["value"] for k in cookies_dict}
        logger.debug(f"Loaded {len(cookies_dict)} cookies")

    api = TwitterOpenapiPython()
    api.additional_api_headers = {
        "sec-ch-ua-platform": '"Windows"',
    }
    api.additional_browser_headers = {
        "sec-ch-ua-platform": '"Windows"',
    }
    logger.debug("Creating Twitter client from cookies")
    return api.get_client_from_cookies(cookies=cookies_dict)

if __name__ == "__main__":
    config = load_config('config.yml')
    logger.setLevel(config.get('log_level', 'INFO').upper())
    logger.debug("Application started")
    tweet_fetch_loop(login())
