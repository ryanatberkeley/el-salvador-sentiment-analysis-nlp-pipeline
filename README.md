# Bitcoin & Mining in El Salvador - Web Scraper & Sentiment Analysis Pipeline

A comprehensive web scraping and NLP analysis pipeline for researching metal mining and Bitcoin's impact on El Salvador. This tool discovers, extracts, filters, and analyzes multilingual content from credible sources.

## Features

- **Multi-source Discovery**: SerpAPI (Google results) + RSS feeds
- **Robust Content Extraction**: Uses trafilatura for clean text extraction
- **Credibility Filtering**: Domain whitelisting, TLD checks, quality indicators
- **Multilingual NLP Analysis**:
  - Language detection (English/Spanish)
  - Topic classification (mining, Bitcoin, both)
  - Sentiment analysis (positive/neutral/negative)
  - Stance detection (supportive/critical/neutral)
  - Automatic summarization
- **Multiple Output Formats**: CSV, Excel, SQLite database
- **Comprehensive Logging**: Track every step of the pipeline

## Quick Start

### 1. Installation

```bash
# Clone or navigate to project directory
cd bitcoin-mining-pipeline

# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
# On macOS/Linux:
source .venv/bin/activate
# On Windows:
# .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration

**Set up your SerpAPI key:**

1. Get a free API key from [SerpAPI](https://serpapi.com/) (100 free searches/month)
2. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```
3. Edit `.env` and add your key:
   ```
   SERPAPI_KEY=your_actual_key_here
   ```

**Customize search queries** (optional):

Edit `config/settings.yml` to modify:
- Search queries
- RSS feeds
- Credibility thresholds
- NLP settings
- Output paths

### 3. Run the Scraper

```bash
python main.py
```

The pipeline will:
1. Discover URLs from search engines and RSS feeds
2. Fetch and extract content from each URL
3. Score credibility and filter low-quality sources
4. Perform NLP analysis (language, sentiment, stance, topic)
5. Save results to CSV, Excel, and SQLite

### 4. View Results

Results are saved to `data/processed/`:
- **articles.csv** - Easy to open in Excel/Google Sheets
- **articles.xlsx** - Excel format with proper formatting
- **mining_btc_esv.db** - SQLite database for queries

**Sample columns:**
- `url`, `domain`, `title`, `author`, `published_date`
- `topic` (mining, bitcoin_es, both)
- `language` (en, es, etc.)
- `sentiment_score` (-1 to 1), `sentiment_label` (positive/neutral/negative)
- `stance` (supportive/critical/neutral)
- `cred_score` (0-1 credibility score)
- `summary` (auto-generated summary)

## Project Structure

```
bitcoin-mining-pipeline/
├── config/
│   └── settings.yml          # All configuration settings
├── data/
│   ├── raw/                  # Discovered URLs (JSON)
│   └── processed/            # Output files (CSV, Excel, DB)
├── src/
│   ├── discover.py           # URL discovery (SerpAPI, RSS)
│   ├── fetch_extract.py      # Content fetching & extraction
│   ├── credibility.py        # Source credibility scoring
│   ├── nlp.py                # NLP analysis (sentiment, stance, etc.)
│   ├── pipeline.py           # Main orchestrator
│   └── utils.py              # Helper functions
├── main.py                   # Entry point
├── requirements.txt          # Python dependencies
├── .env                      # API keys (DO NOT COMMIT)
└── README.md                 # This file
```

## Configuration Guide

### Search Queries

Edit `config/settings.yml` under `search.queries`:

```yaml
search:
  queries:
    - "metal mining environmental impact El Salvador site:gov OR site:edu"
    - "Bitcoin adoption El Salvador IMF World Bank"
    - "minería metálica El Salvador contaminación"
```

### Credibility Settings

Adjust `credibility` section:

```yaml
credibility:
  whitelist_domains:
    - "reuters.com"
    - "worldbank.org"
    - "elfaro.net"
  min_article_len: 500        # Minimum characters
  min_score: 0.4              # Minimum credibility score (0-1)
```

### NLP Settings

