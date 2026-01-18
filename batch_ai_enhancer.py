#!/usr/bin/env python3
"""
Optimized Batch AI Enhancement with better error handling and rate limiting
"""

import sys
sys.path.append('.')
from ai_image_enhancer import AIWatchImageEnhancer
import time
from datetime import datetime

def run_batch_enhancement(batch_size=50, total_limit=None):
    MONGODB_URI = "mongodb://admin:strongpassword123@72.62.76.36:27017/?authSource=admin"
    GOOGLE_API_KEY = "AIzaSyBZ8shurgeNDiDj4TlpBk7RUgrQ-G2mJ_0"
    
    enhancer = AIWatchImageEnhancer(MONGODB_URI, GOOGLE_API_KEY)
    
    try:
        print(f"🚀 Starting Batch AI Enhancement")
        print(f"Batch size: {batch_size}")
        print(f"Total limit: {total_limit or 'No limit'}")
        print(f"Started at: {datetime.now().strftime('%H:%M:%S')}")
        print("-" * 50)
        
        # Run enhancement
        processed, enhanced = enhancer.enhance_all_watches(
            batch_size=batch_size, 
            limit=total_limit
        )
        
        print(f"\n🎉 Batch Enhancement Complete!")
        print(f"Processed: {processed} watches")
        print(f"Enhanced: {enhanced} watches")
        print(f"Completed at: {datetime.now().strftime('%H:%M:%S')}")
        
        # Show summary
        enhancer.get_enhancement_summary()
        
    except KeyboardInterrupt:
        print(f"\n⏹️ Process interrupted by user")
        enhancer.get_enhancement_summary()
    except Exception as e:
        print(f"\n❌ Error occurred: {e}")
        enhancer.get_enhancement_summary()
    finally:
        enhancer.close()

if __name__ == "__main__":
    # Start with smaller batches to handle API rate limits better
    print("Select enhancement scope:")
    print("1. Small batch (50 watches) - Testing")
    print("2. Medium batch (200 watches) - Gradual enhancement")
    print("3. Large batch (500 watches) - Major enhancement")
    print("4. Full database (all remaining watches)")
    
    choice = input("\nEnter your choice (1-4): ").strip()
    
    if choice == "1":
        run_batch_enhancement(batch_size=10, total_limit=50)
    elif choice == "2":
        run_batch_enhancement(batch_size=20, total_limit=200)
    elif choice == "3":
        run_batch_enhancement(batch_size=25, total_limit=500)
    elif choice == "4":
        run_batch_enhancement(batch_size=30, total_limit=None)
    else:
        print("Invalid choice. Running small batch (50 watches)...")
        run_batch_enhancement(batch_size=10, total_limit=50)