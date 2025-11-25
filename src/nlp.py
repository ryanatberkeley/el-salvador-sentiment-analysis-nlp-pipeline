"""
NLP analysis: language detection, sentiment, stance, topic classification
"""
import logging
import re
from langdetect import detect, LangDetectException

logger = logging.getLogger(__name__)

# Lazy loading of transformers models
_SENTIMENT_MODEL = None
_STANCE_MODEL = None

def get_sentiment_model():
    """Lazy load sentiment model"""
    global _SENTIMENT_MODEL
    if _SENTIMENT_MODEL is None:
        try:
            from transformers import pipeline
            logger.info("Loading sentiment analysis model...")
            # Use a fast, multilingual model
            _SENTIMENT_MODEL = pipeline(
                "sentiment-analysis",
                model="nlptown/bert-base-multilingual-uncased-sentiment",
                truncation=True
            )
            logger.info("Sentiment model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load sentiment model: {e}")
            _SENTIMENT_MODEL = None
    return _SENTIMENT_MODEL

def get_stance_model():
    """Lazy load zero-shot stance model"""
    global _STANCE_MODEL
    if _STANCE_MODEL is None:
        try:
            from transformers import pipeline
            logger.info("Loading stance detection model...")
            _STANCE_MODEL = pipeline(
                "zero-shot-classification",
                model="facebook/bart-large-mnli"
            )
            logger.info("Stance model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load stance model: {e}")
            _STANCE_MODEL = None
    return _STANCE_MODEL

