"""
Watch-Only Fast Scraper
Enhanced version that only scrapes watch products and filters out non-watches
"""

import requests
from bs4 import BeautifulSoup
import pymongo
from pymongo import MongoClient
import time
import re
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse
import json
from datetime import datetime

class WatchOnlyFastScraper:
    """
    Fast scraper that only collects watch products
    Filters out non-watch items during scraping
    """
    
    def __init__(self, base_url: str, mongodb_uri: str):
        self.base_url = base_url
        self.mongodb_uri = mongodb_uri
        
        # MongoDB connection
        self.client = MongoClient(mongodb_uri)
        self.db = self.client['watchvine_refined']  
        self.collection = self.db['products']
        
        # Initialize session with headers
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        })
        
        # Watch-specific keywords for filtering
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
            'sunglasses', 'eyewear', 'glasses', 'sunglass', 'shirt', 'tshirt', 
            't-shirt', 'clothing', 'apparel', 'bag', 'wallet', 'belt', 'shoes', 
            'footwear', 'jewelry', 'ring', 'necklace', 'bracelet', 'earring',
            'phone', 'mobile', 'case', 'cover', 'charger'
        ]
        
        print("🎯 Watch-Only Fast Scraper initialized - filtering for watches only!")

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

    def is_watch_category(self, category_url: str, category_name: str = "") -> bool:
        """Check if a category is watch-related"""
        text = f"{category_url} {category_name}".lower()
        
        # Check for watch-specific terms in URL or name
        watch_indicators = ['watch', 'timepiece', 'chronograph', 'horology']
        if any(indicator in text for indicator in watch_indicators):
            return True
        
        # Check for watch brands in category
        brand_indicators = ['rolex', 'omega', 'casio', 'seiko', 'fossil', 'armani']
        if any(brand in text for brand in brand_indicators):
            return True
        
        # Exclude obvious non-watch categories
        exclude_categories = [
            'sunglass', 'eyewear', 'clothing', 'apparel', 'bag', 'wallet', 
            'shoe', 'footwear', 'jewelry', 'ring', 'necklace', 'earring'
        ]
        if any(exclude in text for exclude in exclude_categories):
            return False
        
        return True  # Default to include if uncertain

    def get_category_urls(self, max_depth=2):
        """Get category URLs - prioritize watch categories"""
        try:
            print(f"🔍 Fetching categories from {self.base_url}")
            response = self.session.get(self.base_url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            category_urls = set()
            
            # Common selectors for category links
            selectors = [
                'nav a[href]',
                '.nav a[href]',
                '.menu a[href]', 
                '.navigation a[href]',
                '.category a[href]',
                '.categories a[href]',
                'header a[href]',
                '.main-nav a[href]'
            ]
            
            for selector in selectors:
                links = soup.select(selector)
                for link in links:
                    href = link.get('href')
                    text = link.get_text(strip=True).lower()
                    
                    if href and not href.startswith('#'):
                        full_url = urljoin(self.base_url, href)
                        
                        # Check if this is a watch-related category
                        if self.is_watch_category(full_url, text):
                            category_urls.add(full_url)
            
            # Also add the main URL for general product pages
            category_urls.add(self.base_url)
            
            category_list = list(category_urls)
            print(f"📋 Found {len(category_list)} potential watch categories")
            
            # Log some categories for verification
            for i, url in enumerate(category_list[:5]):
                print(f"  {i+1}. {url}")
            if len(category_list) > 5:
                print(f"  ... and {len(category_list) - 5} more")
            
            return category_list
            
        except Exception as e:
            print(f"❌ Error getting categories: {e}")
            return [self.base_url]

    def extract_product_info(self, product_card, base_url):
        """Extract product information from a product card - WATCHES ONLY"""
        product = {}
        
        try:
            # Extract product name/title
            title_selectors = [
                'h2 a', 'h3 a', '.product-name a', '.product-title a', 
                '.title a', 'h4 a', '.name a', 'a[title]', '.product-link'
            ]
            title_elem = None
            for selector in title_selectors:
                title_elem = product_card.select_one(selector)
                if title_elem:
                    break
            
            if not title_elem:
                return None
            
            product['name'] = title_elem.get('title') or title_elem.get_text(strip=True)
            product['url'] = urljoin(base_url, title_elem.get('href', ''))
            
            if not product['name']:
                return None
            
            # 🎯 CRITICAL: Check if it's a watch product - SKIP if not a watch
            if not self.is_watch_product(product['name'], "", product['url']):
                return None
            
            # Extract price
            price_selectors = [
                '.price', '.product-price', '.cost', '.amount', 
                '[data-price]', '.price-current', '.sale-price',
                '.regular-price', '.product-cost'
            ]
            
            price_elem = None
            for selector in price_selectors:
                price_elem = product_card.select_one(selector)
                if price_elem:
                    break
            
            if price_elem:
                price_text = price_elem.get_text(strip=True)
                # Extract numeric price using regex
                price_match = re.search(r'[\d,]+\.?\d*', price_text.replace(',', ''))
                product['price'] = price_match.group().replace(',', '') if price_match else "0"
            else:
                product['price'] = "0"
            
            # Extract image URLs
            img_selectors = [
                'img', '.product-image img', '.image img',
                '.thumbnail img', '.photo img'
            ]
            
            images = []
            for selector in img_selectors:
                img_elem = product_card.select_one(selector)
                if img_elem:
                    img_src = img_elem.get('src') or img_elem.get('data-src') or img_elem.get('data-lazy')
                    if img_src:
                        # Handle relative URLs
                        full_img_url = urljoin(base_url, img_src)
                        images.append(full_img_url)
                        break  # Take first image
            
            product['image_urls'] = images
            
            # Set watch category since we're only scraping watches
            product['category'] = 'Watch'
            product['category_key'] = 'watch'
            product['scraped_at'] = time.time()
            
            return product
            
        except Exception as e:
            print(f"❌ Error extracting product info: {e}")
            return None

    def scrape_products_from_page(self, url, max_products=None):
        """Scrape watch products from a single page"""
        try:
            print(f"🔍 Scraping: {url}")
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            products = []
            
            # Common selectors for product cards/containers
            product_selectors = [
                '.product-item',
                '.product-card', 
                '.product',
                '.item-product',
                '.listing-item',
                '.grid-item',
                '[data-product]',
                '.product-container'
            ]
            
            product_cards = []
            for selector in product_selectors:
                cards = soup.select(selector)
                if cards:
                    product_cards = cards
                    break
            
            if not product_cards:
                print(f"⚠️ No product cards found on {url}")
                return []
            
            print(f"📦 Found {len(product_cards)} potential products on page")
            watch_count = 0
            
            for card in product_cards:
                if max_products and watch_count >= max_products:
                    break
                    
                product_info = self.extract_product_info(card, url)
                if product_info:  # Only watches pass the filter
                    products.append(product_info)
                    watch_count += 1
                    
                    if watch_count % 10 == 0:
                        print(f"  📈 Found {watch_count} watches so far...")
            
            print(f"✅ Collected {watch_count} WATCH products from this page")
            return products
            
        except Exception as e:
            print(f"❌ Error scraping {url}: {e}")
            return []

    def save_to_mongodb(self, products):
        """Save watch products to MongoDB"""
        if not products:
            return
        
        saved_count = 0
        updated_count = 0
        
        for product in products:
            try:
                # Check if product already exists by URL
                existing = self.collection.find_one({'url': product['url']})
                
                if existing:
                    # Update existing product
                    result = self.collection.update_one(
                        {'url': product['url']},
                        {'$set': product}
                    )
                    if result.modified_count > 0:
                        updated_count += 1
                else:
                    # Insert new product
                    self.collection.insert_one(product)
                    saved_count += 1
                    
            except Exception as e:
                print(f"❌ Error saving product {product.get('name', 'Unknown')}: {e}")
                continue
        
        print(f"💾 Saved {saved_count} new watches, updated {updated_count} existing")

    def run_watch_scraping(self, max_products_per_page=100, max_categories=None):
        """Run the complete watch-only scraping process"""
        try:
            print("🚀 Starting WATCH-ONLY scraping...")
            print("🎯 Filtering: Only watch products will be collected")
            
            # Get watch-related categories
            category_urls = self.get_category_urls()
            
            if max_categories:
                category_urls = category_urls[:max_categories]
                print(f"📋 Limited to {max_categories} categories for this run")
            
            all_products = []
            total_watch_count = 0
            
            for i, category_url in enumerate(category_urls, 1):
                print(f"\n📂 Category {i}/{len(category_urls)}")
                
                products = self.scrape_products_from_page(
                    category_url, 
                    max_products=max_products_per_page
                )
                
                # Add unique products only
                for product in products:
                    if not any(p['url'] == product['url'] for p in all_products):
                        all_products.append(product)
                        total_watch_count += 1
                
                print(f"📊 Total unique watches collected so far: {total_watch_count}")
                
                # Delay between categories
                time.sleep(2)
            
            print(f"\n🎯 WATCH-ONLY scraping summary:")
            print(f"📊 Total WATCH products found: {len(all_products)}")
            print(f"🚫 Non-watch products filtered out during scraping")
            
            if not all_products:
                print("❌ No watch products found. Check if the site has watch categories.")
                return
            
            # Save to MongoDB
            self.save_to_mongodb(all_products)
            
            print(f"\n✅ WATCH scraping completed successfully!")
            print(f"📊 Final count: {len(all_products)} watch products")
            print("🎯 Database now contains ONLY watch products!")
            
        except KeyboardInterrupt:
            print("\n⚠️ Watch scraping interrupted by user")
        except Exception as e:
            print(f"\n❌ Error during watch scraping: {str(e)}")
        finally:
            self.client.close()

# Usage example and main execution
if __name__ == "__main__":
    # Configuration
    BASE_URL = "https://watchvine01.cartpe.in"  # Replace with actual URL
    MONGODB_URI = "mongodb://admin:strongpassword123@72.62.76.36:27017/?authSource=admin"
    
    # Initialize watch-only scraper
    scraper = WatchOnlyFastScraper(BASE_URL, MONGODB_URI)
    
    # Run watch-only scraping
    scraper.run_watch_scraping(
        max_products_per_page=50,  # Limit per page for efficiency
        max_categories=10          # Limit categories for initial run
    )