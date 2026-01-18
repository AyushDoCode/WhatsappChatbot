#!/usr/bin/env python3
"""
Enhanced Watch Scraper - Only scrapes watch products with detailed information
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

class EnhancedWatchScraper:
    def __init__(self, mongodb_uri: str, base_url: str = "https://watchvine01.cartpe.in"):
        self.mongodb_uri = mongodb_uri
        self.base_url = base_url
        self.client = MongoClient(mongodb_uri)
        self.db = self.client['watchvine_refined']
        self.collection = self.db['products']
        
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
        # Watch-specific patterns for filtering
        self.watch_keywords = [
            'watch', 'timepiece', 'chronograph', 'wristwatch', 
            'smartwatch', 'digital watch', 'analog watch'
        ]
        
        # Enhanced extraction patterns
        self.brand_patterns = {
            'rolex': r'\b(rolex)\b',
            'omega': r'\b(omega)\b',
            'audemars_piguet': r'\b(audemars[_\s]*piguet|ap)\b',
            'patek_philippe': r'\b(patek[_\s]*philippe)\b',
            'cartier': r'\b(cartier)\b',
            'breitling': r'\b(breitling)\b',
            'tag_heuer': r'\b(tag[_\s]*heuer)\b',
            'iwc': r'\b(iwc)\b',
            'panerai': r'\b(panerai)\b',
            'hublot': r'\b(hublot)\b',
            'tissot': r'\b(tissot)\b',
            'seiko': r'\b(seiko)\b',
            'casio': r'\b(casio)\b',
            'citizen': r'\b(citizen)\b',
            'fossil': r'\b(fossil)\b',
            'maybach': r'\b(maybach)\b'
        }
    
    def is_watch_product(self, product_name: str, category: str = "") -> bool:
        """Check if a product is a watch"""
        text = f"{product_name} {category}".lower()
        
        # Check for watch keywords
        for keyword in self.watch_keywords:
            if keyword in text:
                return True
        
        # Check for watch brands (likely watches)
        for brand_pattern in self.brand_patterns.values():
            if re.search(brand_pattern, text, re.IGNORECASE):
                return True
        
        # Exclude non-watch items
        exclude_keywords = [
            'sunglasses', 'eyewear', 'glasses', 'sunglass',
            'shirt', 'tshirt', 't-shirt', 'clothing', 'apparel',
            'bag', 'wallet', 'belt', 'shoes', 'footwear',
            'jewelry', 'ring', 'necklace', 'bracelet', 'earring',
            'phone', 'mobile', 'case', 'cover', 'charger'
        ]
        
        for exclude in exclude_keywords:
            if exclude in text:
                return False
        
        return False
    
    def extract_detailed_info(self, product_url: str) -> Dict:
        """Extract detailed information from product page"""
        try:
            response = self.session.get(product_url, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            details = {}
            
            # Try to extract product description
            description_selectors = [
                '.product-description',
                '.description',
                '.product-details',
                '.product-info',
                '#product-description',
                '[data-description]'
            ]
            
            for selector in description_selectors:
                desc_element = soup.select_one(selector)
                if desc_element:
                    details['description'] = desc_element.get_text(strip=True)
                    break
            
            # Try to extract specifications
            spec_selectors = [
                '.specifications',
                '.product-specs',
                '.features',
                '.product-features'
            ]
            
            specs = []
            for selector in spec_selectors:
                spec_elements = soup.select(f"{selector} li, {selector} p")
                if spec_elements:
                    specs.extend([elem.get_text(strip=True) for elem in spec_elements])
            
            if specs:
                details['specifications'] = specs
            
            # Extract additional images
            img_selectors = [
                '.product-gallery img',
                '.product-images img',
                '.additional-images img',
                '.thumbnail img'
            ]
            
            additional_images = []
            for selector in img_selectors:
                img_elements = soup.select(selector)
                for img in img_elements:
                    src = img.get('src') or img.get('data-src')
                    if src:
                        full_url = urljoin(product_url, src)
                        if full_url not in additional_images:
                            additional_images.append(full_url)
            
            if additional_images:
                details['additional_images'] = additional_images[:10]  # Limit to 10 images
            
            return details
            
        except Exception as e:
            print(f"Error extracting details from {product_url}: {e}")
            return {}
    
    def enhance_product_data(self, product: Dict) -> Dict:
        """Enhance product data with extracted fields"""
        name = product.get('name', '')
        url = product.get('url', '')
        category = product.get('category', '')
        description = product.get('description', '')
        
        # Combine all text for analysis
        all_text = f"{name} {category} {description}".lower()
        
        # Extract brand
        brand = None
        for brand_name, pattern in self.brand_patterns.items():
            if re.search(pattern, all_text, re.IGNORECASE):
                brand = brand_name.replace('_', ' ').title()
                break
        
        # Extract colors
        color_patterns = {
            'black': r'\b(black|nero|noir)\b',
            'white': r'\b(white|bianco|blanc)\b',
            'silver': r'\b(silver|argento|steel|stainless)\b',
            'gold': r'\b(gold|oro|golden)\b',
            'rose_gold': r'\b(rose[_\s]*gold|pink[_\s]*gold)\b',
            'blue': r'\b(blue|blu|navy)\b',
            'red': r'\b(red|rosso|rouge)\b',
            'green': r'\b(green|verde|vert)\b',
            'brown': r'\b(brown|marrone|tan)\b',
            'gray': r'\b(gray|grey|grigio)\b'
        }
        
        colors = []
        for color, pattern in color_patterns.items():
            if re.search(pattern, all_text):
                colors.append(color.replace('_', ' ').title())
        
        # Extract styles
        style_patterns = {
            'minimalistic': r'\b(minimal|minimalist|simple|clean|sleek|elegant)\b',
            'sporty': r'\b(sport|sporty|athletic|diving|racing|fitness)\b',
            'luxury': r'\b(luxury|premium|prestige|exclusive|haute)\b',
            'casual': r'\b(casual|everyday|daily|informal)\b',
            'formal': r'\b(formal|dress|business|professional)\b',
            'vintage': r'\b(vintage|retro|classic|heritage)\b',
            'modern': r'\b(modern|contemporary|futuristic)\b',
            'smartwatch': r'\b(smart|digital|fitness|connected)\b'
        }
        
        styles = []
        for style, pattern in style_patterns.items():
            if re.search(pattern, all_text):
                styles.append(style.title())
        
        # Extract materials
        material_patterns = {
            'leather': r'\b(leather|cuir|pelle)\b',
            'metal': r'\b(metal|steel|stainless|bracelet)\b',
            'rubber': r'\b(rubber|silicone|sport[_\s]*band)\b',
            'fabric': r'\b(fabric|canvas|nylon|textile)\b',
            'ceramic': r'\b(ceramic|ceramica)\b',
            'titanium': r'\b(titanium|titan)\b'
        }
        
        materials = []
        for material, pattern in material_patterns.items():
            if re.search(pattern, all_text):
                materials.append(material.title())
        
        # Determine gender
        gender = 'Unisex'  # Default
        if re.search(r'\b(men|male|gentleman|homme)\b', all_text):
            gender = 'Men'
        elif re.search(r'\b(women|female|ladies|femme|lady)\b', all_text):
            gender = 'Women'
        
        # Price range categorization
        price_range = 'Unknown'
        try:
            price_num = float(product.get('price', '0'))
            if price_num < 1000:
                price_range = 'Budget (Under ₹1000)'
            elif price_num < 2500:
                price_range = 'Mid-Range (₹1000-2500)'
            elif price_num < 5000:
                price_range = 'Premium (₹2500-5000)'
            else:
                price_range = 'Luxury (₹5000+)'
        except:
            pass
        
        # Create searchable text
        searchable_terms = [
            name, category, brand or '', 
            ' '.join(colors), ' '.join(styles), ' '.join(materials),
            description
        ]
        searchable_text = ' '.join(filter(None, searchable_terms)).lower()
        
        # Enhanced product data
        enhanced = product.copy()
        enhanced.update({
            'brand': brand,
            'colors': colors,
            'styles': styles,
            'materials': materials,
            'gender': gender,
            'price_range': price_range,
            'searchable_text': searchable_text,
            'enhanced_at': datetime.now().isoformat(),
            'is_watch': True
        })
        
        return enhanced
    
    def scrape_product_list(self, category_url: str) -> List[Dict]:
        """Scrape products from a category page"""
        try:
            response = self.session.get(category_url, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            products = []
            
            # Common product selectors
            product_selectors = [
                '.product-item',
                '.product-card',
                '.product',
                '.item',
                '[data-product]'
            ]
            
            product_elements = []
            for selector in product_selectors:
                elements = soup.select(selector)
                if elements:
                    product_elements = elements
                    break
            
            for element in product_elements:
                try:
                    # Extract product name
                    name_selectors = [
                        '.product-name', '.product-title', 'h3', 'h4',
                        '.name', '.title', '[data-name]'
                    ]
                    
                    name = None
                    for selector in name_selectors:
                        name_elem = element.select_one(selector)
                        if name_elem:
                            name = name_elem.get_text(strip=True)
                            break
                    
                    if not name:
                        continue
                    
                    # Check if it's a watch product
                    if not self.is_watch_product(name, ""):
                        continue
                    
                    # Extract product URL
                    url_selectors = ['a', '[href]']
                    url = None
                    for selector in url_selectors:
                        url_elem = element.select_one(selector)
                        if url_elem and url_elem.get('href'):
                            url = urljoin(category_url, url_elem.get('href'))
                            break
                    
                    # Extract price
                    price_selectors = [
                        '.price', '.product-price', '.cost',
                        '[data-price]', '.amount'
                    ]
                    
                    price = None
                    for selector in price_selectors:
                        price_elem = element.select_one(selector)
                        if price_elem:
                            price_text = price_elem.get_text(strip=True)
                            # Extract numeric price
                            price_match = re.search(r'[\d,]+\.?\d*', price_text.replace(',', ''))
                            if price_match:
                                price = price_match.group().replace(',', '')
                            break
                    
                    # Extract image URLs
                    img_selectors = ['img', '[data-src]']
                    images = []
                    for selector in img_selectors:
                        img_elem = element.select_one(selector)
                        if img_elem:
                            src = img_elem.get('src') or img_elem.get('data-src')
                            if src:
                                images.append(urljoin(category_url, src))
                    
                    if name and url:
                        product = {
                            'name': name,
                            'url': url,
                            'price': price or '0',
                            'image_urls': images,
                            'category': 'Watch',  # Default for scraped watches
                            'scraped_at': time.time()
                        }
                        
                        # Get detailed information
                        details = self.extract_detailed_info(url)
                        product.update(details)
                        
                        # Enhance the product
                        enhanced_product = self.enhance_product_data(product)
                        products.append(enhanced_product)
                        
                        print(f"Scraped watch: {name}")
                        time.sleep(1)  # Be respectful to the server
                        
                except Exception as e:
                    print(f"Error processing product element: {e}")
                    continue
            
            return products
            
        except Exception as e:
            print(f"Error scraping {category_url}: {e}")
            return []
    
    def save_products(self, products: List[Dict]):
        """Save products to MongoDB"""
        if not products:
            return 0
        
        saved_count = 0
        for product in products:
            try:
                # Check if product already exists
                existing = self.collection.find_one({
                    "$or": [
                        {"url": product['url']},
                        {"name": product['name']}
                    ]
                })
                
                if existing:
                    # Update existing product
                    self.collection.replace_one(
                        {"_id": existing["_id"]},
                        product
                    )
                    print(f"Updated: {product['name']}")
                else:
                    # Insert new product
                    self.collection.insert_one(product)
                    print(f"Inserted: {product['name']}")
                
                saved_count += 1
                
            except Exception as e:
                print(f"Error saving product {product.get('name', 'Unknown')}: {e}")
        
        return saved_count
    
    def scrape_watch_categories(self, category_urls: List[str]) -> int:
        """Scrape multiple watch category pages"""
        total_scraped = 0
        
        for url in category_urls:
            print(f"\nScraping category: {url}")
            products = self.scrape_product_list(url)
            saved = self.save_products(products)
            total_scraped += saved
            print(f"Saved {saved} products from {url}")
            
            time.sleep(2)  # Delay between categories
        
        return total_scraped
    
    def close(self):
        """Close database connection"""
        self.client.close()

# Usage example
if __name__ == "__main__":
    MONGODB_URI = "mongodb://admin:strongpassword123@72.62.76.36:27017/?authSource=admin"
    
    scraper = EnhancedWatchScraper(MONGODB_URI)
    
    # Example watch category URLs (you'll need to replace with actual URLs)
    watch_categories = [
        "https://watchvine01.cartpe.in/categories/mens-watches",
        "https://watchvine01.cartpe.in/categories/womens-watches",
        "https://watchvine01.cartpe.in/categories/luxury-watches",
        "https://watchvine01.cartpe.in/categories/sport-watches"
    ]
    
    try:
        total = scraper.scrape_watch_categories(watch_categories)
        print(f"\nScraping completed! Total watches scraped: {total}")
        
    finally:
        scraper.close()