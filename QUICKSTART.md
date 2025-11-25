# Quick Start Guide - 5 Minutes to First Results

## Step 1: Install Dependencies (2 min)

```bash
# Create virtual environment
python3 -m venv .venv

# Activate it
source .venv/bin/activate  # macOS/Linux
# OR
.venv\Scripts\activate     # Windows

# Install packages
pip install -r requirements.txt
```

## Step 2: Get SerpAPI Key (2 min)

1. Go to https://serpapi.com/users/sign_up
2. Sign up for free account (100 searches/month free)
3. Copy your API key from the dashboard

## Step 3: Configure (1 min)

```bash
# Copy example env file
cp .env.example .env

# Edit .env and paste your key
# Change this line:
SERPAPI_KEY=your_serpapi_key_here
# To:
SERPAPI_KEY=abc123your_actual_key_here
```

## Step 4: Run! (5-10 min)

```bash
python main.py
```

That's it! The scraper will:
- Search Google for Bitcoin & mining articles about El Salvador
- Extract content from ~50 credible sources
- Analyze sentiment, stance, and topics
- Save results to CSV, Excel, and SQLite

## Step 5: View Results

Open these files:
- `data/processed/articles.csv` - Import into Excel/Google Sheets
- `data/processed/articles.xlsx` - Already in Excel format
- `data/scraper.log` - Detailed logs

## Common First-Run Issues

**"SERPAPI_KEY not found"**
- Did you create the `.env` file?
- Is your key in the file without quotes?

**"No module named 'transformers'"**
- Did you activate the virtual environment?
- Run `pip install -r requirements.txt` again

**"No articles found"**
- First run downloads AI models (~1-2 GB)
- Check internet connection
- Check `data/scraper.log` for details

## Next Steps

1. **Customize searches**: Edit `config/settings.yml` → `search.queries`
2. **Adjust filters**: Change `credibility.min_score` (lower = more results)
3. **Add sources**: Add trusted domains to `credibility.whitelist_domains`

## Quick Test Run

For a faster test (2-3 min), edit `config/settings.yml`:

```yaml
search:
  results_per_query: 5  # Instead of 20

crawl:
  max_per_domain: 2     # Instead of 5
```

Then run `python main.py`

---

**Need help?** Check [README.md](README.md) for full documentation or review `data/scraper.log` for error details.
