#!/bin/bash

# Complete Watch System Deployment Script
# Deploys the entire watch scraping, AI enhancement, and search system

echo "🚀 DEPLOYING COMPLETE WATCH SYSTEM"
echo "=================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    print_error "Docker is not installed. Please install Docker first."
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null; then
    print_error "Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

print_status "Docker and Docker Compose are available"

# Create necessary directories
print_step "Creating necessary directories..."
mkdir -p logs chroma_watch_db data backups

# Set permissions
chmod 755 logs chroma_watch_db data backups
print_status "Directories created successfully"

# Copy requirements file
print_step "Setting up requirements..."
cp requirements.watch_system.txt requirements.txt
print_status "Requirements file updated"

# Stop any existing containers
print_step "Stopping existing containers..."
docker-compose -f docker-compose.watch_system.yml down --remove-orphans
print_status "Existing containers stopped"

# Build and start the complete system
print_step "Building and starting watch system..."
docker-compose -f docker-compose.watch_system.yml up --build -d

# Wait for services to start
print_status "Waiting for services to start..."
sleep 30

# Check service status
print_step "Checking service status..."

services=("whatsapp-bot" "watch-scraper" "watch-ai-enhancer" "watch-indexer" "watch-search-api")
all_healthy=true

for service in "${services[@]}"; do
    container_name="watch_${service//-/_}"
    if [ "$service" = "whatsapp-bot" ]; then
        container_name="watch_whatsapp_bot"
    fi
    
    if docker ps | grep -q "$container_name"; then
        print_status "$service is running ✅"
    else
        print_error "$service is not running ❌"
        all_healthy=false
    fi
done

# Test API endpoints
print_step "Testing API endpoints..."

# Test main bot health
if curl -f http://localhost:8000/health &>/dev/null; then
    print_status "WhatsApp Bot API is responding ✅"
else
    print_warning "WhatsApp Bot API is not responding ⚠️"
fi

# Test search API health
if curl -f http://localhost:8002/health &>/dev/null; then
    print_status "Watch Search API is responding ✅"
else
    print_warning "Watch Search API is not responding ⚠️"
fi

# Show logs for troubleshooting
if [ "$all_healthy" = false ]; then
    print_step "Showing logs for troubleshooting..."
    docker-compose -f docker-compose.watch_system.yml logs --tail=50
fi

# Show deployment summary
echo
echo "🎉 DEPLOYMENT SUMMARY"
echo "===================="

if [ "$all_healthy" = true ]; then
    print_status "✅ ALL SERVICES DEPLOYED SUCCESSFULLY!"
    echo
    echo "📱 WhatsApp Bot: http://localhost:8000"
    echo "🔍 Watch Search API: http://localhost:8002"
    echo "📊 System Status: http://localhost:8000/health"
    echo
    echo "🚀 SYSTEM FEATURES:"
    echo "   ✅ Smart watch-only scraping (runs 12 AM - 6 AM)"
    echo "   ✅ AI image enhancement with Google Gemini"
    echo "   ✅ Vector image search and indexing"
    echo "   ✅ Natural language watch search"
    echo "   ✅ WhatsApp chatbot integration"
    echo "   ✅ REST API for external integration"
    echo
    echo "📋 QUICK COMMANDS:"
    echo "   View logs: docker-compose -f docker-compose.watch_system.yml logs -f"
    echo "   Stop system: docker-compose -f docker-compose.watch_system.yml down"
    echo "   Restart: docker-compose -f docker-compose.watch_system.yml restart"
    echo
    print_status "System is ready for production use! 🎊"
else
    print_error "❌ SOME SERVICES FAILED TO START"
    print_warning "Check the logs above and fix any issues"
    echo
    echo "🔧 TROUBLESHOOTING:"
    echo "   1. Check logs: docker-compose -f docker-compose.watch_system.yml logs"
    echo "   2. Restart system: ./deploy_watch_system.sh"
    echo "   3. Check Docker resources: docker system df"
    echo "   4. Verify MongoDB connection"
fi

echo
echo "📚 NEXT STEPS:"
echo "   1. Test the scraper: Access container and run smart_watch_scraper.py"
echo "   2. Test AI enhancement: Run auto_ai_watch_enhancer.py"
echo "   3. Test search: Use the Watch Search API endpoints"
echo "   4. Monitor logs: Keep an eye on system performance"
echo
echo "🎯 The system will automatically:"
echo "   • Scrape watches daily (12 AM - 6 AM)"
echo "   • Enhance new watches with AI"
echo "   • Index images for search"
echo "   • Provide intelligent chatbot responses"