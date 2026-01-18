#!/usr/bin/env python3
"""
Watch Database Enhancement System
Automatically extracts brand, color, style, and other attributes from watch names and URLs
"""

import pymongo
from pymongo import MongoClient
import re
import requests
from typing import Dict, List, Optional
import time
import json
from datetime import datetime

class WatchEnhancer:
    def __init__(self, mongodb_uri: str):
        self.mongodb_uri = mongodb_uri
        self.client = MongoClient(mongodb_uri)
        self.db = self.client['watchvine_refined']
        self.collection = self.db['products']
        
        # Enhanced patterns for better extraction
        self.brand_patterns = {
            'audemars_piguet': r'\b(audemars[_\s]*piguet|ap)\b',
            'patek_philippe': r'\b(patek[_\s]*philippe|pp)\b',
            'franck_muller': r'\b(franck[_\s]*muller|fm)\b',
            'rolex': r'\b(rolex|rlx)\b',
            'omega': r'\b(omega|omg)\b',
            'tag_heuer': r'\b(tag[_\s]*heuer|th)\b',
            'breitling': r'\b(breitling|brt)\b',
            'cartier': r'\b(cartier|cart)\b',
            'iwc': r'\b(iwc)\b',
            'jaeger_lecoultre': r'\b(jaeger[_\s]*lecoultre|jlc)\b',
            'vacheron_constantin': r'\b(vacheron[_\s]*constantin|vc)\b',
            'panerai': r'\b(panerai|pan)\b',
            'hublot': r'\b(hublot|hub)\b',
            'richard_mille': r'\b(richard[_\s]*mille|rm)\b',
            'casio': r'\b(casio|cas)\b',
            'seiko': r'\b(seiko|sei)\b',
            'citizen': r'\b(citizen|cit)\b',
            'tissot': r'\b(tissot|tis)\b',
            'hamilton': r'\b(hamilton|ham)\b',
            'fossil': r'\b(fossil|fos)\b',
            'daniel_wellington': r'\b(daniel[_\s]*wellington|dw)\b',
            'mvmt': r'\b(mvmt|movement)\b',
            'nixon': r'\b(nixon|nix)\b',
            'timex': r'\b(timex|tim)\b',
            'bulova': r'\b(bulova|bul)\b',
            'invicta': r'\b(invicta|inv)\b',
            'diesel': r'\b(diesel|die)\b',
            'armani': r'\b(armani|arm|emporio[_\s]*armani)\b',
            'gucci': r'\b(gucci|guc)\b',
            'versace': r'\b(versace|ver)\b',
            'boss': r'\b(boss|hugo[_\s]*boss)\b',
            'calvin_klein': r'\b(calvin[_\s]*klein|ck)\b',
            'tommy_hilfiger': r'\b(tommy[_\s]*hilfiger|th)\b',
            'michael_kors': r'\b(michael[_\s]*kors|mk)\b',
            'apple': r'\b(apple|iwatch)\b',
            'samsung': r'\b(samsung|galaxy[_\s]*watch)\b',
            'garmin': r'\b(garmin|gar)\b',
            'fitbit': r'\b(fitbit|fit)\b',
            'amazfit': r'\b(amazfit|amz)\b',
            'fire_boltt': r'\b(fire[_\s]*boltt|fireboltt)\b',
            'noise': r'\b(noise|noi)\b',
            'boat': r'\b(boat|bot)\b',
            'fastrack': r'\b(fastrack|fas)\b',
            'titan': r'\b(titan|tit)\b',
            'sonata': r'\b(sonata|son)\b',
            'maxima': r'\b(maxima|max)\b',
            'maybach': r'\b(maybach|may)\b'
        }
        
        self.color_patterns = {
            'black': r'\b(black|nero|schwarz|noir)\b',
            'white': r'\b(white|bianco|weiß|blanc|pearl)\b',
            'silver': r'\b(silver|argento|silber|argent|steel|stainless)\b',
            'gold': r'\b(gold|oro|gelb|or|yellow[_\s]*gold)\b',
            'rose_gold': r'\b(rose[_\s]*gold|pink[_\s]*gold|red[_\s]*gold)\b',
            'blue': r'\b(blue|blu|blau|bleu|navy|royal[_\s]*blue)\b',
            'red': r'\b(red|rosso|rot|rouge|burgundy|wine)\b',
            'green': r'\b(green|verde|grün|vert|olive|forest)\b',
            'brown': r'\b(brown|marrone|braun|brun|tan|cognac|leather)\b',
            'gray': r'\b(gray|grey|grigio|grau|gris|charcoal|slate)\b',
            'pink': r'\b(pink|rosa|rose|rose)\b',
            'purple': r'\b(purple|viola|lila|violet|lavender)\b',
            'orange': r'\b(orange|arancione|orange|coral)\b',
            'yellow': r'\b(yellow|giallo|gelb|jaune|golden)\b',
            'bronze': r'\b(bronze|bronzo|bronze)\b',
            'copper': r'\b(copper|rame|kupfer|cuivre)\b',
            'titanium': r'\b(titanium|titanio|titan)\b'
        }
        
        self.style_patterns = {
            'minimalistic': r'\b(minimal|minimalist|simple|clean|sleek|elegant|refined|classic|understated)\b',
            'sporty': r'\b(sport|sporty|athletic|diving|diver|racing|chronograph|tactical|rugged|outdoor)\b',
            'luxury': r'\b(luxury|premium|prestige|exclusive|haute|high[_\s]*end|elite|sophisticated)\b',
            'casual': r'\b(casual|everyday|daily|comfort|relaxed|informal)\b',
            'formal': r'\b(formal|dress|business|professional|office|executive|corporate)\b',
            'vintage': r'\b(vintage|retro|classic|heritage|traditional|antique)\b',
            'modern': r'\b(modern|contemporary|futuristic|innovative|cutting[_\s]*edge)\b',
            'smartwatch': r'\b(smart|digital|fitness|health|connected|wearable|tech)\b'
        }
        
        self.material_patterns = {
            'leather': r'\b(leather|cuoio|leder|cuir|strap|band)\b',
            'metal': r'\b(metal|steel|stainless|bracelet|chain|mesh)\b',
            'rubber': r'\b(rubber|silicone|sport[_\s]*band|flex)\b',
            'fabric': r'\b(fabric|canvas|nylon|textile|cloth)\b',
            'ceramic': r'\b(ceramic|ceramica|keramik)\b',
            'titanium': r'\b(titanium|titanio|titan)\b',
            'gold': r'\b(gold|golden|oro)\b',
            'silver': r'\b(silver|argento|silber)\b'
        }
    
    def extract_brand(self, text: str) -> Optional[str]:
        """Extract brand from product name or URL"""
        text_lower = text.lower()
        for brand, pattern in self.brand_patterns.items():
            if re.search(pattern, text_lower):
                return brand.replace('_', ' ').title()
        return None
    
    def extract_colors(self, text: str) -> List[str]:
        """Extract colors from product name or URL"""
        text_lower = text.lower()
        colors = []
        for color, pattern in self.color_patterns.items():
            if re.search(pattern, text_lower):
                colors.append(color.replace('_', ' ').title())
        return colors
    
    def extract_style(self, text: str) -> List[str]:
        """Extract style/type from product name or URL"""
        text_lower = text.lower()
        styles = []
        for style, pattern in self.style_patterns.items():
            if re.search(pattern, text_lower):
                styles.append(style.title())
        return styles
    
    def extract_materials(self, text: str) -> List[str]:
        """Extract materials from product name or URL"""
        text_lower = text.lower()
        materials = []
        for material, pattern in self.material_patterns.items():
            if re.search(pattern, text_lower):
                materials.append(material.title())
        return materials
    
    def extract_gender(self, category: str, name: str = "") -> str:
        """Extract gender from category or name"""
        text = f"{category} {name}".lower()
        if re.search(r'\b(men|male|homme|masculino)\b', text):
            return "Men"
        elif re.search(r'\b(women|female|femme|feminino|ladies|lady)\b', text):
            return "Women"
        elif re.search(r'\b(unisex|universal|both)\b', text):
            return "Unisex"
        else:
            return "Unisex"  # Default
    
    def extract_price_range(self, price: str) -> str:
        """Categorize price range"""
        try:
            price_num = float(price)
            if price_num < 1000:
                return "Budget (Under ₹1000)"
            elif price_num < 2500:
                return "Mid-Range (₹1000-2500)"
            elif price_num < 5000:
                return "Premium (₹2500-5000)"
            else:
                return "Luxury (₹5000+)"
        except:
            return "Unknown"
    
    def enhance_watch_product(self, product: Dict) -> Dict:
        """Enhance a single watch product with extracted fields"""
        name = product.get('name', '')
        url = product.get('url', '')
        category = product.get('category', '')
        price = product.get('price', '0')
        
        # Combine text for analysis
        analysis_text = f"{name} {url} {category}"
        
        # Extract fields
        enhanced_product = product.copy()
        enhanced_product.update({
            'brand': self.extract_brand(analysis_text),
            'colors': self.extract_colors(analysis_text),
            'styles': self.extract_style(analysis_text),
            'materials': self.extract_materials(analysis_text),
            'gender': self.extract_gender(category, name),
            'price_range': self.extract_price_range(price),
            'enhanced_at': datetime.now().isoformat(),
            'searchable_text': f"{name} {category} {self.extract_brand(analysis_text) or ''} {' '.join(self.extract_colors(analysis_text))} {' '.join(self.extract_style(analysis_text))}".lower()
        })
        
        return enhanced_product
    
    def filter_only_watches(self) -> int:
        """Remove all non-watch products from database"""
        # Define what constitutes a watch
        watch_query = {
            "$or": [
                {"category": {"$regex": "watch", "$options": "i"}},
                {"name": {"$regex": "watch", "$options": "i"}},
                {"category": {"$in": ["Men's Watch", "Women's Watch", "Watch", "Watches"]}}
            ]
        }
        
        # Get non-watch products
        non_watch_query = {
            "$and": [
                {"$nor": [watch_query]},
                {"category": {"$not": {"$regex": "watch", "$options": "i"}}},
                {"name": {"$not": {"$regex": "watch", "$options": "i"}}}
            ]
        }
        
        # Count non-watch products
        non_watch_count = self.collection.count_documents(non_watch_query)
        print(f"Found {non_watch_count} non-watch products to remove")
        
        # Remove non-watch products
        if non_watch_count > 0:
            result = self.collection.delete_many(non_watch_query)
            print(f"Removed {result.deleted_count} non-watch products")
            return result.deleted_count
        
        return 0
    
    def enhance_all_watches(self, batch_size: int = 100):
        """Enhance all watch products in the database"""
        # First filter to only watches
        self.filter_only_watches()
        
        # Get all watch products
        watch_query = {
            "$or": [
                {"category": {"$regex": "watch", "$options": "i"}},
                {"name": {"$regex": "watch", "$options": "i"}},
            ]
        }
        
        total_watches = self.collection.count_documents(watch_query)
        print(f"Enhancing {total_watches} watch products...")
        
        processed = 0
        for watch in self.collection.find(watch_query):
            try:
                enhanced = self.enhance_watch_product(watch)
                
                # Update in database
                self.collection.replace_one(
                    {"_id": watch["_id"]},
                    enhanced
                )
                
                processed += 1
                if processed % batch_size == 0:
                    print(f"Processed {processed}/{total_watches} watches...")
                    time.sleep(0.1)  # Small delay to avoid overwhelming the database
                    
            except Exception as e:
                print(f"Error processing watch {watch.get('name', 'Unknown')}: {e}")
                continue
        
        print(f"Enhancement complete! Processed {processed} watches.")
        return processed
    
    def get_enhancement_summary(self):
        """Get summary of enhanced database"""
        total_watches = self.collection.count_documents({})
        
        # Aggregate by brand
        brands = self.collection.aggregate([
            {"$group": {"_id": "$brand", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 10}
        ])
        
        # Aggregate by gender
        genders = self.collection.aggregate([
            {"$group": {"_id": "$gender", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ])
        
        # Aggregate by price range
        price_ranges = self.collection.aggregate([
            {"$group": {"_id": "$price_range", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ])
        
        print(f"\n=== ENHANCEMENT SUMMARY ===")
        print(f"Total Watch Products: {total_watches}")
        
        print(f"\nTop Brands:")
        for brand in brands:
            print(f"  - {brand['_id'] or 'Unknown'}: {brand['count']}")
        
        print(f"\nGender Distribution:")
        for gender in genders:
            print(f"  - {gender['_id']}: {gender['count']}")
        
        print(f"\nPrice Range Distribution:")
        for price_range in price_ranges:
            print(f"  - {price_range['_id']}: {price_range['count']}")
    
    def close(self):
        """Close database connection"""
        self.client.close()

if __name__ == "__main__":
    # MongoDB connection
    MONGODB_URI = "mongodb://admin:strongpassword123@72.62.76.36:27017/?authSource=admin"
    
    enhancer = WatchEnhancer(MONGODB_URI)
    
    try:
        print("Starting watch database enhancement...")
        enhancer.enhance_all_watches()
        enhancer.get_enhancement_summary()
        
    finally:
        enhancer.close()