"""
Discovery module: find article URLs with SerpAPI (Google search) and, optionally, RSS feeds
"""
import re
import time
import logging
import requests
import feedparser
from src.utils import get_env_variable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DATE RANGE. Run 1: 2016 to 2020. Run 2: change to 2020 and 2026.
# ---------------------------------------------------------------------------
START_YEAR = 2016
END_YEAR = 2020

# Search each year on its own. Google only returns a few dozen results per
# search, so five one-year searches surface far more unique articles than one
# five-year search. Uses about (number of years) times more SerpAPI searches.
SPLIT_BY_YEAR = True

# RSS feeds only carry recent posts, so they ignore the date range above, and
# Google News RSS links are redirect pages that can't be extracted.
INCLUDE_RSS = False

# Spanish queries search Salvadoran Google in Spanish. English queries search
# US Google in English, as before.
ENGLISH_LOCALE = {"google_domain": "google.com", "gl": "us", "hl": "en"}
SPANISH_LOCALE = {"google_domain": "google.com.sv", "gl": "sv", "hl": "es"}
SPANISH_WORDS = {
    "minería", "mineria", "metálica", "metalica", "ley", "impacto", "ambiental",
    "contaminación", "contaminacion", "defensores", "del", "agua", "derogación",
    "derogacion", "contra", "económico", "economico", "evaluación", "evaluacion",
    "préstamo", "prestamo", "fmi", "criptomonedas", "criptomoneda", "cripto",
    "energía", "energia", "geotérmica", "geotermica", "bonos", "volcán", "volcan",
    "turismo", "reversión", "reversion", "prohibición", "prohibicion", "de", "la",
    "los", "las", "y", "en", "sobre", "minera", "mineras", "minero", "mineros",
}

# SerpAPI sometimes takes longer than 30 seconds on later result pages. A
# timed-out page is retried instead of abandoning the rest of the query.
# SerpAPI serves repeat searches from its one-hour cache for free.
SERPAPI_TIMEOUT_SEC = 90
SERPAPI_MAX_ATTEMPTS = 3
RESULTS_PER_PAGE = 10


class SerpAPIQuotaError(Exception):
    """The SerpAPI account is out of searches."""


