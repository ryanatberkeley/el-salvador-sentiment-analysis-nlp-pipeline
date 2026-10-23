# Quick Start: El Salvador Mining & Bitcoin Scraper

This pipeline collects English and Spanish news coverage of metal mining and bitcoin in El Salvador. It then labels each article's sentiment toward both topics with OpenAI's GPT-6.1 Sol model. Results are saved as CSV, Excel, and SQLite files.

## Before you run anything

- **A full run costs money and takes several hours.** Run 1 (2016–2020) uses up to 1,075 SerpAPI searches, and run 2 (2020–2026) uses up to 1,505. The free SerpAPI plan (250 searches a month, 50 an hour) can't finish a run. OpenAI analysis costs about $18 per 1,000 articles.
- **Check with Ryan Ngo before starting a full run**, so the lab doesn't pay twice for the same data.
- **Keep API keys private.** They go in a `.env` file that git ignores. Never post them on GitHub or in group chats.

## What you need

- A Mac or Linux computer. Windows notes are at the end.
- Python 3.10 or newer. We've run the pipeline on Python 3.11. Check yours with `python3 --version`.
- Access to the `digital-ecologies-lab` GitHub organization. The repo is private.
- A SerpAPI key and an OpenAI API key.

## 1. Get the code

```bash
brew install gh        # skip if you already have the GitHub CLI
gh auth login          # sign in once; follow the browser prompt

git clone https://github.com/digital-ecologies-lab/sentiment-analysis.git
cd sentiment-analysis/scripts/el-salvador-sentiment-analysis-nlp-pipeline
```

Run every command below from this folder. In VS Code, use File → Open Folder and pick `el-salvador-sentiment-analysis-nlp-pipeline`.

## 2. Set up Python

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Your prompt now starts with `(.venv)`. Run `source .venv/bin/activate` in every new terminal before you use the pipeline. The install takes a few minutes, because `torch` is large.

## 3. Add your API keys

Run these four lines one at a time. Nothing appears on screen when you paste a key, so the key never shows in your terminal.

```bash
printf "Paste your SerpAPI key and press Enter: "; read -s SERP; echo
printf "Paste your OpenAI key and press Enter: "; read -s OAI; echo
printf 'SERPAPI_KEY=%s\nOPENAI_API_KEY=%s\n' "$SERP" "$OAI" > .env
unset SERP OAI
```

Check that both keys saved:

```bash
awk -F= '{print $1, length($2), "characters"}' .env
```

You should see both names, each with a number above zero.

## 4. Test the OpenAI connection

This costs less than a cent:

```bash
python -c "from src.utils import load_config; from src.nlp import NLPAnalyzer; print(NLPAnalyzer(load_config()).analyze_with_llm('El Salvador made bitcoin legal tender in 2021, and critics warned about price volatility. Metal mining was banned in 2017 over water pollution fears.'))"
```

A summary with `negative` sentiment labels means it works. The call can take 10–20 seconds. `Analysis failed` means you should check your key and your OpenAI credits.

## 5. Optional: a cheap test run

This searches only 2018, with 10 results per query: 43 searches, about half an hour, and under $1.

```bash
sed -i '' 's/^START_YEAR = .*/START_YEAR = 2018/; s/^END_YEAR = .*/END_YEAR = 2018/' src/discover.py
sed -i '' 's/results_per_query: .*/results_per_query: 10/' config/settings.yml
python main.py
```

Afterward, undo the test settings and move the test output aside:

```bash
git checkout -- src/discover.py config/settings.yml
mkdir -p data/test_run
mv data/processed/* data/raw/discovered_urls.json data/scraper.log data/test_run/
```

On Linux, write `sed -i` instead of `sed -i ''`.

## 6. Run 1: 2016–2020

Confirm the years:

```bash
grep -n -E "^START_YEAR|^END_YEAR" src/discover.py
```

It should show 2016 and 2020. Then start the run:

```bash
caffeinate -i python main.py
```

`caffeinate -i` keeps a Mac awake during the run. Near the top of the output you should see `Running 43 search queries across 5 date window(s), 2016-2020`. Leave the terminal open until `Pipeline completed successfully!` appears.

When it finishes, move the outputs into their own folder:

```bash
mkdir -p data/run1_2016-2020
mv data/processed/* data/raw/discovered_urls.json data/scraper.log data/run1_2016-2020/
```

