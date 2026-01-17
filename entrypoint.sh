#!/bin/bash
set -e

echo "========================================"
echo "  WATCHVINE ENTRYPOINT"
echo "========================================"

# Wait for MongoDB to be ready
echo "⏳ Waiting for MongoDB to be ready..."
max_retries=30
retry_count=0

while [ $retry_count -lt $max_retries ]; do
    if python -c "from pymongo import MongoClient; client = MongoClient('$MONGO_URI', serverSelectionTimeoutMS=2000); client.admin.command('ping'); print('MongoDB connected')" 2>/dev/null; then
        echo "✅ MongoDB is ready!"
        break
    fi
    retry_count=$((retry_count + 1))
    echo "  Attempt $retry_count/$max_retries - MongoDB not ready yet..."
    sleep 2
done

if [ $retry_count -eq $max_retries ]; then
    echo "❌ Failed to connect to MongoDB after $max_retries attempts"
    exit 1
fi

# Check if this is first run (no index file exists)
if [ ! -f "/app/vector_index.bin" ]; then
    echo ""
    echo "🆕 First run detected (index missing)! Running initial data setup..."
    echo "========================================"
    
    # Run scraper to fetch all products
    echo ""
    echo "📥 STEP 1: Scraping ALL products from website..."
    # Args: limit=all, clear_db=true, workers=5
    python fast_scraper.py all true 5
    
    # Run indexer to create vector index
    echo ""
    echo "🔨 STEP 2: Creating vector index..."
    python indexer.py
    
    echo ""
    echo "✅ Initial data setup completed!"
    echo "========================================"
else
    echo ""
    echo "✅ Vector index found. Skipping initial data setup."
fi

# Start all services with supervisord
echo ""
echo "🚀 Starting all services via Supervisor..."
echo "  - Main Flask App (Port 5000)"
echo "  - Text Search API (Port 8001)"
echo "  - Image Identifier API (Port 8002)"
echo "  - Nightly Scraper Scheduler"
echo "========================================"

exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
