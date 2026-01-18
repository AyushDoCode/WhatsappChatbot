#!/usr/bin/env python3
"""
Smart Watch-Only Night Scraper with Database Sync
- Only scrapes watch products
- Smart sync: Add new, remove deleted, keep existing
- Auto AI enhancement for new watches only
- Runs between 12 AM to 6 AM
- Includes image indexing
"""

import requests
from bs4 import BeautifulSoup
import pymongo
from pymongo import MongoClient
import time
import re
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse
import json
from datetime import datetime, timedelta
import schedule
import logging
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
import google.generativeai as genai
from PIL import Image
import io

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('watch_scraper.log'),
        logging.StreamHandler()
    ]
)

class SmartWatchScraper:
    def __init__(self, mongodb_uri: str, google_api_key: str, base_url: str = "https://watchvine01.cartpe.in"):
        self.mongodb_uri = mongodb_uri
        self.base_url = base_url
        self.google_api_key = google_api_key
        
        # MongoDB setup
        self.client = MongoClient(mongodb_uri)
        self.db = self.client['watchvine_refined']
        self.collection = self.db['products']
        
        # HTTP session
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
        # Watch detection patterns
        self.watch_keywords = [
            'watch', 'timepiece', 'chronograph', 'wristwatch', 
            'smartwatch', 'digital watch', 'analog watch', 'luxury watch'
        ]
        
        self.watch_brands = [
            'rolex', 'omega', 'audemars piguet', 'patek philippe', 'cartier',
            'breitling', 'tag heuer', 'iwc', 'panerai', 'hublot', 'tissot',
            'seiko', 'casio', 'citizen', 'fossil', 'maybach', 'daniel wellington',
            'mvmt', 'nixon', 'timex', 'bulova', 'invicta', 'diesel', 'armani',
            'gucci', 'versace', 'boss', 'calvin klein', 'tommy hilfiger',
            'michael kors', 'apple', 'samsung', 'garmin', 'fitbit', 'amazfit'
        ]
        
        # Non-watch exclusions
        self.exclude_keywords = [
            'sunglasses', 'eyewear', 'glasses', 'sunglass',
            'shirt', 'tshirt', 't-shirt', 'clothing', 'apparel',
            'bag', 'wallet', 'belt', 'shoes', 'footwear',
            'jewelry', 'ring', 'necklace', 'bracelet', 'earring',
            'phone', 'mobile', 'case', 'cover', 'charger'
        ]
        
        # AI setup for new products
        if google_api_key:
            genai.configure(api_key=google_api_key)
            self.ai_model = genai.GenerativeModel('gemini-2.0-flash')
        else:
            self.ai_model = None
        
        logging.info("Smart Watch Scraper initialized")
    
    def is_watch_product(self, product_name: str, category: str = "", url: str = "") -> bool:
        """Determine if a product is a watch"""
        text = f"{product_name} {category} {url}".lower()
        
        # Check exclusions first
        for exclude in self.exclude_keywords:
            if exclude in text:
                return False
        
        # Check for watch keywords
        for keyword in self.watch_keywords:
            if keyword in text:
                return True
        
        # Check for watch brands
        for brand in self.watch_brands:
            if brand in text:
                return True
        
        # Check category patterns
        if re.search(r'\b(watch|timepiece|chronograph)\b', text):
            return True
        
        return False
    
    def scrape_product_details(self, product_url: str) -> Dict:
        """Scrape detailed product information"""
        try:
            response = self.session.get(product_url, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            details = {}
            
            # Extract product name
            name_selectors = [
                'h1', '.product-title', '.product-name', 
                '[data-product-name]', '.title'
            ]
            
            for selector in name_selectors:
                name_elem = soup.select_one(selector)
                if name_elem:
                    details['name'] = name_elem.get_text(strip=True)
                    break
            
            # Extract price
            price_selectors = [
                '.price', '.product-price', '.cost', 
                '[data-price]', '.amount', '.price-current'
            ]
            
            for selector in price_selectors:
                price_elem = soup.select_one(selector)
                if price_elem:
                    price_text = price_elem.get_text(strip=True)
                    price_match = re.search(r'[\d,]+\.?\d*', price_text.replace(',', ''))
                    if price_match:
                        details['price'] = price_match.group().replace(',', '')
                        break
            
            # Extract images
            img_selectors = [
                '.product-gallery img', '.product-images img',
                '.main-image img', 'img[data-src]', '.gallery img'
            ]
            
            images = []
            for selector in img_selectors:
                img_elements = soup.select(selector)
                for img in img_elements:
                    src = img.get('src') or img.get('data-src')
                    if src:
                        full_url = urljoin(product_url, src)
                        if full_url not in images and any(ext in src.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                            images.append(full_url)
            
            details['image_urls'] = images[:5]  # Limit to 5 images
            
            # Extract description
            desc_selectors = [
                '.product-description', '.description', 
                '.product-details', '.product-info'
            ]
            
            for selector in desc_selectors:
                desc_elem = soup.select_one(selector)
                if desc_elem:
                    details['description'] = desc_elem.get_text(strip=True)[:500]
                    break
            
            # Extract specifications
            spec_selectors = [
                '.specifications li', '.product-specs li', 
                '.features li', '.specs tr'
            ]
            
            specs = []
            for selector in spec_selectors:
                spec_elements = soup.select(selector)
                for spec in spec_elements[:10]:  # Limit specs
                    spec_text = spec.get_text(strip=True)
                    if spec_text and len(spec_text) < 100:
                        specs.append(spec_text)
            
            if specs:
                details['specifications'] = specs
            
            return details
            
        except Exception as e:
            logging.error(f"Error scraping product details from {product_url}: {e}")
            return {}
    
    def scrape_category_page(self, category_url: str) -> List[Dict]:
        """Scrape watches from a category page"""
        try:
            response = self.session.get(category_url, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            products = []
            
            # Product selectors
            product_selectors = [
                '.product-item', '.product-card', '.product',
                '.item', '[data-product]', '.listing-item'
            ]
            
            product_elements = []
            for selector in product_selectors:
                elements = soup.select(selector)
                if elements:
                    product_elements = elements
                    break
            
            for element in product_elements:
                try:
                    # Extract basic info
                    name_elem = element.select_one('.product-name, .product-title, h3, h4, .name, .title')
                    url_elem = element.select_one('a[href]')
                    price_elem = element.select_one('.price, .product-price, .cost')
                    
                    if not name_elem or not url_elem:
                        continue
                    
                    name = name_elem.get_text(strip=True)
                    url = urljoin(category_url, url_elem.get('href'))
                    
                    # Check if it's a watch
                    if not self.is_watch_product(name, "", url):
                        continue
                    
                    # Extract price
                    price = "0"
                    if price_elem:
                        price_text = price_elem.get_text(strip=True)
                        price_match = re.search(r'[\d,]+\.?\d*', price_text.replace(',', ''))
                        if price_match:
                            price = price_match.group().replace(',', '')
                    
                    # Extract image
                    img_elem = element.select_one('img')
                    images = []
                    if img_elem:
                        src = img_elem.get('src') or img_elem.get('data-src')
                        if src:
                            images.append(urljoin(category_url, src))
                    
                    # Get detailed info
                    detailed_info = self.scrape_product_details(url)
                    
                    product = {
                        'name': detailed_info.get('name', name),
                        'url': url,
                        'price': detailed_info.get('price', price),
                        'image_urls': detailed_info.get('image_urls', images),
                        'category': 'Watch',
                        'scraped_at': time.time(),
                        'description': detailed_info.get('description', ''),
                        'specifications': detailed_info.get('specifications', [])
                    }
                    
                    products.append(product)
                    logging.info(f"Scraped watch: {name}")
                    time.sleep(1)  # Rate limiting
                    
                except Exception as e:
                    logging.error(f"Error processing product element: {e}")
                    continue
            
            return products
            
        except Exception as e:
            logging.error(f"Error scraping category {category_url}: {e}")
            return []
    
    def get_all_category_urls(self) -> List[str]:
        """Get all watch-related category URLs"""
        try:
            response = self.session.get(self.base_url, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            category_urls = []
            
            # Find category links
            link_selectors = [
                'a[href*="watch"]', 'a[href*="timepiece"]',
                '.category a', '.menu a', '.nav a'
            ]
            
            for selector in link_selectors:
                links = soup.select(selector)
                for link in links:
                    href = link.get('href')
                    text = link.get_text(strip=True).lower()
                    
                    if href and ('watch' in text or 'watch' in href.lower()):
                        full_url = urljoin(self.base_url, href)
                        if full_url not in category_urls:
                            category_urls.append(full_url)
            
            # Add common watch category patterns
            common_patterns = [
                '/mens-watches', '/women-watches', '/luxury-watches',
                '/sport-watches', '/digital-watches', '/analog-watches',
                '/smart-watches', '/categories/watch', '/categories/watches'
            ]
            
            for pattern in common_patterns:
                url = f"{self.base_url}{pattern}"
                if url not in category_urls:
                    category_urls.append(url)
            
            return category_urls[:20]  # Limit to 20 categories
            
        except Exception as e:
            logging.error(f"Error getting category URLs: {e}")
            return [self.base_url]
    
    def scrape_all_watches(self) -> List[Dict]:
        """Scrape all watch products from the website"""
        logging.info("Starting watch scraping...")
        
        category_urls = self.get_all_category_urls()
        logging.info(f"Found {len(category_urls)} categories to scrape")
        
        all_watches = []
        
        for i, category_url in enumerate(category_urls, 1):
            logging.info(f"Scraping category {i}/{len(category_urls)}: {category_url}")
            
            watches = self.scrape_category_page(category_url)
            all_watches.extend(watches)
            
            logging.info(f"Found {len(watches)} watches in category")
            time.sleep(2)  # Rate limiting between categories
        
        # Remove duplicates based on URL
        unique_watches = {}
        for watch in all_watches:
            url = watch.get('url', '')
            if url and url not in unique_watches:
                unique_watches[url] = watch
        
        final_watches = list(unique_watches.values())
        logging.info(f"Total unique watches scraped: {len(final_watches)}")
        
        return final_watches
    
    def get_existing_watch_urls(self) -> Set[str]:
        """Get URLs of all existing watches in database"""
        existing_urls = set()
        for watch in self.collection.find({}, {'url': 1}):
            if watch.get('url'):
                existing_urls.add(watch['url'])
        return existing_urls
    
    def sync_database(self, scraped_watches: List[Dict]) -> Tuple[int, int, int]:
        """Smart database sync: add new, remove deleted, keep existing"""
        logging.info("Starting database synchronization...")
        
        # Get existing and scraped URLs
        existing_urls = self.get_existing_watch_urls()
        scraped_urls = {watch['url'] for watch in scraped_watches if watch.get('url')}
        
        # Find new, existing, and deleted watches
        new_urls = scraped_urls - existing_urls
        existing_urls_still_present = scraped_urls & existing_urls
        deleted_urls = existing_urls - scraped_urls
        
        logging.info(f"New watches: {len(new_urls)}")
        logging.info(f"Existing watches still present: {len(existing_urls_still_present)}")
        logging.info(f"Deleted watches: {len(deleted_urls)}")
        
        # Add new watches
        new_watches = [watch for watch in scraped_watches if watch['url'] in new_urls]
        added_count = 0
        
        if new_watches:
            try:
                self.collection.insert_many(new_watches)
                added_count = len(new_watches)
                logging.info(f"Added {added_count} new watches to database")
            except Exception as e:
                logging.error(f"Error adding new watches: {e}")
        
        # Remove deleted watches
        deleted_count = 0
        if deleted_urls:
            try:
                result = self.collection.delete_many({'url': {'$in': list(deleted_urls)}})
                deleted_count = result.deleted_count
                logging.info(f"Removed {deleted_count} deleted watches from database")
            except Exception as e:
                logging.error(f"Error removing deleted watches: {e}")
        
        # Update existing watches (only metadata, not AI fields)
        updated_count = 0
        existing_watches = [watch for watch in scraped_watches if watch['url'] in existing_urls_still_present]
        
        for watch in existing_watches:
            try:
                # Only update non-AI fields
                update_data = {
                    'price': watch.get('price'),
                    'image_urls': watch.get('image_urls'),
                    'description': watch.get('description'),
                    'specifications': watch.get('specifications'),
                    'last_updated': time.time()
                }
                
                result = self.collection.update_one(
                    {'url': watch['url']},
                    {'$set': update_data}
                )
                
                if result.modified_count > 0:
                    updated_count += 1
                    
            except Exception as e:
                logging.error(f"Error updating watch {watch.get('url')}: {e}")
        
        logging.info(f"Updated {updated_count} existing watches")
        return added_count, deleted_count, updated_count
    
    def enhance_new_watches_with_ai(self):
        """Run AI enhancement only on new watches (without ai_analysis field)"""
        if not self.ai_model:
            logging.warning("No AI model configured, skipping AI enhancement")
            return
        
        logging.info("Starting AI enhancement for new watches...")
        
        # Find new watches without AI analysis
        new_watches = list(self.collection.find({
            'ai_analysis': {'$exists': False},
            'image_urls': {'$exists': True, '$ne': []}
        }))
        
        if not new_watches:
            logging.info("No new watches need AI enhancement")
            return
        
        logging.info(f"Found {len(new_watches)} new watches for AI enhancement")
        
        # Run comprehensive AI enhancement
        from auto_ai_watch_enhancer import AutoAIWatchEnhancer
        
        enhancer = AutoAIWatchEnhancer(self.mongodb_uri, self.google_api_key)
        
        enhanced_count = 0
        for watch in new_watches:
            try:
                enhanced_watch, success = enhancer.enhance_watch_with_ai(watch)
                
                if success:
                    result = self.collection.replace_one(
                        {'_id': watch['_id']},
                        enhanced_watch
                    )
                    
                    if result.modified_count > 0:
                        enhanced_count += 1
                        logging.info(f"✅ Enhanced: {watch.get('name', 'Unknown')}")
                        
                        # Log enhanced fields for monitoring
                        colors = enhanced_watch.get('colors', [])
                        category = enhanced_watch.get('ai_category', 'N/A')
                        belt_type = enhanced_watch.get('belt_type', 'N/A')
                        logging.info(f"   Fields: {colors[:2]} | {category} | {belt_type}")
                
                time.sleep(1.5)  # Rate limiting for API
                
            except Exception as e:
                logging.error(f"Error enhancing watch {watch.get('name')}: {e}")
                continue
        
        enhancer.close()
        logging.info(f"🎉 AI enhancement completed. Enhanced {enhanced_count} new watches with comprehensive fields")
    
    def run_image_indexing(self):
        """Run image indexing for all watches"""
        logging.info("Starting image indexing...")
        
        try:
            # Import and run the indexer
            import subprocess
            result = subprocess.run([
                sys.executable, 'indexer_v2.py'
            ], capture_output=True, text=True)
            
            if result.returncode == 0:
                logging.info("Image indexing completed successfully")
            else:
                logging.error(f"Image indexing failed: {result.stderr}")
                
        except Exception as e:
            logging.error(f"Error running image indexing: {e}")
    
    def run_full_scraping_cycle(self):
        """Run complete scraping, sync, AI enhancement, and indexing cycle"""
        start_time = time.time()
        logging.info("=" * 60)
        logging.info("STARTING FULL WATCH SCRAPING CYCLE")
        logging.info("=" * 60)
        
        try:
            # 1. Scrape watches
            logging.info("STEP 1: Scraping watch products...")
            scraped_watches = self.scrape_all_watches()
            
            # 2. Sync database
            logging.info("STEP 2: Syncing database...")
            added, deleted, updated = self.sync_database(scraped_watches)
            
            # 3. AI enhancement for new watches only
            logging.info("STEP 3: AI enhancement for new watches...")
            self.enhance_new_watches_with_ai()
            
            # 4. Image indexing
            logging.info("STEP 4: Running image indexing...")
            self.run_image_indexing()
            
            # Summary
            total_time = time.time() - start_time
            logging.info("=" * 60)
            logging.info("SCRAPING CYCLE COMPLETED")
            logging.info("=" * 60)
            logging.info(f"Total time: {total_time/60:.1f} minutes")
            logging.info(f"Watches added: {added}")
            logging.info(f"Watches deleted: {deleted}")
            logging.info(f"Watches updated: {updated}")
            logging.info(f"Total watches in database: {self.collection.count_documents({})}")
            logging.info("=" * 60)
            
        except Exception as e:
            logging.error(f"Error in scraping cycle: {e}")
    
    def is_night_time(self) -> bool:
        """Check if current time is between 12 AM and 6 AM"""
        now = datetime.now()
        return now.hour >= 0 and now.hour < 6
    
    def schedule_night_scraping(self):
        """Schedule scraping to run between 12 AM and 6 AM"""
        # Schedule at 12:30 AM
        schedule.every().day.at("00:30").do(self.run_full_scraping_cycle)
        
        logging.info("Night scraping scheduled for 12:30 AM daily")
        
        while True:
            schedule.run_pending()
            time.sleep(60)  # Check every minute
    
    def close(self):
        """Close database connection"""
        self.client.close()

def main():
    """Main function for testing"""
    MONGODB_URI = "mongodb://admin:strongpassword123@72.62.76.36:27017/?authSource=admin"
    GOOGLE_API_KEY = "AIzaSyBZ8shurgeNDiDj4TlpBk7RUgrQ-G2mJ_0"
    
    scraper = SmartWatchScraper(MONGODB_URI, GOOGLE_API_KEY)
    
    try:
        print("🕐 Smart Watch Scraper")
        print("1. Run scraping cycle now (for testing)")
        print("2. Start night scheduler (12 AM - 6 AM)")
        
        choice = input("Choose option (1-2): ").strip()
        
        if choice == "1":
            scraper.run_full_scraping_cycle()
        elif choice == "2":
            scraper.schedule_night_scraping()
        else:
            print("Invalid choice")
            
    except KeyboardInterrupt:
        logging.info("Scraper stopped by user")
    finally:
        scraper.close()

if __name__ == "__main__":
    main()