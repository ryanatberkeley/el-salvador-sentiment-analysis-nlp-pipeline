"""
Fetch and extract clean text from web pages, falling back to the Wayback Machine
"""
import time
import logging
import requests
import trafilatura
from urllib.parse import urlparse
from collections import defaultdict

logger = logging.getLogger(__name__)

# Standard browser headers. Many news sites return 403 to a bare "Mozilla/5.0".
# These replace the user_agent setting in config/settings.yml.
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
}

# Retrying these never helps, so fail fast and try the archive instead.
NO_RETRY_STATUSES = {400, 401, 402, 403, 404, 410, 451}

# Social and aggregator pages are never articles; don't look for archived copies.
NO_ARCHIVE_DOMAINS = (
    "facebook.com", "instagram.com", "twitter.com", "x.com", "linkedin.com",
    "reddit.com", "quora.com", "youtube.com", "tiktok.com", "news.google.com",
)

# Space out Wayback Machine requests so the archive doesn't rate-limit us.
WAYBACK_MIN_INTERVAL_SEC = 5


def _fix_encoding(response):
    """requests assumes ISO-8859-1 when a page doesn't declare a charset, which
    garbles Spanish accents ("JÃ³venes"). Detect the real encoding instead."""
    if response.encoding and response.encoding.lower() == "iso-8859-1":
        response.encoding = response.apparent_encoding