## 7. Run 2: 2020–2026

```bash
sed -i '' 's/^START_YEAR = .*/START_YEAR = 2020/; s/^END_YEAR = .*/END_YEAR = 2026/' src/discover.py
grep -n -E "^START_YEAR|^END_YEAR" src/discover.py      # should show 2020 and 2026
caffeinate -i python main.py
```

When it finishes:

```bash
mkdir -p data/run2_2020-2026
mv data/processed/* data/raw/discovered_urls.json data/scraper.log data/run2_2020-2026/
git checkout -- src/discover.py      # sets the years back to 2016-2020
```

Both runs include 2020, so some 2020 articles appear in both. Remove duplicates by `url` when you combine the two.

## 8. Check a run

How many articles survived each step:

```bash
grep -E "SerpAPI requests sent|Discovery complete|Successfully extracted|from the Wayback|Credible articles|On-topic articles|Final articles saved" data/run1_2016-2020/scraper.log
```

Whether any model calls failed. You want `0`:

```bash
grep -c "OpenAI targeted analysis failed" data/run1_2016-2020/scraper.log
```

## Output columns

| Column | Meaning |
|---|---|
| `topic` | `mining`, `bitcoin_es`, or `both`, from the model's labels |
| `sentiment_metal_mining`, `sentiment_bitcoin` | `positive`, `negative`, `neutral`, or `not mentioned` |
| `specific_concerns` | Concerns the model found, separated by ` \| ` |
| `summary` | A 2–3 sentence summary from the model |
| `source_type` | `local` (Salvadoran outlet), `international`, or blank if unknown |
| `language` | Detected language of the article |
| `search_window` | The year searched when the article was found. Google's date filter is approximate. |
| `fetched_via` | `direct`, or `wayback` if the text came from the Wayback Machine |
| `cred_score` | Credibility score from 0 to 1. Articles below 0.3 are dropped. |
| `text` | Full extracted article text |

## How the pipeline works (for the methods section)

1. **Search.** 43 English and Spanish queries in `config/settings.yml` go through SerpAPI, one calendar year at a time, up to 50 results per query per year. Spanish queries search Salvadoran Google (`google.com.sv`, Spanish). English queries search US Google in English. Timed-out searches are retried up to 3 times.
2. **Download.** Each page is downloaded and its text extracted with trafilatura. If a site blocks the scraper, the link is dead, or no text comes out, the pipeline uses the earliest copy in the Wayback Machine.
3. **Credibility filter.** Articles scoring below 0.3 are dropped. The score combines trusted domains, length, HTTPS, bylines, citations, and transparency.
4. **Relevance screen.** An article must mention El Salvador and, as whole words, mining or bitcoin. Mentions of "bitcoin mining" don't count as metal mining.
5. **Model analysis.** GPT-6.1 Sol, with high reasoning effort, labels sentiment toward metal mining and toward bitcoin in El Salvador, lists concerns, and writes a summary. It reads up to 6,000 characters: the opening of the article plus any later paragraphs about mining or bitcoin.
6. **Topic.** Final topic labels come from the model. Articles it finds about neither topic are dropped.

## Troubleshooting

- **`No module named 'src'`:** You're in the wrong folder, or you ran a file directly. Run `python main.py` from the pipeline folder.
- **`No module named ...`:** Activate the environment with `source .venv/bin/activate`, then run `pip install -r requirements.txt`.
- **`SerpAPI rejected the API key`:** Check `SERPAPI_KEY` in `.env`.
- **`SerpAPI account is out of searches`:** Stop and get more searches. A run cut off partway misses the later queries, which include most of the bitcoin ones.
- **`Analysis failed` in summaries:** Check your OpenAI key, credits, and spending limit.
- **Searches are slow:** That's normal. SerpAPI can take 30–90 seconds on later result pages, and the pipeline retries instead of skipping them.
- **Stopping a run:** Press Control + C, not Command + C. Results are only saved at the end, so nothing is half-written.

## Windows

- Activate the environment with `.venv\Scripts\activate`.
- The `read -s`, `sed`, and `caffeinate` commands don't work. Create `.env` by hand in VS Code with the two lines `SERPAPI_KEY=...` and `OPENAI_API_KEY=...`. Edit `START_YEAR` and `END_YEAR` near the top of `src/discover.py` directly. Set your PC not to sleep during a run.
- Start a run with `python main.py`.
