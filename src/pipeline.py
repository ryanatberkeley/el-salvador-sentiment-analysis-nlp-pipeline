"""
Main ETL pipeline orchestrator
"""
import logging
import hashlib
import json
from pathlib import Path
from datetime import datetime
import pandas as pd
import numpy as np

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
        return hashlib.sha256(url.encode()).hexdigest()[:16]

    def classify_source_type(self, domain):
        """
        Heuristic-based classification of domains into 'local' vs 'international'.
        Returns np.nan if the classification is unsure/unknown.
        """
        if not domain:
            return np.nan
            
        domain = domain.lower()
        
        # 1. El Salvador top-level domain
        if domain.endswith(".sv"):
            return "local"
            
        # 2. Known local El Salvador news outlets
        local_outlets = [
            "elsalvador.com", "laprensagrafica.com", "elfaro.net",
            "diario.elmundo.sv", "gatoencerrado.news", "revistafactum.com",
            "diarioelsalvador.com", "lanoticiasv.com", "contrapunto.com.sv"
        ]
        
        if any(outlet in domain for outlet in local_outlets):
            return "local"
            
        # 3. Known international and global crypto outlets
        international_outlets = [
            "reuters.com", "apnews.com", "bbc.com", "bbc.co.uk",
            "nytimes.com", "washingtonpost.com", "wsj.com",
            "bloomberg.com", "ft.com", "theguardian.com",
            "aljazeera.com", "cnn.com", "cnbc.com", "foxnews.com",
            "elpais.com", "elmundo.es", "coindesk.com", "cointelegraph.com",
            "decrypt.co", "bitcoinmagazine.com", "yahoo.com", "msn.com"
        ]
        
        if any(outlet in domain for outlet in international_outlets):
            return "international"
            
        # 4. If it matches neither list, we are unsure. 
        return np.nan

    def save_discovered_urls(self, urls):
        output_path = Path("data/raw/discovered_urls.json")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(urls, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved {len(urls)} discovered URLs to {output_path}")

    def save_results(self, articles_df):
        if articles_df.empty:
            logger.warning("No articles to save")
            return

        Path(self.csv_path).parent.mkdir(parents=True, exist_ok=True)
        articles_df["scraped_at"] = datetime.now().isoformat()

        articles_df.to_csv(self.csv_path, index=False, encoding='utf-8')
        logger.info(f"Saved {len(articles_df)} articles to CSV: {self.csv_path}")

        try:
            articles_df.to_excel(self.excel_path, index=False, engine='openpyxl')
            logger.info(f"Saved {len(articles_df)} articles to Excel: {self.excel_path}")
        except Exception as e:
            logger.warning(f"Could not save Excel file: {e}")

        try:
            import sqlite3
            conn = sqlite3.connect(self.sqlite_path)
            existing_df = pd.DataFrame()
            try:
                existing_df = pd.read_sql("SELECT * FROM articles", conn)
                logger.info(f"Found {len(existing_df)} existing articles in database")
            except:
                logger.info("Creating new articles table")

            if not existing_df.empty:
                combined_df = pd.concat([existing_df, articles_df], ignore_index=True)
                combined_df = combined_df.drop_duplicates(subset=['id'], keep='last')
                logger.info(f"Merged data: {len(combined_df)} total articles")
            else:
                combined_df = articles_df

            combined_df.to_sql("articles", conn, if_exists="replace", index=False)
            conn.close()
            logger.info(f"Saved to SQLite: {self.sqlite_path}")

        except Exception as e:
            logger.error(f"Failed to save to SQLite: {e}")

    def run(self):
        logger.info("="*80)
        logger.info("STARTING SCRAPER PIPELINE")
        logger.info("="*80)

        start_time = datetime.now()

        # Step 1: Discovery
        logger.info("\n[STEP 1/5] URL Discovery")
        discovered_urls = self.discoverer.discover_all()
        if not discovered_urls:
            logger.error("No URLs discovered. Exiting.")
            return
        self.save_discovered_urls(discovered_urls)

        # Step 2: Fetch & Extract
        logger.info(f"\n[STEP 2/5] Fetching & Extracting Content")
        extracted_articles = self.fetcher.batch_fetch(discovered_urls)
        if not extracted_articles:
            logger.error("No articles extracted. Exiting.")
            return

        # Step 3: Credibility Scoring
        logger.info(f"\n[STEP 3/5] Assessing Credibility")
        credible_articles = []
        for article in extracted_articles:
            score, signals = self.credibility_scorer.score(article)
            article["cred_score"] = score
            article.update({f"cred_{k}": v for k, v in signals.items()})

            if self.credibility_scorer.should_keep(article, score):
                credible_articles.append(article)

        logger.info(f"Credible articles: {len(credible_articles)} of {len(extracted_articles)}")

        if not credible_articles:
            logger.error("No credible articles found. Exiting.")
            return

        # Step 4: NLP Analysis & Source Classification
        logger.info(f"\n[STEP 4/5] Running Targeted LLM Analysis & Source Classification")
        analyzed_articles = []
        for i, article in enumerate(credible_articles, 1):
            logger.info(f"Analyzing {i}/{len(credible_articles)}: {article.get('title', 'Untitled')[:60]}...")
            try:
                # Apply NLP
                nlp_results = self.nlp_analyzer.analyze(article)
                article.update(nlp_results)

                # Classify Source (Local vs International vs NaN)
                article["source_type"] = self.classify_source_type(article.get("domain", ""))

                if nlp_results["topic"] != "other":
                    article["id"] = self.generate_article_id(article["url"])
                    analyzed_articles.append(article)
            except Exception as e:
                logger.error(f"NLP analysis failed for {article['url']}: {e}")
                continue

        logger.info(f"On-topic articles: {len(analyzed_articles)} of {len(credible_articles)}")

        if not analyzed_articles:
            logger.error("No on-topic articles found. Exiting.")
            return

        # Step 5: Save Results
        logger.info(f"\n[STEP 5/5] Saving Results")
        df = pd.DataFrame(analyzed_articles)

        # Updated column order based on new LLM outputs & Source Type
        column_order = [
            "id", "url", "domain", "source_type", "title", "author", "published_date",
            "topic", "language",
            "sentiment_metal_mining", "sentiment_bitcoin", "specific_concerns",
            "cred_score", "cred_domain_whitelisted", "cred_length_ok", "cred_https",
            "cred_has_byline", "cred_has_citations", "cred_indicator_count",
            "summary", "text", "text_length", "discovery_source",
            "search_query", "search_window", "fetched_via", "scraped_at"
        ]

        final_columns = [col for col in column_order if col in df.columns]
        df = df[final_columns]
        
        # Save to DB/CSV
        self.save_results(df)

        # ---------------------------------------------------------
        # Automated Grouping and Sentiment Comparison
        # ---------------------------------------------------------
        logger.info("\n" + "="*80)
        logger.info("ANALYTICAL BREAKDOWN: TOPIC x SOURCE TYPE")
        logger.info("="*80)
        
        # Convert string sentiments into numeric scores for easy averaging
        sentiment_map = {"positive": 1, "neutral": 0, "negative": -1, "not mentioned": np.nan}
        df["mining_score"] = df["sentiment_metal_mining"].map(sentiment_map)
        df["bitcoin_score"] = df["sentiment_bitcoin"].map(sentiment_map)

        # Group by Topic and then Source Type
        # dropna=False keeps articles whose source type is unknown in the table
        grouped = df.groupby(["topic", "source_type"], dropna=False).agg(
            article_count=("id", "count"),
            avg_mining_sentiment=("mining_score", "mean"),
            avg_bitcoin_sentiment=("bitcoin_score", "mean")
        ).reset_index()

        # Print out the analytical comparison
        print(grouped.to_string(index=False))

        # Final Summary
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        logger.info("\n" + "="*80)
        logger.info("PIPELINE COMPLETE - SUMMARY")
        logger.info("="*80)
        logger.info(f"Duration: {duration:.1f} seconds")
        logger.info(f"Final articles saved: {len(analyzed_articles)}")
        logger.info("="*80)

if __name__ == "__main__":
    from src.utils import load_config, setup_logging
    config = load_config()
    setup_logging(config)
    pipeline = ScraperPipeline(config)
    pipeline.run()