class ContentFetcher:
    """Fetch and extract content from URLs"""

    def __init__(self, config):
        self.config = config
        self.crawl_config = config.get("crawl", {})
        self.timeout = self.crawl_config.get("timeout_sec", 20)
        self.max_retries = self.crawl_config.get("max_retries", 2)
        self.sleep_sec = self.crawl_config.get("sleep_sec", 2.0)
        self.max_per_domain = self.crawl_config.get("max_per_domain", 5)
        self.use_wayback = self.crawl_config.get("use_wayback", True)

        self.session = requests.Session()
        self.session.headers.update(BROWSER_HEADERS)

        self._last_wayback_request = 0.0
        self.wayback_recovered = 0

    def get_domain(self, url):
        """Extract domain from URL"""
        try:
            return urlparse(url).netloc.lower()
        except Exception:
            return ""

    def fetch_html(self, url):
        """Fetch HTML from URL with retries.

        Returns (html or None, reason) where reason explains a failure.
        """
        reason = "request error"
        for attempt in range(self.max_retries + 1):
            try:
                response = self.session.get(url, timeout=self.timeout, allow_redirects=True)

                if response.status_code in NO_RETRY_STATUSES:
                    logger.warning(f"Request error for {url}: HTTP {response.status_code}")
                    return None, f"HTTP {response.status_code}"

                response.raise_for_status()

                content_type = response.headers.get("Content-Type", "").lower()
                if "text/html" not in content_type and "text/plain" not in content_type:
                    logger.warning(f"Non-HTML content type: {content_type} for {url}")
                    return None, "not HTML"

                _fix_encoding(response)
                return response.text, "ok"

            except requests.Timeout:
                reason = "timeout"
                logger.warning(f"Timeout fetching {url} (attempt {attempt + 1})")
            except requests.RequestException as e:
                reason = "request error"
                logger.warning(f"Request error for {url}: {e}")
            except Exception as e:
                reason = "unexpected error"
                logger.error(f"Unexpected error fetching {url}: {e}")

            if attempt < self.max_retries:
                time.sleep(2)

        return None, reason

    def fetch_from_wayback(self, url):
        """Fetch the earliest archived copy of a page from the Wayback Machine.

        In the archive URL, timestamp "0" means the earliest capture (the page as
        first published) and "id_" returns the original HTML without the archive's
        toolbar. Returns HTML or None.
        """
        if not self.use_wayback:
            return None

        domain = self.get_domain(url)
        if any(domain == d or domain.endswith("." + d) for d in NO_ARCHIVE_DOMAINS):
            return None

        wait = WAYBACK_MIN_INTERVAL_SEC - (time.time() - self._last_wayback_request)
        if wait > 0:
            time.sleep(wait)
        self._last_wayback_request = time.time()

        archive_url = f"https://web.archive.org/web/0id_/{url}"
        try:
            response = self.session.get(
                archive_url, timeout=max(self.timeout, 30), allow_redirects=True
            )
            if response.status_code == 429:
                logger.warning(
                    "Wayback Machine is rate limiting requests. "
                    "Turning off the archive fallback for the rest of this run."
                )
                self.use_wayback = False
                return None
            if response.status_code != 200:
                logger.debug(f"No archived copy of {url} (HTTP {response.status_code})")
                return None
            if "text/html" not in response.headers.get("Content-Type", "").lower():
                return None

            _fix_encoding(response)
            return response.text

        except requests.RequestException as e:
            logger.debug(f"Wayback Machine request failed for {url}: {e}")
            return None

    def extract_text(self, html, url):
        """Extract clean text using trafilatura"""
        try:
            extracted = trafilatura.extract(
                html,
                url=url,
                include_comments=False,
                include_tables=False,
                no_fallback=False,
                favor_recall=True,
                include_links=False,
            )
            return extracted or ""
        except Exception as e:
            logger.error(f"Text extraction failed for {url}: {e}")
            return ""

    def extract_metadata(self, html, url):
        """Extract metadata (title, author, date) using trafilatura"""
        try:
            metadata = trafilatura.extract_metadata(html, default_url=url)
            if metadata:
                return {
                    "title": metadata.title or "",
                    "author": metadata.author or "",
                    "date": metadata.date or "",
                    "description": metadata.description or "",
                    "sitename": metadata.sitename or "",
                }
        except Exception:
            pass

        return {"title": "", "author": "", "date": "", "description": "", "sitename": ""}

    def fetch_and_extract(self, url_data):
        """
        Fetch URL and extract content + metadata. If the site blocks us, the
        link is dead, or no text comes out, try the Wayback Machine's copy.
        Returns: dict with url, domain, title, author, text, etc., or None
        """
        url = url_data.get("url", "")
        domain = self.get_domain(url)

        html, reason = self.fetch_html(url)
        text = ""
        if html:
            text = self.extract_text(html, url)
            if not text:
                logger.warning(f"No text extracted from {url}")
        else:
            logger.warning(f"Failed to fetch HTML for {url} ({reason})")

        fetched_via = "direct"
        if not text:
            archived_html = self.fetch_from_wayback(url)
            archived_text = self.extract_text(archived_html, url) if archived_html else ""
            if archived_text:
                html, text, fetched_via = archived_html, archived_text, "wayback"
                self.wayback_recovered += 1
                logger.info(f"✓ Recovered from the Wayback Machine: {url}")

        if not text:
            return None

        metadata = self.extract_metadata(html, url)

        result = {
            "url": url,
            "domain": domain,
            "title": metadata.get("title") or url_data.get("title", ""),
            "author": metadata.get("author", ""),
            "published_date": metadata.get("date", ""),
            "description": metadata.get("description") or url_data.get("snippet", ""),
            "sitename": metadata.get("sitename", ""),
            "text": text,
            "text_length": len(text),
            "html_length": len(html),
            "discovery_source": url_data.get("source", "unknown"),
            "search_query": url_data.get("search_query", ""),
            "search_window": url_data.get("search_window", ""),
            "fetched_via": fetched_via,
        }

        logger.info(f"✓ Extracted {len(text)} chars from {domain} ({fetched_via})")
        return result

    def batch_fetch(self, url_list):
        """
        Fetch multiple URLs with domain rate limiting
        Returns: list of extracted content dicts
        """
        logger.info(f"Starting batch fetch of {len(url_list)} URLs")

        domain_counts = defaultdict(int)
        results = []
        skipped = 0

        for i, url_data in enumerate(url_list, 1):
            url = url_data.get("url", "")
            domain = self.get_domain(url)

            if domain_counts[domain] >= self.max_per_domain:
                logger.debug(f"Skipping {url} - domain limit reached for {domain}")
                skipped += 1
                continue

            logger.info(f"Processing {i}/{len(url_list)}: {url[:80]}...")

            result = self.fetch_and_extract(url_data)
            if result:
                results.append(result)
                domain_counts[domain] += 1

            if i < len(url_list):
                time.sleep(self.sleep_sec)

        logger.info("=" * 60)
        logger.info("Batch fetch complete:")
        logger.info(f"  Successfully extracted: {len(results)}")
        logger.info(f"    of which from the Wayback Machine: {self.wayback_recovered}")
        logger.info(f"  Failed/empty: {len(url_list) - len(results) - skipped}")
        logger.info(f"  Skipped (domain limit): {skipped}")
        logger.info("=" * 60)

        return results


# For testing
if __name__ == "__main__":
    from src.utils import load_config, setup_logging

    config = load_config()
    setup_logging(config)

    fetcher = ContentFetcher(config)
    test_url = {"url": "https://www.reuters.com/technology/", "title": "Test Article"}

    result = fetcher.fetch_and_extract(test_url)
    if result:
        print(f"\nTitle: {result['title']}")
        print(f"Fetched via: {result['fetched_via']}")
        print(f"Text length: {result['text_length']}")
        print(f"Text preview: {result['text'][:200]}...")