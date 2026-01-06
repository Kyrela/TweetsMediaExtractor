# <img alt="Icon" height="50" src="icon.png"/> TweetsMediaExtractor

TweetsMediaExtractor is a Python script that extracts videos that are behind
an external link from search results on Twitter (e.g. CDN links).

Support for direct tweet media download and other formats may be added
in the future.

# Features

- Twitter search with pagination
- t.co link correction
- Regex-based url detection (allows for altered link matching, e.g. `my_cdn com/445564` to `https://my_cdn.com/445564`)
- URL caching to avoid duplicate downloads
- Rate limit handling with retries
- Original video quality download
- Download videos from external links
  - Direct video links
  - Gofile links
- Highly configurable via a YAML file

## Installation

### Precompiled Executable

1. Go to the latest [release](https://github.com/Kyrela/TweetsMediaExtractor/releases/latest) and download the
   precompiled executable for your platform.

### Python Script

If you prefer to run the Python script directly, or cannot find a suitable
precompiled executable, follow these steps:

1. Clone the repository:
   ```bash
   git clone https://github.com/Kyrela/TweetsMediaExtractor.git
   cd TweetsMediaExtractor
   ```
2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

1. Create a `config.yml` file with your search and download preferences. (See
   the Configuration section below for details.)
2. Export your Twitter cookies from your browser and save them in a file named
   `cookies.json` in the same directory as the script.
   (You can use browser extensions like "Cookie-Editor" to export cookies.)
3. Run the script by double-clicking the executable or using the command line:
   ```bash
   .\TweetsMediaExtractor.exe
   ```
   Or, if running the Python script directly:
   ```bash
   python tweets_media_extractor.py
   ```
4. The downloaded medias will be saved in the specified output directory.

## Configuration

The `config.yml` file contains various settings to customize the behavior of the
script. Here's the list of available options:

```yaml
search:
  raw_query: "your search terms here"
  # The raw search query to use on Twitter.
  # More information about Twitter search query syntax: https://docs.x.com/x-api/posts/search/integrate/build-a-query
  # Required.
  product: "Top"
  # The type of search to perform.
  # Options: "Top", "Latest", "People", "Photos", "Videos".
  # More info: https://help.x.com/en/resources/recommender-systems/search-recommendations
  # Default is "Top".
  count: 20
  # Number of tweets to fetch per request (max 100).
  # It might not always return the requested number.
  # Default is 20.

max_search_pages: 100
# Maximum number of pages to fetch. Set to null for no limit.
# Default is null.
log_level: "DEBUG"
# Logging level. It controls the verbosity of the output.
# Options: "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL".
# Default is "INFO".

downloads:
  output: "output"
  # Directory to save downloaded videos.
  # Default is "output".
  min_size: 1048576  # 1 MB
  # Minimum file size in bytes to download.
  # Default is 0.
  max_size: 524288000  # 500 MB
  # Maximum file size in bytes to download.
  # Default is null (no limit).
  chunk_size: 8192
  # Chunk size in bytes for downloading files.
  # It represents the amount of data to be read into memory at once.
  # Default is 8192 bytes (8 KB).
  timeout: 30
  # Timeout in seconds for download requests.
  # Default is 30 seconds.
  retries: 3
  # Number of retries for failed downloads.
  # Also affects twitter searches.
  # Default is 3.
  backoff_factor: 0.5
  # Backoff factor for retries.
  # Default is 0.5.
  status_forcelist: [500, 502, 503, 504]
  # HTTP status codes that trigger a retry.
  # Default is [500, 502, 503, 504].
  cache_links_path: ".link_cache.txt"
  # Path to the file that stores cached links to avoid duplicate downloads.
  # Default is ".link_cache.txt".

external_links:
  "https://video.twimg.com/\\S*": null
  "https://gofile.io/d/\\S*": null
  "ttps://video.twimg.com/\\S*": "h\\g<0>"
  "ttps://gofile.io/d/\\S*": "h\\g<0>"
# A mapping of regex patterns to replacement strings for extracting
# external links from tweets.
# The keys are regex patterns to match URLs in tweets.
# The values are replacement strings that can include backreferences.
# If the value is null, the matched URL is used as is.
# This allows for correcting altered links (e.g., missing 'h' in 'https').
# Required.
```

Example for finding and downloading movies:

```yaml
search:
  raw_query: '(movie OR film OR blu-ray OR 1080p OR 720p OR 4k OR hdrip OR brrip OR dvdrip OR x264 OR x265 OR h264 OR h265) AND "gofile"'
  product: "Latest"
  # '(movie OR film OR blu-ray OR 1080p OR 720p OR 4k OR hdrip OR brrip OR dvdrip OR x264 OR x265 OR h264 OR h265) AND gofile' with 'Top' also provide good results.
  count: 50

max_search_pages: 200

downloads:
  output: "movies"
  min_size: 209715200  # 200 MB
  max_size: 21474836480  # 20 GB
 
external_links:
  "https://gofile.io/d/\\S*": null
  "ttps://gofile.io/d/\\S*": "h\\g<0>"
  "gofile io/d/(\\S*)": "https://gofile.io/d/\\g<1>"
```

## Roadmap

- [ ] Add support for direct tweet media download.
  - [ ] keywork-based (e.g. "movie", "blu-ray").
  - [ ] user-based (e.g. from specific Twitter users, by id).
- [ ] Add support for more external link providers.
  - [ ] Google Drive.
  - [ ] Mega.nz.
  - [ ] Mediafire.
  - [ ] Zippyshare.
  - [ ] Anonfiles.
  - [ ] Others (suggestions welcome).
- [ ] Add support for more formats.
  - [ ] Images (with direct links and external links).
  - [ ] Other (with only external links).
- [ ] Add pornographic content filter (only sfw/only nsfw/both).
- [ ] Improve error handling and logging.
- [ ] Add support for minimal length and maximal length filters.
