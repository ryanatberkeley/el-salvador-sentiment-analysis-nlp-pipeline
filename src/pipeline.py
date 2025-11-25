"""
Main ETL pipeline orchestrator
"""
import logging
import hashlib
import json
from pathlib import Path
from datetime import datetime
import pandas as pd

from src.discover import URLDiscoverer
from src.fetch_extract import ContentFetcher
from src.credibility import CredibilityScorer
from src.nlp import NLPAnalyzer

logger = logging.getLogger(__name__)

class ScraperPipeline:
    """Main pipeline to orchestrate the scraping process"""

    def __init__(self, config):
        self.config = config
        self.discoverer = URLDiscoverer(config)
        self.fetcher = ContentFetcher(config)
        self.credibility_scorer = CredibilityScorer(config)
        self.nlp_analyzer = NLPAnalyzer(config)

        # Storage paths
        self.storage_config = config.get("storage", {})
        self.sqlite_path = self.storage_config.get("sqlite_path", "data/processed/articles.db")
        self.csv_path = self.storage_config.get("csv_path", "data/processed/articles.csv")
        self.excel_path = self.storage_config.get("excel_path", "data/processed/articles.xlsx")

    def generate_article_id(self, url):
        """Generate unique ID from URL"""
        return hashlib.sha256(url.encode()).hexdigest()[:16]

    def save_discovered_urls(self, urls):
        """Save discovered URLs to JSON file"""
        output_path = Path("data/raw/discovered_urls.json")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(urls, f, indent=2, ensure_ascii=False)

        logger.info(f"Saved {len(urls)} discovered URLs to {output_path}")

    def save_results(self, articles_df):
        """Save results to multiple formats"""
        if articles_df.empty:
            logger.warning("No articles to save")
            return

        # Create output directory
        Path(self.csv_path).parent.mkdir(parents=True, exist_ok=True)

        # Add metadata
        articles_df["scraped_at"] = datetime.now().isoformat()

        # Save to CSV
        articles_df.to_csv(self.csv_path, index=False, encoding='utf-8')
        logger.info(f"Saved {len(articles_df)} articles to CSV: {self.csv_path}")

        # Save to Excel
        try:
            articles_df.to_excel(self.excel_path, index=False, engine='openpyxl')
            logger.info(f"Saved {len(articles_df)} articles to Excel: {self.excel_path}")
        except Exception as e:
            logger.warning(f"Could not save Excel file: {e}")

        # Save to SQLite
        try:
            import sqlite3
            conn = sqlite3.connect(self.sqlite_path)

            # Check if table exists and load existing data
            existing_df = pd.DataFrame()
            try:
                existing_df = pd.read_sql("SELECT * FROM articles", conn)
                logger.info(f"Found {len(existing_df)} existing articles in database")
            except:
                logger.info("Creating new articles table")

            # Combine with existing, deduplicate by ID
            if not existing_df.empty:
                combined_df = pd.concat([existing_df, articles_df], ignore_index=True)
                combined_df = combined_df.drop_duplicates(subset=['id'], keep='last')
                logger.info(f"Merged data: {len(combined_df)} total articles (removed {len(existing_df) + len(articles_df) - len(combined_df)} duplicates)")
            else:
                combined_df = articles_df

            # Save to database
            combined_df.to_sql("articles", conn, if_exists="replace", index=False)
            conn.close()

            logger.info(f"Saved to SQLite: {self.sqlite_path}")

        except Exception as e:
            logger.error(f"Failed to save to SQLite: {e}")

    def run(self):
        """Execute the complete pipeline"""
        logger.info("="*80)
        logger.info("STARTING SCRAPER PIPELINE")
        logger.info("="*80)

        start_time = datetime.now()

        # Step 1: Discovery
        logger.info("\n[STEP 1/5] URL Discovery")
        logger.info("-" * 80)
        discovered_urls = self.discoverer.discover_all()

        if not discovered_urls:
            logger.error("No URLs discovered. Exiting.")
            return

        self.save_discovered_urls(discovered_urls)

        # Step 2: Fetch & Extract
        logger.info(f"\n[STEP 2/5] Fetching & Extracting Content from {len(discovered_urls)} URLs")
        logger.info("-" * 80)
        extracted_articles = self.fetcher.batch_fetch(discovered_urls)

        if not extracted_articles:
            logger.error("No articles extracted. Exiting.")
            return

        logger.info(f"Successfully extracted {len(extracted_articles)} articles")

        # Step 3: Credibility Scoring
        logger.info(f"\n[STEP 3/5] Assessing Credibility")
        logger.info("-" * 80)

        credible_articles = []
        for article in extracted_articles:
            score, signals = self.credibility_scorer.score(article)

            # Add credibility data to article
            article["cred_score"] = score
            article.update({f"cred_{k}": v for k, v in signals.items()})

            # Filter by minimum score
            if self.credibility_scorer.should_keep(article, score):
                credible_articles.append(article)
            else:
                logger.debug(f"Filtered out low-credibility article: {article['url']} (score: {score})")

        logger.info(f"Kept {len(credible_articles)}/{len(extracted_articles)} articles after credibility filter")

        if not credible_articles:
            logger.error("No credible articles found. Exiting.")
            return

        # Step 4: NLP Analysis
        logger.info(f"\n[STEP 4/5] Running NLP Analysis")
        logger.info("-" * 80)

        analyzed_articles = []
        for i, article in enumerate(credible_articles, 1):
            logger.info(f"Analyzing {i}/{len(credible_articles)}: {article.get('title', 'Untitled')[:60]}...")

            try:
                nlp_results = self.nlp_analyzer.analyze(article)
                article.update(nlp_results)

                # Only keep articles on-topic
                if nlp_results["topic"] != "other":
                    # Generate unique ID
                    article["id"] = self.generate_article_id(article["url"])
                    analyzed_articles.append(article)
                else:
                    logger.debug(f"Filtered out off-topic article: {article['url']}")

            except Exception as e:
                logger.error(f"NLP analysis failed for {article['url']}: {e}")
                continue

        logger.info(f"Completed NLP analysis: {len(analyzed_articles)} on-topic articles")

        if not analyzed_articles:
            logger.error("No on-topic articles found. Exiting.")
            return

        # Step 5: Save Results
        logger.info(f"\n[STEP 5/5] Saving Results")
        logger.info("-" * 80)

        # Convert to DataFrame
        df = pd.DataFrame(analyzed_articles)

        # Select and order columns
        column_order = [
            "id", "url", "domain", "title", "author", "published_date",
            "topic", "language",
            "sentiment_score", "sentiment_label", "stance",
            "cred_score", "cred_domain_whitelisted", "cred_length_ok", "cred_https",
            "cred_has_byline", "cred_has_citations", "cred_indicator_count",
            "summary", "text_length", "discovery_source", "scraped_at"
        ]

        # Keep only existing columns
        final_columns = [col for col in column_order if col in df.columns]
        df = df[final_columns]

        # Save
        self.save_results(df)

        # Summary statistics
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        logger.info("\n" + "="*80)
        logger.info("PIPELINE COMPLETE - SUMMARY")
        logger.info("="*80)
        logger.info(f"Duration: {duration:.1f} seconds")
        logger.info(f"URLs discovered: {len(discovered_urls)}")
        logger.info(f"Articles extracted: {len(extracted_articles)}")
        logger.info(f"Articles passing credibility: {len(credible_articles)}")
        logger.info(f"Final articles saved: {len(analyzed_articles)}")
        logger.info("")
        logger.info("Topic breakdown:")
        logger.info(f"  Mining: {len(df[df['topic'] == 'mining'])}")
        logger.info(f"  Bitcoin/El Salvador: {len(df[df['topic'] == 'bitcoin_es'])}")
        logger.info(f"  Both: {len(df[df['topic'] == 'both'])}")
        logger.info("")
        logger.info("Sentiment breakdown:")
        logger.info(f"  Positive: {len(df[df['sentiment_label'] == 'positive'])}")
        logger.info(f"  Neutral: {len(df[df['sentiment_label'] == 'neutral'])}")
        logger.info(f"  Negative: {len(df[df['sentiment_label'] == 'negative'])}")
        logger.info("")
        logger.info("Stance breakdown:")
        logger.info(f"  Supportive: {len(df[df['stance'] == 'supportive'])}")
        logger.info(f"  Critical: {len(df[df['stance'] == 'critical'])}")
        logger.info(f"  Neutral: {len(df[df['stance'] == 'neutral'])}")
        logger.info("="*80)
        logger.info(f"Results saved to:")
        logger.info(f"  CSV: {self.csv_path}")
        logger.info(f"  Excel: {self.excel_path}")
        logger.info(f"  SQLite: {self.sqlite_path}")
        logger.info("="*80)

# For testing
if __name__ == "__main__":
    from src.utils import load_config, setup_logging

    config = load_config()
    setup_logging(config)

    pipeline = ScraperPipeline(config)
    pipeline.run()
