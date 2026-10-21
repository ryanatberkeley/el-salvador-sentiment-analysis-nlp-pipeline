"""
NLP analysis: language detection, relevance screening, and targeted LLM sentiment analysis
"""
import logging
import os
import re
import json
import openai
from langdetect import detect, LangDetectException

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Relevance screening. Every pattern matches whole words only: the old
# substring check matched "mina" inside "criminal" and "ore" inside "more".
# ---------------------------------------------------------------------------

# The article must be about El Salvador. "Salvador" alone isn't enough, because
# Google also returns pages about people named Salvador.
EL_SALVADOR_RE = re.compile(
    r"\bel\s+salvador\b|\bsan\s+salvador\b|\b(?:le|du|au)\s+salvador\b|"
    r"\bsalvadore(?:ñ|n)\w*|\bsalvadoran\w*|\bbukele\b",
    re.IGNORECASE,
)

MINING_RE = re.compile(
    r"\b(?:mining|miners?|miner[ií]a|mineros?|mineras?|minas?|mines?|"
    r"extractivismo|extractivism|oceanagold|pac\s+rim)\b",
    re.IGNORECASE,
)

BITCOIN_RE = re.compile(
    r"\b(?:bitcoins?|btc|cripto(?:monedas?|activos?)?|crypto(?:currenc(?:y|ies))?|"
    r"blockchain|chivo|volcano\s+bonds?|bonos?\s+volc[aá]n)\b",
    re.IGNORECASE,
)

# "Bitcoin mining" is about bitcoin, not metal mining. Removed before the
# mining check so it doesn't count as mining coverage.
CRYPTO_MINING_RE = re.compile(
    r"\b(?:bitcoins?|btc|crypto(?:currency)?|cripto(?:monedas?)?)[\s-]+(?:mining|miners?)\b"
    r"|\b(?:miner[ií]a|mineros?)\s+(?:de\s+)?(?:bitcoins?|btc|cripto\w*)\b"
    r"|\bmining\s+(?:bitcoins?|btc|crypto\w*)\b",
    re.IGNORECASE,
)

SENTIMENT_LABELS = {"positive", "negative", "neutral", "not mentioned"}


def _normalize_sentiment(value):
    value = str(value or "").strip().lower().replace("_", " ")
    if value in ("", "none", "n/a", "na", "not applicable", "not_mentioned"):
        return "not mentioned"
    return value


