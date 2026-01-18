#!/usr/bin/env python3
"""
AI Image-based Watch Enhancement System using Google Gemini
Analyzes watch images to extract colors, styles, and materials
"""

import google.generativeai as genai
import requests
from PIL import Image
import io
import pymongo
from pymongo import MongoClient
import json
import time
from typing import Dict, List, Optional
from datetime import datetime
import re

class AIWatchImageEnhancer:
    def __init__(self, mongodb_uri: str, google_api_key: str):
        # Configure Google Gemini API
        genai.configure(api_key=google_api_key)
        self.model = genai.GenerativeModel('gemini-2.0-flash')
        
        # MongoDB setup
        self.mongodb_uri = mongodb_uri
        self.client = MongoClient(mongodb_uri)
        self.db = self.client['watchvine_refined']
        self.collection = self.db['products']
        
        # Analysis prompt for Gemini
        self.analysis_prompt = """
        Analyze this watch image and extract the following information in JSON format:

        {
            "colors": ["list of primary colors visible in the watch (e.g., black, silver, gold, blue, etc.)"],
            "styles": ["list of style characteristics (e.g., minimalistic, luxury, sporty, casual, formal, vintage, modern, etc.)"],
            "materials": ["list of materials visible (e.g., leather, metal, steel, rubber, ceramic, fabric, etc.)"],
            "additional_details": {
                "dial_color": "color of the watch face",
                "strap_type": "type of strap/bracelet",
                "watch_type": "analog/digital/smartwatch",
                "design_elements": ["notable design features"]
            }
        }

        Guidelines:
        - Colors: Focus on dominant colors of case, dial, and strap
        - Styles: Determine overall aesthetic (luxury, sporty, minimalistic, etc.)
        - Materials: Identify visible materials from case, strap, and dial
        - Be specific and accurate
        - Only include what you can clearly see
        - Use standard color names (black, white, silver, gold, blue, red, green, brown, etc.)
        
        Return only valid JSON, no additional text.
        """
    
    def download_and_prepare_image(self, image_url: str) -> Optional[Image.Image]:
        """Download and prepare image for AI analysis"""
        try:
            # Download image
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            response = requests.get(image_url, headers=headers, timeout=10)
            response.raise_for_status()
            
            # Open and prepare image
            image = Image.open(io.BytesIO(response.content))
            
            # Convert to RGB if needed
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Resize if too large (to save API costs)
            max_size = 1024
            if max(image.size) > max_size:
                image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            
            return image
            
        except Exception as e:
            print(f"Error downloading/preparing image {image_url}: {e}")
            return None
    
    def analyze_watch_image(self, image: Image.Image) -> Dict:
        """Analyze watch image using Gemini AI"""
        try:
            # Generate content using Gemini
            response = self.model.generate_content([
                self.analysis_prompt,
                image
            ])
            
            # Parse the JSON response
            response_text = response.text.strip()
            
            # Clean up the response (sometimes AI adds extra text)
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_text = response_text[json_start:json_end]
                analysis = json.loads(json_text)
                
                # Validate and clean the data
                cleaned_analysis = {
                    'colors': self.clean_array_field(analysis.get('colors', [])),
                    'styles': self.clean_array_field(analysis.get('styles', [])),
                    'materials': self.clean_array_field(analysis.get('materials', [])),
                    'additional_details': analysis.get('additional_details', {})
                }
                
                return cleaned_analysis
            else:
                print(f"Could not extract JSON from response: {response_text}")
                return self.get_empty_analysis()
                
        except Exception as e:
            print(f"Error analyzing image with Gemini: {e}")
            return self.get_empty_analysis()
    
    def clean_array_field(self, field_data: List) -> List[str]:
        """Clean and standardize array fields"""
        if not isinstance(field_data, list):
            return []
        
        cleaned = []
        for item in field_data:
            if isinstance(item, str) and item.strip():
                # Standardize the item
                clean_item = item.strip().lower()
                
                # Color standardization
                color_mapping = {
                    'silver': ['silver', 'stainless', 'steel', 'metallic'],
                    'gold': ['gold', 'golden', 'yellow gold'],
                    'rose gold': ['rose gold', 'pink gold', 'copper'],
                    'black': ['black', 'dark'],
                    'white': ['white', 'light'],
                    'blue': ['blue', 'navy'],
                    'red': ['red', 'burgundy', 'wine'],
                    'green': ['green', 'olive'],
                    'brown': ['brown', 'tan', 'cognac'],
                    'gray': ['gray', 'grey', 'charcoal']
                }
                
                # Style standardization
                style_mapping = {
                    'minimalistic': ['minimalistic', 'minimal', 'simple', 'clean'],
                    'luxury': ['luxury', 'premium', 'elegant', 'sophisticated'],
                    'sporty': ['sporty', 'sport', 'athletic', 'racing'],
                    'casual': ['casual', 'everyday', 'informal'],
                    'formal': ['formal', 'dress', 'business', 'professional'],
                    'vintage': ['vintage', 'retro', 'classic'],
                    'modern': ['modern', 'contemporary', 'futuristic']
                }
                
                # Material standardization
                material_mapping = {
                    'leather': ['leather', 'genuine leather'],
                    'metal': ['metal', 'steel', 'stainless steel'],
                    'rubber': ['rubber', 'silicone'],
                    'ceramic': ['ceramic'],
                    'titanium': ['titanium'],
                    'fabric': ['fabric', 'canvas', 'nylon']
                }
                
                # Apply mappings
                standardized = None
                for standard, variants in {**color_mapping, **style_mapping, **material_mapping}.items():
                    if clean_item in variants:
                        standardized = standard.title()
                        break
                
                if standardized:
                    if standardized not in cleaned:
                        cleaned.append(standardized)
                else:
                    # If not in mapping, use title case
                    title_item = item.strip().title()
                    if title_item not in cleaned:
                        cleaned.append(title_item)
        
        return cleaned[:5]  # Limit to 5 items max
    
    def get_empty_analysis(self) -> Dict:
        """Return empty analysis structure"""
        return {
            'colors': [],
            'styles': [],
            'materials': [],
            'additional_details': {}
        }
    
    def enhance_watch_with_ai(self, watch: Dict) -> Dict:
        """Enhance a single watch product with AI image analysis"""
        watch_name = watch.get('name', 'Unknown')
        image_urls = watch.get('image_urls', [])
        
        if not image_urls:
            print(f"No images found for {watch_name}")
            return watch
        
        print(f"Analyzing images for: {watch_name}")
        
        # Analyze the first image (main product image)
        main_image_url = image_urls[0]
        image = self.download_and_prepare_image(main_image_url)
        
        if image is None:
            print(f"Could not process image for {watch_name}")
            return watch
        
        # Analyze with AI
        analysis = self.analyze_watch_image(image)
        
        if analysis and (analysis['colors'] or analysis['styles'] or analysis['materials']):
            # Update watch with AI analysis
            enhanced_watch = watch.copy()
            enhanced_watch.update({
                'colors': analysis['colors'],
                'styles': analysis['styles'],
                'materials': analysis['materials'],
                'ai_analysis': {
                    'analyzed_at': datetime.now().isoformat(),
                    'image_analyzed': main_image_url,
                    'additional_details': analysis.get('additional_details', {})
                }
            })
            
            print(f"✅ Enhanced {watch_name}:")
            print(f"   Colors: {analysis['colors']}")
            print(f"   Styles: {analysis['styles']}")
            print(f"   Materials: {analysis['materials']}")
            
            return enhanced_watch
        else:
            print(f"❌ No analysis results for {watch_name}")
            return watch
    
    def enhance_all_watches(self, batch_size: int = 10, limit: Optional[int] = None):
        """Enhance all watches with AI image analysis"""
        # Find watches that need AI enhancement (empty colors, styles, materials)
        query = {
            "$or": [
                {"colors": {"$exists": False}},
                {"colors": {"$size": 0}},
                {"styles": {"$exists": False}},
                {"styles": {"$size": 0}},
                {"materials": {"$exists": False}},
                {"materials": {"$size": 0}},
                {"ai_analysis": {"$exists": False}}
            ],
            "image_urls": {"$exists": True, "$ne": []}
        }
        
        total_watches = self.collection.count_documents(query)
        print(f"Found {total_watches} watches that need AI enhancement")
        
        if limit:
            total_watches = min(total_watches, limit)
            print(f"Processing limited to {limit} watches")
        
        processed = 0
        enhanced = 0
        
        cursor = self.collection.find(query)
        if limit:
            cursor = cursor.limit(limit)
        
        for watch in cursor:
            try:
                enhanced_watch = self.enhance_watch_with_ai(watch)
                
                # Update in database
                result = self.collection.replace_one(
                    {"_id": watch["_id"]},
                    enhanced_watch
                )
                
                if result.modified_count > 0:
                    enhanced += 1
                
                processed += 1
                
                # Progress update
                if processed % batch_size == 0:
                    print(f"\n📊 Progress: {processed}/{total_watches} processed, {enhanced} enhanced")
                    time.sleep(2)  # Rate limiting for API
                
                # Small delay between requests
                time.sleep(1)
                
            except Exception as e:
                print(f"Error processing watch {watch.get('name', 'Unknown')}: {e}")
                continue
        
        print(f"\n🎉 AI Enhancement Complete!")
        print(f"📈 Total processed: {processed}")
        print(f"✅ Successfully enhanced: {enhanced}")
        
        return processed, enhanced
    
    def get_enhancement_summary(self):
        """Get summary of AI-enhanced watches"""
        # Count AI-enhanced watches
        ai_enhanced = self.collection.count_documents({"ai_analysis": {"$exists": True}})
        
        # Count watches with extracted fields
        with_colors = self.collection.count_documents({"colors": {"$ne": []}})
        with_styles = self.collection.count_documents({"styles": {"$ne": []}})
        with_materials = self.collection.count_documents({"materials": {"$ne": []}})
        
        print(f"\n=== AI ENHANCEMENT SUMMARY ===")
        print(f"AI-enhanced watches: {ai_enhanced}")
        print(f"Watches with colors: {with_colors}")
        print(f"Watches with styles: {with_styles}")
        print(f"Watches with materials: {with_materials}")
        
        # Show top extracted values
        colors_agg = list(self.collection.aggregate([
            {"$unwind": "$colors"},
            {"$group": {"_id": "$colors", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 10}
        ]))
        
        styles_agg = list(self.collection.aggregate([
            {"$unwind": "$styles"},
            {"$group": {"_id": "$styles", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 10}
        ]))
        
        materials_agg = list(self.collection.aggregate([
            {"$unwind": "$materials"},
            {"$group": {"_id": "$materials", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 10}
        ]))
        
        if colors_agg:
            print(f"\nTop Colors:")
            for item in colors_agg:
                print(f"  {item['_id']}: {item['count']}")
        
        if styles_agg:
            print(f"\nTop Styles:")
            for item in styles_agg:
                print(f"  {item['_id']}: {item['count']}")
        
        if materials_agg:
            print(f"\nTop Materials:")
            for item in materials_agg:
                print(f"  {item['_id']}: {item['count']}")
    
    def close(self):
        """Close database connection"""
        self.client.close()

# Usage script
if __name__ == "__main__":
    MONGODB_URI = "mongodb://admin:strongpassword123@72.62.76.36:27017/?authSource=admin"
    GOOGLE_API_KEY = "AIzaSyBZ8shurgeNDiDj4TlpBk7RUgrQ-G2mJ_0"
    
    enhancer = AIWatchImageEnhancer(MONGODB_URI, GOOGLE_API_KEY)
    
    try:
        print("🚀 Starting AI Image Enhancement...")
        
        # Enhance watches (start with a small batch for testing)
        processed, enhanced = enhancer.enhance_all_watches(batch_size=5, limit=20)
        
        # Show summary
        enhancer.get_enhancement_summary()
        
    finally:
        enhancer.close()