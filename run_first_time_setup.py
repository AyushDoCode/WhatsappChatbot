#!/usr/bin/env python3
"""
First Time Setup - Complete Watch System
Run this first to set up and test the entire system
"""

import os
import sys
import subprocess
import time
import requests
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def run_command(command, description):
    """Run a system command with logging"""
    logging.info(f"🔧 {description}")
    try:
        result = subprocess.run(command, shell=True, check=True, 
                              capture_output=True, text=True)
        logging.info(f"✅ {description} completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"❌ {description} failed: {e.stderr}")
        return False

def main():
    """First time setup and deployment"""
    print("🚀 WATCH SYSTEM - FIRST TIME SETUP")
    print("=" * 50)
    
    # Step 1: Make scripts executable
    logging.info("Making scripts executable...")
    os.chmod("deploy_watch_system.sh", 0o755)
    
    # Step 2: Deploy the system
    logging.info("Starting deployment...")
    if not run_command("./deploy_watch_system.sh", "Watch System Deployment"):
        sys.exit(1)
    
    # Step 3: Wait for system to start
    logging.info("Waiting for system to fully start...")
    time.sleep(60)
    
    # Step 4: Test the system
    logging.info("Testing the complete system...")
    if run_command("python test_watch_system.py --test all", "System Testing"):
        print("\n🎉 SETUP COMPLETED SUCCESSFULLY!")
        print("Your watch system is now ready for production!")
    else:
        print("\n⚠️ Setup completed but some tests failed.")
        print("Check the logs and run tests again.")
    
    print("\n📋 QUICK START COMMANDS:")
    print("• Test scraper: docker exec watch_scraper python smart_watch_scraper.py")
    print("• Test AI enhancer: docker exec watch_ai_enhancer python auto_ai_watch_enhancer.py")
    print("• View logs: docker-compose -f docker-compose.watch_system.yml logs -f")
    print("• System stats: curl http://localhost:8002/stats")

if __name__ == "__main__":
    main()