class NLPAnalyzer:
    """Perform NLP analysis on article text using targeted LLM prompts"""

    def __init__(self, config):
        self.config = config.get("nlp", {})
        self.enable_language = self.config.get("enable_language_detection", True)
        self.max_text_llm = self.config.get("max_text_for_summary", 6000)

    def detect_language(self, text):
        """Detect language using langdetect"""
        if not self.enable_language or not text:
            return "unknown"
        try:
            return detect(text[:1000])
        except LangDetectException:
            logger.debug("Language detection failed")
            return "unknown"
        except Exception as e:
            logger.error(f"Unexpected error in language detection: {e}")
            return "unknown"

    def classify_topic(self, text, title=""):
        """
        Keyword screen run before the LLM, so off-topic pages cost nothing.
        Returns "mining", "bitcoin_es", "both", or "other".
        """
        combined = f"{title}\n{text}"

        if not EL_SALVADOR_RE.search(combined):
            return "other"

        has_mining = bool(MINING_RE.search(CRYPTO_MINING_RE.sub(" ", combined)))
        has_bitcoin = bool(BITCOIN_RE.search(combined))

        if has_mining and has_bitcoin:
            return "both"
        if has_mining:
            return "mining"
        if has_bitcoin:
            return "bitcoin_es"
        return "other"

    def build_excerpt(self, text):
        """
        Text sent to the LLM, within max_text_for_summary characters. For long
        articles: the opening two-thirds of the budget, then any later paragraphs
        that mention mining or bitcoin, so a late mention isn't missed.
        """
        limit = self.max_text_llm
        if len(text) <= limit:
            return text

        head_len = (limit * 2) // 3
        budget = limit - head_len
        separator = "\n\n[...]\n\n"

        extras = []
        used = 0
        for paragraph in text[head_len:].split("\n"):
            paragraph = paragraph.strip()
            if not paragraph or not (MINING_RE.search(paragraph) or BITCOIN_RE.search(paragraph)):
                continue
            room = budget - used - len(separator)
            if room <= 0:
                break
            extras.append(paragraph[:room])
            used += len(separator) + len(extras[-1])

        if not extras:
            return text[:limit]
        return text[:head_len] + separator + separator.join(extras)

    def analyze_with_llm(self, text):
        """
        Targeted LLM analysis for sentiment and specific concerns/harms.
        "llm_ok" is False when the call failed, so failures aren't mistaken
        for "not mentioned".
        """
        default_result = {
            "summary": "Analysis failed or text too short.",
            "sentiment_metal_mining": "not mentioned",
            "sentiment_bitcoin": "not mentioned",
            "specific_concerns": "",
            "llm_ok": False,
        }

        if not text:
            return default_result

        openai.api_key = os.getenv("OPENAI_API_KEY")
        if not openai.api_key:
            logger.error("No OpenAI API key found.")
            return default_result

        try:
            text_sample = self.build_excerpt(text)

            system_prompt = """You are a highly analytical research assistant. Analyze the provided article text.
            You must respond in strictly valid JSON format matching the structure below.

            Analyze the sentiment specifically toward two defined objects:
            1. Metal Mining
            2. Bitcoin / Digital Transformations in El Salvador

            Identify if any specific concerns, harms, or negative narratives are present in the text (e.g., 'environmental degradation', 'market volatility', 'water pollution').

            Output JSON Format:
            {
                "summary": "A concise 2-3 sentence summary of the article.",
                "sentiment_metal_mining": "positive", "negative", "neutral", or "not mentioned",
                "sentiment_bitcoin": "positive", "negative", "neutral", or "not mentioned",
                "specific_concerns": ["list", "of", "concerns", "found"]
            }"""

            response = openai.chat.completions.create(
                model="gpt-6.1-sol",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Article Text:\n\n{text_sample}"},
                ],
                reasoning_effort="high",
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content.strip()
            parsed = json.loads(content)

            concerns = parsed.get("specific_concerns", [])
            if isinstance(concerns, list):
                concerns = " | ".join(str(c) for c in concerns)

            return {
                "summary": parsed.get("summary", ""),
                "sentiment_metal_mining": _normalize_sentiment(parsed.get("sentiment_metal_mining")),
                "sentiment_bitcoin": _normalize_sentiment(parsed.get("sentiment_bitcoin")),
                "specific_concerns": concerns or "",
                "llm_ok": True,
            }

        except Exception as e:
            logger.error(f"OpenAI targeted analysis failed: {e}")
            return default_result

    def analyze(self, article):
        """
        Run complete NLP analysis pipeline.

        1. Keyword screen: must mention El Salvador plus mining or bitcoin.
           Pages that fail are marked "other" and never sent to the LLM.
        2. LLM sentiment analysis.
        3. Final topic comes from the LLM's labels. If it says neither topic is
           discussed, the article is marked "other" and dropped by the pipeline.
        """
        text = article.get("text", "") or ""
        title = article.get("title", "") or ""

        language = self.detect_language(text)
        keyword_topic = self.classify_topic(text, title)

        if keyword_topic == "other":
            logger.info(f"  Off-topic, not sent to the LLM: {title[:60]}")
            return {
                "language": language,
                "topic": "other",
                "sentiment_metal_mining": "not mentioned",
                "sentiment_bitcoin": "not mentioned",
                "specific_concerns": "",
                "summary": "",
            }

        llm = self.analyze_with_llm(text)

        if llm["llm_ok"]:
            mining = llm["sentiment_metal_mining"] != "not mentioned"
            bitcoin = llm["sentiment_bitcoin"] != "not mentioned"
            if mining and bitcoin:
                topic = "both"
            elif mining:
                topic = "mining"
            elif bitcoin:
                topic = "bitcoin_es"
            else:
                topic = "other"
                logger.info(f"  LLM found neither topic, dropping: {title[:60]}")
        else:
            # Keep the article so a failed call shows up as "Analysis failed"
            # in the results instead of silently disappearing.
            topic = keyword_topic

        return {
            "language": language,
            "topic": topic,
            "sentiment_metal_mining": llm["sentiment_metal_mining"],
            "sentiment_bitcoin": llm["sentiment_bitcoin"],
            "specific_concerns": llm["specific_concerns"],
            "summary": llm["summary"],
        }