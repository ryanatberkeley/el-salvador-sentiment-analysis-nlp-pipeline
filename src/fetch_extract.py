"""
Fetch and extract clean text from web pages
"""
import time
import logging
import requests
import trafilatura
from urllib.parse import urlparse
from collections import defaultdict

logger = logging.getLogger(__name__)

class ContentFetcher:
    """Fetch and extract content from URLs"""

    def __init__(self, config):
        self.config = config
        self.crawl_config = config.get("crawl", {})
        self.user_agent = self.crawl_config.get("user_agent", "Mozilla/5.0")
        self.timeout = self.crawl_config.get("timeout_sec", 20)
        self.max_retries = self.crawl_config.get("max_retries", 2)
        self.sleep_sec = self.crawl_config.get("sleep_sec", 2.0)
        self.max_per_domain = self.crawl_config.get("max_per_domain", 5)

        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.user_agent})

    def get_domain(self, url):
        """Extract domain from URL"""
        try:
            return urlparse(url).netloc.lower()
        except:
            return ""

    def fetch_html(self, url):
        """Fetch HTML content from URL with retries"""
        for attempt in range(self.max_retries + 1):
            try:
                logger.debug(f"Fetching URL (attempt {attempt + 1}): {url}")
                response = self.session.get(
                    url,
                    timeout=self.timeout,
                    allow_redirects=True
                )
                response.raise_for_status()

                # Check content type
                content_type = response.headers.get("Content-Type", "").lower()
                if "text/html" not in content_type and "text/plain" not in content_type:
                    logger.warning(f"Non-HTML content type: {content_type} for {url}")
                    return None

                return response.text

            except requests.Timeout:
                logger.warning(f"Timeout fetching {url} (attempt {attempt + 1})")
            except requests.RequestException as e:
                logger.warning(f"Request error for {url}: {e}")
            except Exception as e:
                logger.error(f"Unexpected error fetching {url}: {e}")

            if attempt < self.max_retries:
                time.sleep(2)

        return None

    def extract_text(self, html, url):
        """Extract clean text using trafilatura"""
        try:
            # Use trafilatura for robust extraction
            extracted = trafilatura.extract(
                html,
                url=url,
                include_comments=False,
                include_tables=False,
                no_fallback=False,
                favor_recall=True,  # Get more content
                include_links=False
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
                    "sitename": metadata.sitename or ""
                }
        except:
            pass

        return {
            "title": "",
            "author": "",
            "date": "",
            "description": "",
            "sitename": ""
        }

    def fetch_and_extract(self, url_data):
        """
        Fetch URL and extract content + metadata
        Returns: dict with url, domain, title, author, text, etc.
        """
        url = url_data.get("url", "")
        domain = self.get_domain(url)

        # Fetch HTML
        html = self.fetch_html(url)
        if not html:
            logger.warning(f"Failed to fetch HTML for {url}")
            return None

        # Extract text
        text = self.extract_text(html, url)
        if not text:
            logger.warning(f"No text extracted from {url}")
            return None

        # Extract metadata
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
            "discovery_source": url_data.get("source", "unknown")
        }

        logger.info(f"✓ Extracted {len(text)} chars from {domain}")
        return result

    def batch_fetch(self, url_list):
        """
        Fetch multiple URLs with domain rate limiting
        Returns: list of extracted content dicts
        """
        logger.info(f"Starting batch fetch of {len(url_list)} URLs")

        # Track domain request counts
        domain_counts = defaultdict(int)
        results = []
        skipped = 0

        for i, url_data in enumerate(url_list, 1):
            url = url_data.get("url", "")
            domain = self.get_domain(url)

            # Check domain limit
            if domain_counts[domain] >= self.max_per_domain:
                logger.debug(f"Skipping {url} - domain limit reached for {domain}")
                skipped += 1
                continue

            logger.info(f"Processing {i}/{len(url_list)}: {url[:80]}...")

            # Fetch and extract
            result = self.fetch_and_extract(url_data)

            if result:
                results.append(result)
                domain_counts[domain] += 1

            # Rate limiting
            if i < len(url_list):
                time.sleep(self.sleep_sec)

        logger.info("=" * 60)
        logger.info(f"Batch fetch complete:")
        logger.info(f"  Successfully extracted: {len(results)}")
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

    # Test with a single URL
    test_url = {
        "url": "https://www.reuters.com/technology/",
        "title": "Test Article"
    }

    result = fetcher.fetch_and_extract(test_url)
    if result:
        print(f"\nTitle: {result['title']}")
        print(f"Text length: {result['text_length']}")
        print(f"Text preview: {result['text'][:200]}...")
