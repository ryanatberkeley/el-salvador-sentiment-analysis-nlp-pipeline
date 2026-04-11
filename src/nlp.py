"""
NLP analysis: language detection, topic classification, and targeted LLM sentiment/analysis
"""
import logging
import os
import json
import openai
from langdetect import detect, LangDetectException

logger = logging.getLogger(__name__)

class NLPAnalyzer:
    """Perform NLP analysis on article text using targeted LLM prompts"""

    def __init__(self, config):
        self.config = config.get("nlp", {})
        self.enable_language = self.config.get("enable_language_detection", True)
        self.max_text_llm = self.config.get("max_text_for_summary", 4000) # Increased slightly for full context

    def detect_language(self, text):
        """Detect language using langdetect"""
        if not self.enable_language or not text:
            return "unknown"

        try:
            lang = detect(text[:1000])  # Use first 1000 chars
            return lang
        except LangDetectException:
            logger.debug("Language detection failed")
            return "unknown"
        except Exception as e:
            logger.error(f"Unexpected error in language detection: {e}")
            return "unknown"

    def classify_topic(self, text, title=""):
        """
        Classify article topic based on keywords (Kept as a fast pre-filter)
        Returns: "mining", "bitcoin_es", "both", or "other"
        """
        combined = (title + " " + text[:2000]).lower()

        mining_keywords = [
            "mining", "minería", "miner", "minero", "metal mining", "minería metálica",
            "gold mining", "copper mining", "oro", "cobre", "open-pit", "cielo abierto",
            "extraction", "extracción", "mineral", "ore", "mina",
            "environmental impact mining", "impacto ambiental minería", "mining pollution"
        ]

        bitcoin_keywords = [
            "bitcoin", "btc", "cryptocurrency", "criptomoneda", "bitcoin law", "ley bitcoin",
            "bitcoin adoption", "adopción bitcoin", "bitcoin beach", "chivo wallet",
            "el salvador bitcoin", "bukele bitcoin", "bitcoin economy", "remesas bitcoin"
        ]

        has_mining = sum(1 for kw in mining_keywords if kw in combined) >= 2
        has_bitcoin = sum(1 for kw in bitcoin_keywords if kw in combined) >= 2

        if has_mining and has_bitcoin:
            return "both"
        elif has_mining:
            return "mining"
        elif has_bitcoin:
            return "bitcoin_es"
        else:
            if any(kw in combined for kw in ["mining", "minería", "mina"]):
                return "mining"
            elif any(kw in combined for kw in ["bitcoin", "btc", "criptomoneda"]):
                return "bitcoin_es"
            return "other"

    def analyze_with_llm(self, text):
        """
        Targeted LLM analysis for sentiment and specific concerns/harms.
        """
        # Default empty structure in case of failure
        default_result = {
            "summary": "Analysis failed or text too short.",
            "sentiment_metal_mining": "not mentioned",
            "sentiment_bitcoin": "not mentioned",
            "specific_concerns": ""
        }

        if not text:
            return default_result

        openai.api_key = os.getenv("OPENAI_API_KEY")
        if not openai.api_key:
            logger.error("No OpenAI API key found.")
            return default_result

        try:
            text_sample = text[:self.max_text_llm]
            
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
                model="gpt-3.5-turbo", # Consider "gpt-4o-mini" for better reasoning
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Article Text:\n\n{text_sample}"}
                ],
                max_tokens=300,
                response_format={ "type": "json_object" }
            )
            
            content = response.choices[0].message.content.strip()
            parsed_data = json.loads(content)
            
            # Format list into a comma-separated string for easier CSV/DB storage
            concerns_list = parsed_data.get("specific_concerns", [])
            if isinstance(concerns_list, list):
                parsed_data["specific_concerns"] = " | ".join(concerns_list)

            return parsed_data

        except Exception as e:
            logger.error(f"OpenAI targeted analysis failed: {e}")
            return default_result

    def analyze(self, article):
        """Run complete NLP analysis pipeline"""
        text = article.get("text", "")
        title = article.get("title", "")

        logger.debug(f"Running NLP analysis for: {title[:50]}...")

        # 1. Fast Pre-filters
        language = self.detect_language(text)
        topic = self.classify_topic(text, title)

        # 2. Targeted LLM Analysis
        llm_results = self.analyze_with_llm(text)

        results = {
            "language": language,
            "topic": topic,
            "sentiment_metal_mining": llm_results.get("sentiment_metal_mining", "not mentioned"),
            "sentiment_bitcoin": llm_results.get("sentiment_bitcoin", "not mentioned"),
            "specific_concerns": llm_results.get("specific_concerns", ""),
            "summary": llm_results.get("summary", "")
        }

        logger.debug(f"NLP results - Topic: {topic}, Mining Sentiment: {results['sentiment_metal_mining']}, Bitcoin Sentiment: {results['sentiment_bitcoin']}")
        return results