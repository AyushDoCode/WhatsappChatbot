"""
Initial Setup Script
Runs on first startup to scrape products and create vector index
"""

import os
import sys
import logging
from pymongo import MongoClient
import subprocess

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def check_database_needs_scraping():
    """Check if products database needs scraping (less than 10 products)"""
    try:
        MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
        DB_NAME = os.getenv("DATABASE_NAME", "watchvine_refined")
        COLLECTION_NAME = os.getenv("COLLECTION_NAME", "products")
        
        client = MongoClient(MONGO_URI)
        db = client[DB_NAME]
        collection = db[COLLECTION_NAME]
        
        count = collection.count_documents({})
        logger.info(f"📊 Database has {count} products")
        
        # Need scraping if less than 10 products
        needs_scraping = count < 10
        
        if needs_scraping:
            logger.warning(f"⚠️ Database has only {count} products (minimum: 10) - scraping needed!")
        else:
            logger.info(f"✅ Database has sufficient products ({count} >= 10)")
        
        return needs_scraping
    except Exception as e:
        logger.error(f"❌ Error checking database: {e}")
        return True  # If error, assume scraping is needed

def check_index_exists():
    """Check if vector index file exists"""
    index_file = "/app/vector_index.bin"
    metadata_file = "/app/metadata.pkl"
    
    exists = os.path.exists(index_file) and os.path.exists(metadata_file)
    logger.info(f"📂 Vector index exists: {exists}")
    
    return exists

def run_scraper():
    """Run the OPTIMIZED fast scraper to populate database"""
    logger.info("=" * 70)
    logger.info("🚀 STARTING PRODUCT SCRAPING...")
    logger.info("⚙️  Using optimized settings: 5 workers, 0.5-1s delays")
    logger.info("⏱️  Expected duration: ~30-60 minutes for all products")
    logger.info("=" * 70)
    
    try:
        # Run fast_scraper.py with OPTIMIZED settings (5 workers instead of 10)
        # Using Popen to stream output in real-time
        import sys
        
        # NEVER clear DB during auto-init if we already pointed to user's DB
        process = subprocess.Popen(
            ["python", "-u", "fast_scraper.py", "all", "false", "5"],
            cwd="/app",
            stdout=sys.stdout,  # Stream directly to console
            stderr=sys.stderr,
            text=True,
            bufsize=1  # Line buffered
        )
        
        # Wait for completion
        return_code = process.wait(timeout=7200)
        result = type('obj', (object,), {'returncode': return_code})()  # Create simple object
        
        if result.returncode == 0:
            logger.info("✅ Scraping completed successfully!")
            return True
        else:
            logger.error(f"❌ Scraping failed with return code: {result.returncode}")
            return False
            
    except subprocess.TimeoutExpired:
        logger.error("❌ Scraping timeout (>2 hours)")
        try:
            process.kill()
        except:
            pass
        return False
    except Exception as e:
        logger.error(f"❌ Scraping error: {e}")
        return False

def run_indexer():
    """Run the indexer to create vector index"""
    logger.info("=" * 70)
    logger.info("🔨 CREATING VECTOR INDEX...")
    logger.info("⏱️  This may take 10-20 minutes depending on product count")
    logger.info("💾 Memory required: ~2-3 GB")
    logger.info("=" * 70)
    
    try:
        # Run indexer.py with live output streaming
        import sys
        
        process = subprocess.Popen(
            ["python", "-u", "indexer.py"],
            cwd="/app",
            stdout=sys.stdout,  # Stream directly to console
            stderr=sys.stderr,
            text=True,
            bufsize=1  # Line buffered
        )
        
        # Wait for completion
        return_code = process.wait(timeout=3600)
        result = type('obj', (object,), {'returncode': return_code})()  # Create simple object
        
        if result.returncode == 0:
            logger.info("✅ Indexing completed successfully!")
            return True
        else:
            logger.error(f"❌ Indexing failed with return code: {result.returncode}")
            logger.error("💡 Possible reasons:")
            logger.error("   - Not enough memory (indexer needs ~2-3 GB)")
            logger.error("   - Model download timeout")
            logger.error("   - Too many products to index")
            return False
            
    except subprocess.TimeoutExpired:
        logger.error("❌ Indexing timeout (>60 minutes)")
        logger.error("💡 Indexer is taking too long. This usually means:")
        logger.error("   - Too many products (>5000)")
        logger.error("   - Server has low memory")
        logger.error("   - Network is slow (downloading embedding model)")
        try:
            process.kill()
        except:
            pass
        return False
    except Exception as e:
        logger.error(f"❌ Indexing error: {e}")
        return False

def main():
    """Main initialization logic - checks if scraping/indexing needed"""
    logger.info("=" * 70)
    logger.info("🔍 CHECKING DATABASE AND INDEX STATUS...")
    logger.info("=" * 70)
    
    # Check if database needs scraping (< 10 products)
    needs_scraping = check_database_needs_scraping()
    
    # Check if index exists
    index_exists = check_index_exists()
    
    # If database has enough products AND index exists, we're good
    if not needs_scraping and index_exists:
        logger.info("✅ Database has sufficient products and index exists")
        logger.info("✅ No setup needed - skipping scraping and indexing")
        logger.info("=" * 70)
        return True
    
    # If database needs scraping (< 10 products)
    if needs_scraping:
        logger.info("⚠️ Database has less than 10 products - scraping needed")
        logger.info("🕷️  Starting scraper to fetch ALL products...")
        
        # Run scraper
        if not run_scraper():
            logger.error("❌ Failed to scrape products")
            return False
        
        logger.info("✅ Products scraped successfully!")
        
        # After scraping, we MUST rebuild index
        logger.info("🔨 Data changed - rebuilding vector index...")
        if not run_indexer():
            logger.error("❌ Failed to create index after scraping")
            return False
        
        logger.info("✅ Vector index created successfully!")
    
    # If database is fine but index doesn't exist
    elif not index_exists:
        logger.info("⚠️ Database has products but vector index missing")
        logger.info("🔨 Creating vector index from existing data...")
        
        # Run indexer
        if not run_indexer():
            logger.error("❌ Failed to create index")
            return False
        
        logger.info("✅ Vector index created successfully!")
    
    logger.info("=" * 70)
    logger.info("🎉 SETUP COMPLETED SUCCESSFULLY!")
    logger.info("=" * 70)
    
    return True

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        logger.info("\n⚠️ Setup interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        sys.exit(1)