class NLPAnalyzer:
    """Perform NLP analysis on article text"""

    def __init__(self, config):
        self.config = config.get("nlp", {})
        self.enable_sentiment = self.config.get("enable_sentiment", True)
        self.enable_stance = self.config.get("enable_stance", True)
        self.enable_summary = self.config.get("enable_summary", True)
        self.enable_language = self.config.get("enable_language_detection", True)

        # Text limits for performance
        self.max_text_sentiment = self.config.get("max_text_for_sentiment", 2000)
        self.max_text_stance = self.config.get("max_text_for_stance", 1500)
        self.max_text_summary = self.config.get("max_text_for_summary", 3000)

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
        Classify article topic based on keywords
        Returns: "mining", "bitcoin_es", "both", or "other"
        """
        combined = (title + " " + text[:2000]).lower()

        # Mining keywords
        mining_keywords = [
            "mining", "minería", "miner", "minero",
            "metal mining", "minería metálica",
            "gold mining", "copper mining", "oro", "cobre",
            "open-pit", "cielo abierto",
            "extraction", "extracción",
            "mineral", "ore", "mina",
            "environmental impact mining", "impacto ambiental minería",
            "mining pollution", "contaminación minera"
        ]

        # Bitcoin keywords
        bitcoin_keywords = [
            "bitcoin", "btc", "cryptocurrency", "criptomoneda",
            "bitcoin law", "ley bitcoin",
            "bitcoin adoption", "adopción bitcoin",
            "bitcoin beach", "chivo wallet",
            "el salvador bitcoin", "bukele bitcoin",
            "bitcoin economy", "economía bitcoin",
            "bitcoin remittance", "remesas bitcoin"
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
            # Default classification based on weaker signal
            if any(kw in combined for kw in ["mining", "minería", "mina"]):
                return "mining"
            elif any(kw in combined for kw in ["bitcoin", "btc", "criptomoneda"]):
                return "bitcoin_es"
            return "other"

    def analyze_sentiment(self, text):
        """
        Analyze sentiment using multilingual BERT
        Returns: (score, label) where score is -1 to 1
        """
        if not self.enable_sentiment or not text:
            return 0.0, "neutral"

        try:
            model = get_sentiment_model()
            if model is None:
                return 0.0, "neutral"

            # Truncate text
            text_sample = text[:self.max_text_sentiment]

            result = model(text_sample)[0]

            # Model outputs "1 star" to "5 stars"
            # Convert to -1 to 1 scale
            label = result["label"]
            stars = int(label.split()[0])  # Extract number from "3 stars"

            # Map 1-5 stars to -1 to 1
            score = (stars - 3) / 2.0  # 1->-1, 2->-0.5, 3->0, 4->0.5, 5->1

            # Label
            if score > 0.3:
                sentiment_label = "positive"
            elif score < -0.3:
                sentiment_label = "negative"
            else:
                sentiment_label = "neutral"

            return round(score, 3), sentiment_label

        except Exception as e:
            logger.error(f"Sentiment analysis failed: {e}")
            return 0.0, "neutral"

    def analyze_stance(self, text, topic):
        """
        Analyze stance toward topic using zero-shot classification
        Returns: "supportive", "critical", "neutral"
        """
        if not self.enable_stance or not text or topic == "other":
            return "neutral"

        try:
            model = get_stance_model()
            if model is None:
                return "neutral"

            # Truncate text
            text_sample = text[:self.max_text_stance]

            # Define stance labels based on topic
            if topic == "mining":
                labels = [
                    "supportive of metal mining",
                    "critical of metal mining",
                    "neutral about metal mining"
                ]
            elif topic == "bitcoin_es":
                labels = [
                    "supportive of Bitcoin in El Salvador",
                    "critical of Bitcoin in El Salvador",
                    "neutral about Bitcoin in El Salvador"
                ]
            else:  # both
                labels = [
                    "supportive",
                    "critical",
                    "neutral reporting"
                ]

            result = model(text_sample, labels)

            # Get top label
            top_label = result["labels"][0]
            confidence = result["scores"][0]

            # Map to simple stance
            if "supportive" in top_label and confidence > 0.4:
                return "supportive"
            elif "critical" in top_label and confidence > 0.4:
                return "critical"
            else:
                return "neutral"

        except Exception as e:
            logger.error(f"Stance analysis failed: {e}")
            return "neutral"

    def generate_summary(self, text):
        """
        Generate extractive summary (first 2 sentences + key excerpt)
        Simplified version without heavy summarization models
        """
        if not self.enable_summary or not text:
            return ""

        try:
            # Simple extractive summary: first 2-3 sentences
            sentences = re.split(r'[.!?]+', text[:self.max_text_summary])
            sentences = [s.strip() for s in sentences if len(s.strip()) > 20]

            if len(sentences) >= 2:
                summary = ". ".join(sentences[:2]) + "."
            elif len(sentences) == 1:
                summary = sentences[0] + "."
            else:
                summary = text[:300] + "..."

            # Limit to ~200 chars
            if len(summary) > 250:
                summary = summary[:247] + "..."

            return summary

        except Exception as e:
            logger.error(f"Summary generation failed: {e}")
            return text[:200] + "..."

    def analyze(self, article):
        """
        Run complete NLP analysis pipeline

        Args:
            article: dict with text, title, etc.

        Returns:
            dict with language, topic, sentiment, stance, summary
        """
        text = article.get("text", "")
        title = article.get("title", "")

        logger.debug(f"Running NLP analysis for: {title[:50]}...")

        # Language detection
        language = self.detect_language(text)

        # Topic classification
        topic = self.classify_topic(text, title)

        # Sentiment analysis
        sentiment_score, sentiment_label = self.analyze_sentiment(text)

        # Stance analysis
        stance = self.analyze_stance(text, topic)

        # Summary
        summary = self.generate_summary(text)

        results = {
            "language": language,
            "topic": topic,
            "sentiment_score": sentiment_score,
            "sentiment_label": sentiment_label,
            "stance": stance,
            "summary": summary
        }

        logger.debug(f"NLP results - Topic: {topic}, Sentiment: {sentiment_label}, Stance: {stance}")

        return results

# For testing
if __name__ == "__main__":
    from src.utils import load_config, setup_logging

    config = load_config()
    setup_logging(config)

    analyzer = NLPAnalyzer(config)

    test_article = {
        "title": "Bitcoin Adoption in El Salvador Shows Mixed Results",
        "text": """
        The adoption of Bitcoin as legal tender in El Salvador has produced mixed economic results
        according to recent reports from the IMF. While tourism to Bitcoin Beach has increased,
        overall cryptocurrency adoption among citizens remains low. The government's investment
        in Bitcoin has faced criticism due to market volatility.
        """ * 3
    }

    results = analyzer.analyze(test_article)
    print("\nNLP Analysis Results:")
    for key, value in results.items():
        print(f"  {key}: {value}")
