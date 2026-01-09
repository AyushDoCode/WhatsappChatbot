#!/bin/bash

################################################################################
# Cleanup Script - Remove Old WhatsApp Bot Data
# 
# This script safely removes:
# - Old temp images
# - Old logs (archived with timestamp)
# - Old container data
# - Old Docker volumes (optional)
#
# PRESERVES:
# - Evolution API
# - Redis
# - Postgres
# - MongoDB data (unless --full flag is used)
################################################################################

set -e

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║     CLEANUP OLD WHATSAPP BOT DATA                            ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# Check for --full flag
FULL_CLEANUP=false
if [ "$1" = "--full" ]; then
    FULL_CLEANUP=true
    echo -e "${RED}⚠️  FULL CLEANUP MODE - Will remove MongoDB data too!${NC}"
    echo ""
    read -p "Are you sure? This will delete all products and conversations! (yes/no): " confirm
    if [ "$confirm" != "yes" ]; then
        echo -e "${YELLOW}Cleanup cancelled${NC}"
        exit 0
    fi
fi

echo -e "${CYAN}🗑️  Step 1: Stopping WatchVine containers${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Stop only WatchVine containers (preserve Evolution, Redis, Postgres)
echo -e "${YELLOW}Stopping containers...${NC}"
docker stop watchvine_main_app 2>/dev/null || echo "  main_app not running"
docker stop watchvine_text_search 2>/dev/null || echo "  text_search not running"
docker stop watchvine_image_identifier 2>/dev/null || echo "  image_identifier not running"

if [ "$FULL_CLEANUP" = true ]; then
    docker stop watchvine_mongodb 2>/dev/null || echo "  mongodb not running"
fi

echo -e "${GREEN}✅ Containers stopped${NC}"
echo ""

echo -e "${CYAN}🗑️  Step 2: Removing containers${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

docker rm watchvine_main_app 2>/dev/null || echo "  main_app not found"
docker rm watchvine_text_search 2>/dev/null || echo "  text_search not found"
docker rm watchvine_image_identifier 2>/dev/null || echo "  image_identifier not found"

if [ "$FULL_CLEANUP" = true ]; then
    docker rm watchvine_mongodb 2>/dev/null || echo "  mongodb not found"
fi

echo -e "${GREEN}✅ Containers removed${NC}"
echo ""

echo -e "${CYAN}🗑️  Step 3: Cleaning temp images${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ -d "temp_images" ]; then
    IMAGE_COUNT=$(find temp_images -type f | wc -l)
    echo -e "${YELLOW}Found ${IMAGE_COUNT} images in temp_images/${NC}"
    
    if [ "$IMAGE_COUNT" -gt 0 ]; then
        rm -rf temp_images/*
        echo -e "${GREEN}✅ ${IMAGE_COUNT} images deleted${NC}"
    else
        echo -e "${CYAN}No images to clean${NC}"
    fi
else
    mkdir -p temp_images
    echo -e "${GREEN}✅ Created temp_images folder${NC}"
fi
echo ""

echo -e "${CYAN}🗑️  Step 4: Archiving old logs${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)

if [ -d "logs" ]; then
    # Create archive directory
    mkdir -p logs/archive
    
    # Archive main logs
    if [ -f "logs/main.log" ]; then
        mv logs/main.log logs/archive/main.log.$TIMESTAMP
        echo -e "${GREEN}✅ Archived main.log${NC}"
    fi
    
    if [ -f "logs/main.err.log" ]; then
        mv logs/main.err.log logs/archive/main.err.log.$TIMESTAMP
        echo -e "${GREEN}✅ Archived main.err.log${NC}"
    fi
    
    # Archive API logs
    if [ -f "logs/text_search_api.log" ]; then
        mv logs/text_search_api.log logs/archive/text_search_api.log.$TIMESTAMP
        echo -e "${GREEN}✅ Archived text_search_api.log${NC}"
    fi
    
    if [ -f "logs/image_identifier_api.log" ]; then
        mv logs/image_identifier_api.log logs/archive/image_identifier_api.log.$TIMESTAMP
        echo -e "${GREEN}✅ Archived image_identifier_api.log${NC}"
    fi
    
    # Clean old archives (keep last 5)
    OLD_ARCHIVES=$(ls -t logs/archive/*.log.* 2>/dev/null | tail -n +6)
    if [ ! -z "$OLD_ARCHIVES" ]; then
        echo "$OLD_ARCHIVES" | xargs rm -f
        echo -e "${GREEN}✅ Cleaned old log archives${NC}"
    fi
else
    mkdir -p logs
    echo -e "${GREEN}✅ Created logs folder${NC}"
fi
echo ""

echo -e "${CYAN}🗑️  Step 5: Removing old Docker volumes${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Remove shared index volume (will be recreated with new index)
if docker volume ls | grep -q "whatsappbot_shared_index"; then
    docker volume rm whatsappbot_shared_index 2>/dev/null && echo -e "${GREEN}✅ Removed shared_index volume${NC}" || echo -e "${YELLOW}⚠️  Could not remove shared_index (may be in use)${NC}"
fi

if [ "$FULL_CLEANUP" = true ]; then
    echo -e "${RED}Removing MongoDB volumes...${NC}"
    docker volume rm whatsappbot_mongodb_data 2>/dev/null && echo -e "${GREEN}✅ Removed mongodb_data${NC}" || true
    docker volume rm whatsappbot_mongodb_config 2>/dev/null && echo -e "${GREEN}✅ Removed mongodb_config${NC}" || true
fi
echo ""

echo -e "${CYAN}🗑️  Step 6: Cleaning Docker system${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo -e "${YELLOW}Removing unused Docker images...${NC}"
docker image prune -f

echo -e "${YELLOW}Removing dangling volumes...${NC}"
docker volume prune -f

echo -e "${GREEN}✅ Docker system cleaned${NC}"
echo ""

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║     CLEANUP COMPLETE!                                        ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

echo -e "${GREEN}✅ Summary:${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  • Old containers: Removed"
echo "  • Temp images: Cleaned"
echo "  • Logs: Archived with timestamp"
echo "  • Docker volumes: Cleaned"
if [ "$FULL_CLEANUP" = true ]; then
    echo "  • MongoDB data: REMOVED (full cleanup)"
else
    echo "  • MongoDB data: Preserved"
fi
echo ""

echo -e "${CYAN}✅ PRESERVED (Not touched):${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
docker ps --format "table {{.Names}}\t{{.Status}}" | grep -E "evolution|redis|postgres" || echo "  No Evolution/Redis/Postgres containers found"
echo ""

echo -e "${GREEN}🎉 Ready for fresh deployment!${NC}"
echo ""
echo -e "${CYAN}Next Steps:${NC}"
echo "  1. Run deployment script: bash deploy_production.sh"
echo "  2. Wait for indexer to complete (~2-3 hours)"
echo "  3. Test your bot"
echo ""
