"""
Utility functions for logging, configuration, and helpers
"""
import logging
import yaml
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def setup_logging(config):
    """Setup logging configuration"""
    log_level = getattr(logging, config.get("logging", {}).get("level", "INFO"))
    log_file = config.get("logging", {}).get("file", "data/scraper.log")

    # Create logs directory if needed
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)

    # Configure logging
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )

    return logging.getLogger(__name__)

def load_config(config_path="config/settings.yml"):
    """Load configuration from YAML file"""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        return config
    except FileNotFoundError:
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    except yaml.YAMLError as e:
        raise ValueError(f"Error parsing YAML configuration: {e}")

def get_env_variable(var_name, default=None, required=False):
    """Get environment variable with error handling"""
    value = os.getenv(var_name, default)
    if required and not value:
        raise ValueError(f"Required environment variable {var_name} is not set")
    return value

def safe_filename(text, max_len=100):
    """Convert text to safe filename"""
    import re
    # Remove invalid characters
    safe = re.sub(r'[^\w\s-]', '', text)
    safe = re.sub(r'[-\s]+', '-', safe)
    return safe[:max_len].strip('-')

def truncate_text(text, max_length):
    """Safely truncate text to max length"""
    if not text:
        return ""
    return text[:max_length] if len(text) > max_length else text
