"""
Discovery module: Find URLs using SerpAPI and RSS feeds
"""
import time
import logging
import requests
import feedparser
from urllib.parse import urlencode
from src.utils import get_env_variable

logger = logging.getLogger(__name__)

class URLDiscoverer:
    """Discover URLs from multiple sources"""

    def __init__(self, config):
        self.config = config
        self.search_config = config.get("search", {})
        self.rss_config = config.get("rss", {})
        self.serpapi_key = get_env_variable("SERPAPI_KEY", required=True)

    def serpapi_search(self, query, num_results=20):
        """
        Search using SerpAPI (Google results)
        Docs: https://serpapi.com/search-api
        """
        logger.info(f"Searching SerpAPI for: {query}")

        params = {
            "api_key": self.serpapi_key,
            "q": query,
            "num": min(num_results, 100),  # Max 100 per request
            "engine": "google",
            "google_domain": "google.com",
            "gl": "us",
            "hl": "en"
        }

        try:
            url = "https://serpapi.com/search?" + urlencode(params)
            response = requests.get(url, timeout=30)
            response.raise_for_status()

            data = response.json()

            # Extract organic results
            results = []
            for item in data.get("organic_results", []):
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("link", ""),
                    "snippet": item.get("snippet", ""),
                    "source": "serpapi"
                })

            logger.info(f"Found {len(results)} results for query: {query}")
            return results

        except requests.RequestException as e:
            logger.error(f"SerpAPI request failed for query '{query}': {e}")
            return []
        except Exception as e:
            logger.error(f"Error parsing SerpAPI results: {e}")
            return []

    def rss_discover(self):
        """Discover URLs from RSS feeds"""
        if not self.rss_config.get("enabled", False):
            logger.info("RSS discovery disabled")
            return []

        feeds = self.rss_config.get("feeds", [])
        logger.info(f"Discovering URLs from {len(feeds)} RSS feeds")

        results = []
        for feed_url in feeds:
            try:
                logger.debug(f"Parsing RSS feed: {feed_url}")
                feed = feedparser.parse(feed_url)

                for entry in feed.entries[:20]:  # Limit per feed
                    results.append({
                        "title": entry.get("title", ""),
                        "url": entry.get("link", ""),
                        "snippet": entry.get("summary", "")[:200],
                        "source": "rss"
                    })

                logger.info(f"Found {len(feed.entries[:20])} entries from {feed_url}")

            except Exception as e:
                logger.warning(f"Failed to parse RSS feed {feed_url}: {e}")
                continue

        return results

    def discover_all(self):
        """
        Run complete discovery process
        Returns: List of deduplicated URL dictionaries
        """
        logger.info("=" * 60)
        logger.info("Starting URL discovery process")
        logger.info("=" * 60)

        all_results = []

        # 1. Search engine discovery (SerpAPI)
        queries = self.search_config.get("queries", [])
        results_per_query = self.search_config.get("results_per_query", 20)

        logger.info(f"Running {len(queries)} search queries...")
        for i, query in enumerate(queries, 1):
            logger.info(f"Query {i}/{len(queries)}: {query}")
            results = self.serpapi_search(query, results_per_query)
            all_results.extend(results)

            # Rate limiting between queries
            if i < len(queries):
                time.sleep(1)

        # 2. RSS discovery
        logger.info("Discovering from RSS feeds...")
        rss_results = self.rss_discover()
        all_results.extend(rss_results)

        # 3. Deduplicate by URL
        logger.info(f"Deduplicating {len(all_results)} total results...")
        seen_urls = set()
        deduplicated = []

        for result in all_results:
            url = result.get("url", "").split("#")[0].split("?")[0]  # Clean URL

            if url and url not in seen_urls and url.startswith("http"):
                seen_urls.add(url)
                deduplicated.append(result)

        logger.info("=" * 60)
        logger.info(f"Discovery complete: {len(deduplicated)} unique URLs found")
        logger.info("=" * 60)

        return deduplicated

# For testing
if __name__ == "__main__":
    from src.utils import load_config, setup_logging

    config = load_config()
    setup_logging(config)

    discoverer = URLDiscoverer(config)
    urls = discoverer.discover_all()

    print(f"\nDiscovered {len(urls)} URLs")
    for i, url_data in enumerate(urls[:10], 1):
        print(f"{i}. {url_data['title'][:60]}...")
        print(f"   {url_data['url']}")