Enable/disable features:

```yaml
nlp:
  enable_sentiment: true
  enable_stance: true
  enable_summary: true
  enable_language_detection: true
```

## Advanced Usage

### Running Individual Modules

Test each module separately:

```bash
# Test URL discovery
python -m src.discover

# Test content fetching
python -m src.fetch_extract

# Test credibility scoring
python -m src.credibility

# Test NLP analysis
python -m src.nlp
```

### Querying the Database

```python
import sqlite3
import pandas as pd

conn = sqlite3.connect("data/processed/mining_btc_esv.db")

# Get all positive sentiment articles
df = pd.read_sql("""
    SELECT title, url, sentiment_label, stance, cred_score
    FROM articles
    WHERE sentiment_label = 'positive'
    ORDER BY cred_score DESC
""", conn)

print(df)
```

### Filtering Results

```python
import pandas as pd

df = pd.read_csv("data/processed/articles.csv")

# High-credibility Bitcoin articles
bitcoin_articles = df[
    (df['topic'] == 'bitcoin_es') &
    (df['cred_score'] > 0.7)
]

# Critical stance toward mining
critical_mining = df[
    (df['topic'] == 'mining') &
    (df['stance'] == 'critical')
]
```

## Troubleshooting

### "SERPAPI_KEY not found"
- Make sure you created `.env` file
- Verify the key is correct (no quotes, no spaces)
- Get a free key at https://serpapi.com/

### "No articles extracted"
- Check your internet connection
- Try fewer/different search queries
- Lower `min_article_len` in settings.yml
- Check the log file at `data/scraper.log`

### NLP models not loading
- Ensure you have enough disk space (~2GB for models)
- First run downloads models automatically (may take time)
- Check internet connection for model downloads

### Low number of results
- Increase `results_per_query` in settings.yml
- Add more search queries
- Add more RSS feeds
- Lower `min_score` in credibility settings

## Performance Tips

1. **Limit searches for testing**: Reduce `results_per_query` to 10
2. **Disable heavy NLP**: Set `enable_stance: false` for faster runs
3. **Increase rate limiting**: Adjust `sleep_sec` to avoid getting blocked
4. **Use domain limits**: `max_per_domain` prevents over-scraping one site

## Ethics & Best Practices

- ✅ Respects rate limiting (2 sec between requests)
- ✅ Uses descriptive User-Agent
- ✅ Limits requests per domain
- ✅ Only scrapes publicly accessible content
- ✅ Focuses on credible, journalistic sources

**Please:**
- Do not lower `sleep_sec` below 1.0
- Do not increase `max_per_domain` above 10
- Do not scrape sites that explicitly forbid it
- Respect robots.txt (trafilatura handles this)

## Citation & License

This tool is for educational and research purposes. When using scraped content:
- Always cite original sources
- Respect copyright and terms of service
- Use for non-commercial research only

## Support

For issues, questions, or contributions:
- Check `data/scraper.log` for detailed error messages
- Review the configuration in `config/settings.yml`
- Ensure all dependencies are installed: `pip install -r requirements.txt`

## Example Output

```
╔══════════════════════════════════════════════════════════════════════════════╗
║     Bitcoin & Mining in El Salvador - Web Scraper & Sentiment Pipeline      ║
╚══════════════════════════════════════════════════════════════════════════════╝

PIPELINE COMPLETE - SUMMARY
================================================================================
Duration: 245.3 seconds
URLs discovered: 87
Articles extracted: 52
Articles passing credibility: 38
Final articles saved: 35

Topic breakdown:
  Mining: 12
  Bitcoin/El Salvador: 18
  Both: 5

Sentiment breakdown:
  Positive: 14
  Neutral: 16
  Negative: 5

Stance breakdown:
  Supportive: 11
  Critical: 8
  Neutral: 16
================================================================================
```

## What's Next?

- Add more credible sources to whitelist
- Customize search queries for your research focus
- Export results and analyze in Jupyter/R/Tableau
- Schedule regular runs with cron or Task Scheduler
- Build visualizations and reports from the data

Happy researching! 🔍📊
