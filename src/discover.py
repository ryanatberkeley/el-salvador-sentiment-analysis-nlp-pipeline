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
#changed by ryan
    def serpapi_search(self, query, num_results=50):
        """
        Search using SerpAPI with pagination for paid accounts
        """
        logger.info(f"Searching SerpAPI for: {query} (Target: {num_results} results)")

        all_query_results = []
        results_per_page = 10  # Google standard organic results per page
        
        # Loop through pages using the 'start' parameter (0, 10, 20, 30...)
        for start_index in range(0, num_results, results_per_page):
            logger.debug(f"Fetching results {start_index} to {start_index + results_per_page}...")
            
            params = {
                "api_key": self.serpapi_key,
                "q": query,
                "num": results_per_page,  
                "start": start_index,     # <--- This tells Google to go to the next page!
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
                page_results = data.get("organic_results", [])
                
                # If Google runs out of relevant articles, stop early
                if not page_results:
                    logger.info(f"Reached the end of Google's results at index {start_index}.")
                    break

                for item in page_results:
                    all_query_results.append({
                        "title": item.get("title", ""),
                        "url": item.get("link", ""),
                        "snippet": item.get("snippet", ""),
                        "source": "serpapi"
                    })
                
                # Be polite to the API, tiny sleep between page requests
                time.sleep(0.5)

            except requests.RequestException as e:
                logger.error(f"SerpAPI request failed for query '{query}' at start={start_index}: {e}")
                break
            except Exception as e:
                logger.error(f"Error parsing SerpAPI results: {e}")
                break

        logger.info(f"Found {len(all_query_results)} total results for query: {query}")
        return all_query_results

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
                        "snippet": str(entry.get("summary", ""))[:200], #ryan changed here
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