class URLDiscoverer:
    """Discover URLs from multiple sources"""

    def __init__(self, config):
        self.config = config
        self.search_config = config.get("search", {})
        self.rss_config = config.get("rss", {})
        self.serpapi_key = get_env_variable("SERPAPI_KEY", required=True)
        self.serpapi_requests = 0

    @staticmethod
    def date_windows():
        """List of (start_year, end_year) windows to search."""
        if SPLIT_BY_YEAR:
            return [(year, year) for year in range(START_YEAR, END_YEAR + 1)]
        return [(START_YEAR, END_YEAR)]

    @staticmethod
    def locale_for(query):
        """Salvadoran Spanish Google for Spanish queries, US English Google otherwise."""
        words = set(re.findall(r"\w+", query.lower()))
        return SPANISH_LOCALE if words & SPANISH_WORDS else ENGLISH_LOCALE

    def _fetch_page(self, params, label):
        """Fetch one page of SerpAPI results, retrying timeouts and server errors.

        Returns the JSON dict, or None if every attempt failed.
        """
        for attempt in range(1, SERPAPI_MAX_ATTEMPTS + 1):
            try:
                self.serpapi_requests += 1
                response = requests.get(
                    "https://serpapi.com/search",
                    params=params,
                    timeout=SERPAPI_TIMEOUT_SEC,
                )
                if response.status_code == 401:
                    raise RuntimeError(
                        "SerpAPI rejected the API key (HTTP 401). Check SERPAPI_KEY in .env."
                    )
                if response.status_code == 429 and "run out of searches" in response.text.lower():
                    raise SerpAPIQuotaError(response.text[:200])
                response.raise_for_status()
                return response.json()

            except (RuntimeError, SerpAPIQuotaError):
                raise
            except (requests.RequestException, ValueError) as e:
                if attempt < SERPAPI_MAX_ATTEMPTS:
                    wait = 5 * attempt
                    logger.warning(
                        f"SerpAPI attempt {attempt} failed for {label}: {e}. Retrying in {wait}s"
                    )
                    time.sleep(wait)
                else:
                    logger.error(
                        f"SerpAPI request failed for {label} after {attempt} attempts: {e}"
                    )
        return None

    def serpapi_search(self, query, num_results=50):
        """Search Google through SerpAPI, up to num_results per date window."""
        locale = self.locale_for(query)
        logger.info(
            f"Searching SerpAPI for: {query} "
            f"(up to {num_results} per window, {locale['hl']}/{locale['gl']})"
        )

        results = []
        per_window = []

        for start_year, end_year in self.date_windows():
            window = str(start_year) if start_year == end_year else f"{start_year}-{end_year}"
            window_count = 0

            for start in range(0, num_results, RESULTS_PER_PAGE):
                params = {
                    "api_key": self.serpapi_key,
                    "engine": "google",
                    "q": query,
                    "num": RESULTS_PER_PAGE,
                    "start": start,
                    "tbs": f"cdr:1,cd_min:1/1/{start_year},cd_max:12/31/{end_year}",
                    **locale,
                }
                data = self._fetch_page(params, f"query '{query}' ({window}) at start={start}")
                if data is None:
                    break  # gave up on this page; move on to the next window

                page = data.get("organic_results", [])
                if not page:
                    logger.info(f"Reached the end of Google's results at index {start} ({window}).")
                    break

                for item in page:
                    results.append({
                        "title": item.get("title", ""),
                        "url": item.get("link", ""),
                        "snippet": item.get("snippet", ""),
                        "source": "serpapi",
                        "search_query": query,
                        "search_window": window,
                        "search_locale": locale["gl"],
                    })
                window_count += len(page)
                time.sleep(0.5)

            per_window.append(f"{window}: {window_count}")

        breakdown = f" ({', '.join(per_window)})" if len(per_window) > 1 else ""
        logger.info(f"Found {len(results)} total results for query: {query}{breakdown}")
        return results

    def rss_discover(self):
        """Discover URLs from RSS feeds"""
        if not INCLUDE_RSS:
            logger.info("RSS discovery skipped: feeds only carry recent posts and ignore the date range")
            return []
        if not self.rss_config.get("enabled", False):
            logger.info("RSS discovery disabled")
            return []

        feeds = self.rss_config.get("feeds", [])
        logger.info(f"Discovering URLs from {len(feeds)} RSS feeds")

        results = []
        for feed_url in feeds:
            try:
                feed = feedparser.parse(feed_url)
                for entry in feed.entries[:20]:
                    results.append({
                        "title": entry.get("title", ""),
                        "url": entry.get("link", ""),
                        "snippet": str(entry.get("summary", ""))[:200],
                        "source": "rss",
                    })
                logger.info(f"Found {len(feed.entries[:20])} entries from {feed_url}")
            except Exception as e:
                logger.warning(f"Failed to parse RSS feed {feed_url}: {e}")

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

        queries = self.search_config.get("queries", [])
        results_per_query = self.search_config.get("results_per_query", 20)
        windows = self.date_windows()
        pages_per_window = -(-results_per_query // RESULTS_PER_PAGE)
        max_searches = len(queries) * len(windows) * pages_per_window

        logger.info(
            f"Running {len(queries)} search queries across {len(windows)} date window(s), "
            f"{START_YEAR}-{END_YEAR}..."
        )
        logger.info(f"At most {max_searches} SerpAPI searches; fewer when Google runs out of results")

        for i, query in enumerate(queries, 1):
            logger.info(f"Query {i}/{len(queries)}: {query}")
            try:
                all_results.extend(self.serpapi_search(query, results_per_query))
            except SerpAPIQuotaError as e:
                logger.error(
                    f"SerpAPI account is out of searches. Stopping discovery after "
                    f"{i - 1} of {len(queries)} queries: {e}"
                )
                break
            if i < len(queries):
                time.sleep(1)

        logger.info("Discovering from RSS feeds...")
        all_results.extend(self.rss_discover())

        # Deduplicate by URL, ignoring #fragments and ?query strings
        logger.info(f"Deduplicating {len(all_results)} total results...")
        seen_urls = set()
        deduplicated = []
        for result in all_results:
            url = result.get("url", "").split("#")[0].split("?")[0]
            if url and url not in seen_urls and url.startswith("http"):
                seen_urls.add(url)
                deduplicated.append(result)

        logger.info("=" * 60)
        logger.info(f"SerpAPI requests sent: {self.serpapi_requests}")
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
