#!/bin/bash

################################################################################
# QUICK DEPLOYMENT SCRIPT - Copy Files to Docker Container
################################################################################

# Color codes for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}================================${NC}"
echo -e "${BLUE}WatchVine Docker Deployment${NC}"
echo -e "${BLUE}================================${NC}\n"

# Step 1: Ask for container ID
echo -e "${YELLOW}Step 1: Find your container ID${NC}"
echo "Run this command to list containers:"
echo -e "${BLUE}docker ps${NC}\n"

read -p "Enter your Container ID (or press Enter to list): " CONTAINER_ID

if [ -z "$CONTAINER_ID" ]; then
    echo -e "${YELLOW}Listing Docker containers:${NC}"
    docker ps
    echo ""
    read -p "Enter your Container ID: " CONTAINER_ID
fi

if [ -z "$CONTAINER_ID" ]; then
    echo -e "${RED}❌ No container ID provided. Exiting.${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Using Container ID: $CONTAINER_ID${NC}\n"

# Step 2: Copy files
echo -e "${YELLOW}Step 2: Copying files to container...${NC}"

files=(
    "system_prompt_config.py"
    "backend_tool_classifier.py"
    "text_search_api.py"
    "agent_orchestrator.py"
    "main.py"
)

for file in "${files[@]}"; do
    if [ -f "$file" ]; then
        docker cp "$file" "$CONTAINER_ID:/app/"
        echo -e "${GREEN}✅ Copied $file${NC}"
    else
        echo -e "${YELLOW}⚠️  $file not found in current directory${NC}"
    fi
done

echo ""

# Step 3: Verify files
echo -e "${YELLOW}Step 3: Verifying files in container...${NC}"
docker exec "$CONTAINER_ID" ls -lh /app/system_prompt_config.py /app/backend_tool_classifier.py /app/text_search_api.py /app/agent_orchestrator.py /app/main.py 2>/dev/null

echo ""

# Step 4: Restart container
read -p "Do you want to restart the container? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}Restarting container...${NC}"
    docker restart "$CONTAINER_ID"
    echo -e "${GREEN}✅ Container restarted${NC}"
    sleep 2
    echo -e "${YELLOW}Checking container status...${NC}"
    docker ps | grep "$CONTAINER_ID"
else
    echo -e "${YELLOW}Skipped restart. Container will use old code until restart.${NC}"
fi

echo ""
echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}✅ Deployment Complete!${NC}"
echo -e "${GREEN}================================${NC}\n"

echo -e "${BLUE}Summary of changes deployed:${NC}"
echo "1. ✅ Price range search feature (1500-2000 watches)"
echo "2. ✅ NO WHOLESALE policy"
echo "3. ✅ NO WARRANTY on imported watches"
echo "4. ✅ AUTHENTICITY = IMPORTED terminology"
echo ""

echo -e "${YELLOW}View logs:${NC}"
echo -e "${BLUE}docker logs -f $CONTAINER_ID${NC}\n"
