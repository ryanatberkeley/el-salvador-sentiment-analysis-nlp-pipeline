"""
Credibility assessment module
"""
import logging
import re
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

class CredibilityScorer:
    """Assess source credibility using multiple signals"""

    def __init__(self, config):
        self.config = config.get("credibility", {})
        self.whitelist_domains = set(self.config.get("whitelist_domains", []))
        self.whitelist_tlds = self.config.get("whitelist_tlds", [])
        self.min_article_len = self.config.get("min_article_len", 500)
        self.require_https = self.config.get("require_https", False)
        self.min_indicators = self.config.get("min_indicators", 1)

    def check_domain_whitelist(self, domain):
        """Check if domain is in whitelist"""
        # Direct match
        if domain in self.whitelist_domains:
            return True

        # Check if any whitelisted domain is a suffix
        for trusted in self.whitelist_domains:
            if domain.endswith(f".{trusted}") or domain == trusted:
                return True

        return False

    def check_tld(self, domain):
        """Check if domain has trusted TLD"""
        for tld in self.whitelist_tlds:
            if domain.endswith(tld):
                return True
        return False

    def check_https(self, url):
        """Check if URL uses HTTPS"""
        return url.startswith("https://")

    def check_length(self, text_length):
        """Check if article meets minimum length"""
        return text_length >= self.min_article_len

    def detect_byline(self, text, title="", author=""):
        """Detect author byline in content"""
        if author:  # Already has author from metadata
            return True

        # Check title
        if title and re.search(r'\bby\s+[A-Z][a-z]+', title, re.IGNORECASE):
            return True

        # Check first 500 chars
        preview = text[:500]

        patterns = [
            r'\bby\s+[A-Z][a-z]+\s+[A-Z][a-z]+',  # By John Doe
            r'\bpor\s+[A-Z][a-z]+',  # Por Juan (Spanish)
            r'\bescrito\s+por\b',  # Escrito por
            r'\bautor[:\s]',  # Autor:
        ]

        for pattern in patterns:
            if re.search(pattern, preview, re.IGNORECASE):
                return True

        return False

    def detect_citations(self, text):
        """Detect if article has external citations/sources"""
        # Count URLs in text (excluding social media)
        url_pattern = r'https?://(?!(?:twitter|facebook|instagram|linkedin)\.com)[^\s<>"\')]+|www\.[^\s<>"\')]+\.[a-z]{2,}'
        urls = re.findall(url_pattern, text.lower())

        # Filter out likely false positives
        valid_urls = [u for u in urls if not any(x in u for x in ['javascript:', 'mailto:', '.jpg', '.png', '.gif'])]

        # Check for citation indicators
        citation_indicators = [
            'according to',
            'reported by',
            'study published',
            'research shows',
            'según',  # Spanish: according to
            'estudio',  # Spanish: study
            'investigación'  # Spanish: research
        ]

        has_indicators = any(ind in text.lower() for ind in citation_indicators)

        return len(valid_urls) >= 2 or has_indicators

    def detect_transparency(self, text, domain):
        """Detect transparency indicators (about page, organization info)"""
        preview = text[:2000].lower()

        indicators = [
            'about us',
            'quiénes somos',
            'our mission',
            'nuestra misión',
            'editorial',
            'newsroom',
            'redacción',
            'contact',
            'contacto'
        ]

        # Known transparent domains
        transparent_domains = ['reuters.com', 'apnews.com', 'bbc.com', 'worldbank.org', 'imf.org']

        if domain in transparent_domains:
            return True

        return any(ind in preview for ind in indicators)

    def score(self, article):
        """
        Calculate credibility score (0-1)

        Args:
            article: dict with url, domain, text, title, author, etc.

        Returns:
            tuple: (score, signals_dict)
        """
        url = article.get("url", "")
        domain = article.get("domain", "")
        text = article.get("text", "")
        text_length = article.get("text_length", 0)
        title = article.get("title", "")
        author = article.get("author", "")

        # Signals (binary)
        signals = {
            "domain_whitelisted": self.check_domain_whitelist(domain),
            "tld_trusted": self.check_tld(domain),
            "https": self.check_https(url),
            "length_ok": self.check_length(text_length),
            "has_byline": self.detect_byline(text, title, author),
            "has_citations": self.detect_citations(text),
            "has_transparency": self.detect_transparency(text, domain)
        }

        # Calculate indicator count
        indicator_count = sum([
            signals["has_byline"],
            signals["has_citations"],
            signals["has_transparency"]
        ])
        signals["indicator_count"] = indicator_count
        signals["min_indicators_met"] = indicator_count >= self.min_indicators

        # Weighted scoring
        score = 0.0

        # Domain trust (40%)
        if signals["domain_whitelisted"]:
            score += 0.40
        elif signals["tld_trusted"]:
            score += 0.20

        # Length (15%)
        if signals["length_ok"]:
            score += 0.15

        # Quality indicators (30%)
        indicator_score = (indicator_count / 3.0) * 0.30
        score += indicator_score

        # HTTPS (10%)
        if signals["https"]:
            score += 0.10

        # Penalty for very short articles
        if text_length < 300:
            score *= 0.5

        # Bonus for excellent sources
        if signals["domain_whitelisted"] and signals["has_citations"] and signals["length_ok"]:
            score = min(1.0, score + 0.1)

        logger.debug(f"Credibility score for {domain}: {score:.2f}")

        return round(score, 3), signals

    def should_keep(self, article, score):
        """Determine if article should be kept based on minimum score"""
        min_score = self.config.get("min_score", 0.4)
        return score >= min_score

# For testing
if __name__ == "__main__":
    from src.utils import load_config, setup_logging

    config = load_config()
    setup_logging(config)

    scorer = CredibilityScorer(config)

    # Test article
    test_article = {
        "url": "https://www.reuters.com/business/finance/test",
        "domain": "reuters.com",
        "title": "Bitcoin in El Salvador: Analysis by Jane Smith",
        "author": "Jane Smith",
        "text": "According to the IMF, Bitcoin adoption in El Salvador has shown mixed results. " * 20,
        "text_length": 1000
    }

    score, signals = scorer.score(test_article)
    print(f"\nCredibility Score: {score}")
    print(f"Signals: {signals}")
    print(f"Keep article: {scorer.should_keep(test_article, score)}")
