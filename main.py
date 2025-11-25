#!/usr/bin/env python3
"""
Main entry point for the Bitcoin Mining El Salvador scraper pipeline

Usage:
    python main.py
"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.utils import load_config, setup_logging, get_env_variable
from src.pipeline import ScraperPipeline

def main():
    """Main execution function"""
    print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║     Bitcoin & Mining in El Salvador - Web Scraper & Sentiment Pipeline      ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
    """)

    try:
        # Load configuration
        print("Loading configuration...")
        config = load_config("config/settings.yml")

        # Setup logging
        logger = setup_logging(config)
        logger.info("Scraper pipeline starting...")

        # Check for API key
        api_key = get_env_variable("SERPAPI_KEY")
        if not api_key:
            print("\n" + "="*80)
            print("ERROR: SERPAPI_KEY not found!")
            print("="*80)
            print("\nPlease set your SerpAPI key:")
            print("  1. Copy .env.example to .env")
            print("  2. Add your SerpAPI key to .env")
            print("  3. Get a free key at: https://serpapi.com/")
            print("\nExample .env file:")
            print("  SERPAPI_KEY=your_key_here")
            print("="*80)
            return 1

        # Initialize and run pipeline
        pipeline = ScraperPipeline(config)
        pipeline.run()

        print("\n✓ Pipeline completed successfully!")
        print(f"\nResults saved to:")
        print(f"  • data/processed/articles.csv")
        print(f"  • data/processed/articles.xlsx")
        print(f"  • data/processed/mining_btc_esv.db")

        return 0

    except FileNotFoundError as e:
        print(f"\n✗ Error: {e}")
        print("Make sure config/settings.yml exists")
        return 1

    except ValueError as e:
        print(f"\n✗ Configuration error: {e}")
        return 1

    except KeyboardInterrupt:
        print("\n\n✗ Pipeline interrupted by user")
        return 1

    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
