#!/usr/bin/env python3
"""
Complete AI Watch Enhancement System
Single file with all functionality for image-based field extraction using Google Gemini

Features:
- AI image analysis using Google Gemini 2.0 Flash
- Extract colors, styles, materials from watch images
- Batch processing with rate limiting
- Progress monitoring
- Database enhancement
- Error handling and recovery

Usage:
    python complete_ai_watch_enhancer.py
"""

import google.generativeai as genai
import requests
from PIL import Image
import io
import pymongo
from pymongo import MongoClient
import json
import time
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import re
import os
import sys

class CompleteAIWatchEnhancer:
    def __init__(self, mongodb_uri: str, google_api_key: str):
        """Initialize the AI Watch Enhancement System"""
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
        
        # Create indexes for better performance
        self._create_indexes()
        
        print(f"✅ AI Watch Enhancement System Initialized")
        print(f"🔗 Connected to MongoDB: {self.db.name}")
        print(f"🤖 Using Google Gemini: {self.model.model_name}")
    
    def _create_indexes(self):
        """Create database indexes for better search performance"""
        try:
            self.collection.create_index([("colors", 1)])
            self.collection.create_index([("styles", 1)])
            self.collection.create_index([("materials", 1)])
            self.collection.create_index([("ai_analysis.analyzed_at", -1)])
        except Exception as e:
            pass  # Indexes might already exist
    
    def download_and_prepare_image(self, image_url: str) -> Optional[Image.Image]:
        """Download and prepare image for AI analysis"""
        try:
            # Download image
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            response = requests.get(image_url, headers=headers, timeout=15)
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
            print(f"❌ Error downloading/preparing image {image_url}: {e}")
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
                print(f"⚠️ Could not extract JSON from response: {response_text[:100]}...")
                return self.get_empty_analysis()
                
        except Exception as e:
            print(f"❌ Error analyzing image with Gemini: {e}")
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
                    'silver': ['silver', 'stainless', 'steel', 'metallic', 'chrome'],
                    'gold': ['gold', 'golden', 'yellow gold', 'brass'],
                    'rose gold': ['rose gold', 'pink gold', 'copper', 'rose'],
                    'black': ['black', 'dark', 'charcoal'],
                    'white': ['white', 'light', 'pearl', 'ivory'],
                    'blue': ['blue', 'navy', 'royal blue', 'azure'],
                    'red': ['red', 'burgundy', 'wine', 'crimson'],
                    'green': ['green', 'olive', 'emerald', 'forest'],
                    'brown': ['brown', 'tan', 'cognac', 'bronze'],
                    'gray': ['gray', 'grey', 'slate', 'gunmetal']
                }
                
                # Style standardization
                style_mapping = {
                    'minimalistic': ['minimalistic', 'minimal', 'simple', 'clean', 'understated'],
                    'luxury': ['luxury', 'premium', 'elegant', 'sophisticated', 'high-end'],
                    'sporty': ['sporty', 'sport', 'athletic', 'racing', 'diving'],
                    'casual': ['casual', 'everyday', 'informal', 'relaxed'],
                    'formal': ['formal', 'dress', 'business', 'professional', 'classic'],
                    'vintage': ['vintage', 'retro', 'classic', 'heritage', 'traditional'],
                    'modern': ['modern', 'contemporary', 'futuristic', 'innovative'],
                    'smartwatch': ['smart', 'digital', 'fitness', 'connected', 'wearable']
                }
                
                # Material standardization
                material_mapping = {
                    'leather': ['leather', 'genuine leather', 'cowhide'],
                    'metal': ['metal', 'steel', 'stainless steel', 'alloy'],
                    'rubber': ['rubber', 'silicone', 'elastomer'],
                    'ceramic': ['ceramic', 'high-tech ceramic'],
                    'titanium': ['titanium', 'ti'],
                    'fabric': ['fabric', 'canvas', 'nylon', 'textile', 'nato'],
                    'gold': ['gold', 'yellow gold', 'white gold'],
                    'silver': ['silver', 'sterling silver']
                }
                
                # Apply mappings
                standardized = None
                all_mappings = {**color_mapping, **style_mapping, **material_mapping}
                
                for standard, variants in all_mappings.items():
                    if clean_item in variants or any(variant in clean_item for variant in variants):
                        standardized = standard.title()
                        break
                
                if standardized:
                    if standardized not in cleaned:
                        cleaned.append(standardized)
                else:
                    # If not in mapping, use title case
                    title_item = item.strip().title()
                    if title_item not in cleaned and len(title_item) > 2:
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
    
    def enhance_watch_with_ai(self, watch: Dict) -> Tuple[Dict, bool]:
        """Enhance a single watch product with AI image analysis"""
        watch_name = watch.get('name', 'Unknown')
        image_urls = watch.get('image_urls', [])
        
        if not image_urls:
            print(f"⚠️ No images found for {watch_name}")
            return watch, False
        
        print(f"🔍 Analyzing images for: {watch_name}")
        
        # Analyze the first image (main product image)
        main_image_url = image_urls[0]
        image = self.download_and_prepare_image(main_image_url)
        
        if image is None:
            print(f"❌ Could not process image for {watch_name}")
            return watch, False
        
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
                    'additional_details': analysis.get('additional_details', {}),
                    'api_model': 'gemini-2.0-flash'
                }
            })
            
            print(f"✅ Enhanced {watch_name}:")
            print(f"   🎨 Colors: {analysis['colors']}")
            print(f"   ✨ Styles: {analysis['styles']}")
            print(f"   🔧 Materials: {analysis['materials']}")
            
            return enhanced_watch, True
        else:
            print(f"❌ No analysis results for {watch_name}")
            return watch, False
    
    def get_watches_needing_enhancement(self, limit: Optional[int] = None) -> List[Dict]:
        """Get watches that need AI enhancement"""
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
        
        cursor = self.collection.find(query)
        if limit:
            cursor = cursor.limit(limit)
        
        return list(cursor)
    
    def enhance_batch(self, watches: List[Dict], batch_name: str = "Batch") -> Tuple[int, int]:
        """Enhance a batch of watches"""
        processed = 0
        enhanced = 0
        
        print(f"🚀 Processing {batch_name}: {len(watches)} watches")
        print("-" * 60)
        
        for i, watch in enumerate(watches, 1):
            try:
                enhanced_watch, success = self.enhance_watch_with_ai(watch)
                
                if success:
                    # Update in database
                    result = self.collection.replace_one(
                        {"_id": watch["_id"]},
                        enhanced_watch
                    )
                    
                    if result.modified_count > 0:
                        enhanced += 1
                
                processed += 1
                
                # Progress update
                if processed % 10 == 0:
                    print(f"📊 Progress: {processed}/{len(watches)} processed, {enhanced} enhanced")
                
                # Rate limiting for API
                time.sleep(2)  # 2 seconds between requests
                
            except KeyboardInterrupt:
                print(f"\n⏹️ Batch interrupted by user")
                break
            except Exception as e:
                print(f"❌ Error processing watch {watch.get('name', 'Unknown')}: {e}")
                continue
        
        print(f"\n✅ {batch_name} Complete!")
        print(f"📈 Processed: {processed}, Enhanced: {enhanced}")
        
        return processed, enhanced
    
    def enhance_all_watches(self, batch_size: int = 20, total_limit: Optional[int] = None):
        """Enhance all watches with AI image analysis"""
        print(f"🔍 Finding watches that need enhancement...")
        
        watches_to_process = self.get_watches_needing_enhancement(total_limit)
        total_watches = len(watches_to_process)
        
        if total_watches == 0:
            print(f"✅ All watches are already enhanced!")
            return 0, 0
        
        print(f"📊 Found {total_watches} watches that need AI enhancement")
        
        if total_limit:
            print(f"🎯 Processing limited to {total_limit} watches")
        
        total_processed = 0
        total_enhanced = 0
        
        # Process in batches
        for i in range(0, total_watches, batch_size):
            batch_end = min(i + batch_size, total_watches)
            batch_watches = watches_to_process[i:batch_end]
            batch_num = (i // batch_size) + 1
            total_batches = (total_watches + batch_size - 1) // batch_size
            
            batch_name = f"Batch {batch_num}/{total_batches}"
            
            processed, enhanced = self.enhance_batch(batch_watches, batch_name)
            total_processed += processed
            total_enhanced += enhanced
            
            # Break if user interrupted
            if processed < len(batch_watches):
                break
            
            # Longer delay between batches
            if i + batch_size < total_watches:
                print(f"⏱️ Waiting 10 seconds before next batch...")
                time.sleep(10)
        
        print(f"\n🎉 AI Enhancement Complete!")
        print(f"📈 Total processed: {total_processed}")
        print(f"✅ Successfully enhanced: {total_enhanced}")
        
        return total_processed, total_enhanced
    
    def get_enhancement_summary(self):
        """Get comprehensive summary of AI-enhanced watches"""
        # Count AI-enhanced watches
        ai_enhanced = self.collection.count_documents({"ai_analysis": {"$exists": True}})
        total_watches = self.collection.count_documents({})
        
        # Count watches with extracted fields
        with_colors = self.collection.count_documents({"colors": {"$ne": []}})
        with_styles = self.collection.count_documents({"styles": {"$ne": []}})
        with_materials = self.collection.count_documents({"materials": {"$ne": []}})
        
        # Count watches still needing enhancement
        needs_enhancement = len(self.get_watches_needing_enhancement())
        
        print(f"\n" + "="*60)
        print(f"📊 AI ENHANCEMENT SUMMARY")
        print(f"="*60)
        print(f"Total watches: {total_watches}")
        print(f"AI-enhanced: {ai_enhanced}")
        print(f"With colors: {with_colors}")
        print(f"With styles: {with_styles}")
        print(f"With materials: {with_materials}")
        print(f"Still need enhancement: {needs_enhancement}")
        print(f"Completion: {((ai_enhanced / total_watches) * 100):.1f}%")
        
        # Show recent enhancements
        recent = list(self.collection.find(
            {"ai_analysis.analyzed_at": {"$exists": True}},
            {"name": 1, "colors": 1, "styles": 1, "materials": 1, "ai_analysis.analyzed_at": 1}
        ).sort("ai_analysis.analyzed_at", -1).limit(5))
        
        if recent:
            print(f"\n🆕 Recently Enhanced:")
            for watch in recent:
                name = watch.get('name', 'Unknown')[:35]
                colors = ', '.join(watch.get('colors', [])[:3])
                styles = ', '.join(watch.get('styles', [])[:2])
                print(f"  • {name}: {colors} | {styles}")
        
        # Show top extracted values with better formatting
        print(f"\n🎨 Top Colors Extracted:")
        colors_agg = list(self.collection.aggregate([
            {"$unwind": "$colors"},
            {"$group": {"_id": "$colors", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 10}
        ]))
        
        for item in colors_agg[:8]:
            print(f"  {item['_id']}: {item['count']}")
        
        print(f"\n✨ Top Styles Extracted:")
        styles_agg = list(self.collection.aggregate([
            {"$unwind": "$styles"},
            {"$group": {"_id": "$styles", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 10}
        ]))
        
        for item in styles_agg[:8]:
            print(f"  {item['_id']}: {item['count']}")
        
        print(f"\n🔧 Top Materials Extracted:")
        materials_agg = list(self.collection.aggregate([
            {"$unwind": "$materials"},
            {"$group": {"_id": "$materials", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 10}
        ]))
        
        for item in materials_agg[:8]:
            print(f"  {item['_id']}: {item['count']}")
        
        print(f"\n" + "="*60)
    
    def test_ai_analysis(self, num_samples: int = 3):
        """Test AI analysis on sample watches"""
        print(f"🧪 Testing AI analysis on {num_samples} sample watches")
        print("-" * 60)
        
        # Get sample watches
        watches = self.get_watches_needing_enhancement(num_samples)
        
        if not watches:
            print(f"⚠️ No watches found for testing")
            return
        
        for i, watch in enumerate(watches, 1):
            print(f"🔍 Test {i}: {watch['name']}")
            print(f"Current state:")
            print(f"  Colors: {watch.get('colors', [])}")
            print(f"  Styles: {watch.get('styles', [])}")
            print(f"  Materials: {watch.get('materials', [])}")
            
            enhanced_watch, success = self.enhance_watch_with_ai(watch)
            
            if success:
                print(f"✅ AI Analysis Results:")
                print(f"  Colors: {enhanced_watch['colors']}")
                print(f"  Styles: {enhanced_watch['styles']}")
                print(f"  Materials: {enhanced_watch['materials']}")
                if enhanced_watch['ai_analysis']['additional_details']:
                    print(f"  Details: {enhanced_watch['ai_analysis']['additional_details']}")
            else:
                print(f"❌ AI analysis failed")
            
            print("-" * 60)
            
            if i < len(watches):
                time.sleep(2)
        
        print(f"✅ Testing complete!")
    
    def monitor_progress(self):
        """Display current enhancement progress"""
        print(f"🔍 AI Enhancement Progress Monitor")
        print(f"Time: {datetime.now().strftime('%H:%M:%S')}")
        print("=" * 50)
        
        # Get current stats
        total_watches = self.collection.count_documents({})
        ai_enhanced = self.collection.count_documents({"ai_analysis": {"$exists": True}})
        
        with_colors = self.collection.count_documents({"colors": {"$ne": []}})
        with_styles = self.collection.count_documents({"styles": {"$ne": []}})
        with_materials = self.collection.count_documents({"materials": {"$ne": []}})
        
        needs_enhancement = len(self.get_watches_needing_enhancement())
        
        print(f"📊 Current Stats:")
        print(f"Total watches: {total_watches}")
        print(f"AI-enhanced: {ai_enhanced}")
        print(f"With colors: {with_colors}")
        print(f"With styles: {with_styles}")
        print(f"With materials: {with_materials}")
        print(f"Still need enhancement: {needs_enhancement}")
        print(f"Completion: {((ai_enhanced / total_watches) * 100):.1f}%")
        
        # Progress bar
        progress = int((ai_enhanced / total_watches) * 40)
        bar = "█" * progress + "░" * (40 - progress)
        print(f"Progress: [{bar}] {((ai_enhanced / total_watches) * 100):.1f}%")
    
    def close(self):
        """Close database connection"""
        self.client.close()
        print(f"🔐 Database connection closed")

def main():
    """Main function with interactive menu"""
    # Configuration
    MONGODB_URI = "mongodb://admin:strongpassword123@72.62.76.36:27017/?authSource=admin"
    GOOGLE_API_KEY = "AIzaSyBZ8shurgeNDiDj4TlpBk7RUgrQ-G2mJ_0"
    
    print("🤖 Complete AI Watch Enhancement System")
    print("="*50)
    
    # Initialize the enhancer
    try:
        enhancer = CompleteAIWatchEnhancer(MONGODB_URI, GOOGLE_API_KEY)
    except Exception as e:
        print(f"❌ Failed to initialize system: {e}")
        return
    
    try:
        while True:
            print(f"\n📋 What would you like to do?")
            print(f"1. 🧪 Test AI analysis (3 samples)")
            print(f"2. 📊 Monitor current progress")
            print(f"3. 🚀 Small batch (50 watches)")
            print(f"4. 📈 Medium batch (200 watches)")
            print(f"5. 🎯 Large batch (500 watches)")
            print(f"6. 🌟 Full enhancement (all remaining)")
            print(f"7. 📑 Show summary")
            print(f"8. 🚪 Exit")
            
            choice = input(f"\nEnter your choice (1-8): ").strip()
            
            if choice == "1":
                enhancer.test_ai_analysis(3)
            
            elif choice == "2":
                enhancer.monitor_progress()
            
            elif choice == "3":
                print(f"🚀 Starting small batch enhancement (50 watches)...")
                enhancer.enhance_all_watches(batch_size=10, total_limit=50)
            
            elif choice == "4":
                print(f"📈 Starting medium batch enhancement (200 watches)...")
                enhancer.enhance_all_watches(batch_size=20, total_limit=200)
            
            elif choice == "5":
                print(f"🎯 Starting large batch enhancement (500 watches)...")
                enhancer.enhance_all_watches(batch_size=25, total_limit=500)
            
            elif choice == "6":
                confirm = input(f"⚠️ This will process ALL remaining watches. Continue? (y/N): ").strip().lower()
                if confirm in ['y', 'yes']:
                    print(f"🌟 Starting full enhancement...")
                    enhancer.enhance_all_watches(batch_size=30)
                else:
                    print(f"❌ Full enhancement cancelled")
            
            elif choice == "7":
                enhancer.get_enhancement_summary()
            
            elif choice == "8":
                print(f"👋 Exiting...")
                break
            
            else:
                print(f"❌ Invalid choice. Please enter 1-8.")
    
    except KeyboardInterrupt:
        print(f"\n⏹️ Process interrupted by user")
    
    finally:
        enhancer.close()

if __name__ == "__main__":
    main()