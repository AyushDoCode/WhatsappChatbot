#!/usr/bin/env python3
"""
Automatic AI Watch Enhancement System with Real-time Monitoring
Single file that automatically starts enhancing products with live progress display

Features:
- Automatic enhancement with real-time progress
- Enhanced belt/strap type detection (chain, leather, metal, etc.)
- Live scanning display
- Progress bars and statistics
- Google Gemini 2.0 Flash AI analysis

Usage:
    python auto_ai_watch_enhancer.py
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
import threading
from concurrent.futures import ThreadPoolExecutor

class AutoAIWatchEnhancer:
    def __init__(self, mongodb_uri: str, google_api_key: str):
        """Initialize the Auto AI Watch Enhancement System"""
        # Configure Google Gemini API
        genai.configure(api_key=google_api_key)
        self.model = genai.GenerativeModel('gemini-2.0-flash')
        
        # MongoDB setup
        self.mongodb_uri = mongodb_uri
        self.client = MongoClient(mongodb_uri)
        self.db = self.client['watchvine_refined']
        self.collection = self.db['products']
        
        # Progress tracking
        self.total_to_process = 0
        self.processed = 0
        self.enhanced = 0
        self.current_watch = ""
        self.start_time = datetime.now()
        self.is_running = False
        
        # Comprehensive analysis prompt for all fields
        self.analysis_prompt = """
        Analyze this watch image and extract the following information in JSON format:

        {
            "colors": ["list of ALL colors visible in the watch including case, dial, hands, markers, strap (e.g., black, silver, gold, blue, white, red, green, brown, rose_gold, etc.)"],
            "styles": ["list of style characteristics based on design aesthetics (e.g., minimalistic, luxury, sporty, casual, formal, vintage, modern, classic, contemporary, elegant, rugged, etc.)"],
            "materials": ["list of ALL materials visible including case, dial, hands, strap, crown (e.g., leather, metal, steel, stainless_steel, gold, silver, rubber, silicone, ceramic, titanium, fabric, canvas, etc.)"],
            "belt_type": "primary strap/belt type (leather_belt, chain_belt, metal_belt, steel_bracelet, rubber_belt, silicone_belt, fabric_belt, nato_belt, mesh_belt, ceramic_belt, hybrid_belt, rope_belt, etc.)",
            "category": "watch category based on design and purpose (luxury_watch, sport_watch, dress_watch, casual_watch, smart_watch, diving_watch, pilot_watch, racing_watch, business_watch, fashion_watch, etc.)",
            "gender_target": "target gender based on design (mens, womens, unisex)",
            "additional_details": {
                "dial_color": "primary color of the watch face",
                "dial_style": "dial design (analog, digital, chronograph, etc.)",
                "case_shape": "shape of watch case (round, square, rectangular, etc.)",
                "case_color": "color of the watch case",
                "strap_material": "specific strap/bracelet material",
                "strap_color": "color of the strap/bracelet",
                "watch_size": "apparent size (small, medium, large)",
                "complications": ["any visible complications (date, chronograph, etc.)"],
                "brand_style": "apparent brand category (luxury, mid-range, budget, sport, fashion)",
                "design_elements": ["notable design features (textured dial, luminous hands, etc.)"]
            }
        }

        COMPREHENSIVE ANALYSIS GUIDELINES:

        Colors (extract ALL visible colors):
        - Case colors: black, silver, gold, rose_gold, white, blue, etc.
        - Dial colors: black, white, blue, silver, gold, green, brown, etc.  
        - Strap colors: black, brown, silver, gold, blue, red, etc.
        - Accent colors: hands, markers, subdials, complications

        Styles (determine design aesthetics):
        - minimalistic: clean, simple, understated design
        - luxury: premium, elegant, sophisticated appearance
        - sporty: athletic, racing, diving, robust design
        - casual: everyday, informal, relaxed style
        - formal: dress, business, professional appearance
        - vintage: retro, classic, heritage design
        - modern: contemporary, futuristic, innovative
        - classic: timeless, traditional design

        Materials (identify ALL visible materials):
        - Case: steel, stainless_steel, gold, silver, titanium, ceramic, plastic
        - Dial: metal, mother_of_pearl, carbon_fiber, etc.
        - Strap: leather, metal, steel, rubber, silicone, fabric, canvas, nylon
        - Hardware: buckle, clasp materials

        Belt Types (primary strap type):
        - leather_belt: genuine leather, crocodile, alligator straps
        - metal_belt/steel_bracelet: steel links, metal bracelet
        - chain_belt: chain links, chainmail style
        - rubber_belt/silicone_belt: sport bands, rubber straps
        - fabric_belt/nato_belt: canvas, nylon, textile straps
        - mesh_belt: metal mesh, milanese bracelet
        - ceramic_belt: ceramic links
        - hybrid_belt: combination materials

        Category (watch purpose/type):
        - luxury_watch: high-end, premium watches
        - sport_watch: athletic, fitness, outdoor watches
        - dress_watch: formal, business, elegant watches
        - casual_watch: everyday, lifestyle watches
        - smart_watch: digital, connected watches
        - diving_watch: water-resistant, professional diving
        - pilot_watch: aviation-inspired watches
        - racing_watch: motorsport-inspired chronographs

        Analysis Rules:
        - Extract EVERYTHING you can see
        - Be comprehensive and detailed
        - Use specific color names
        - Include both primary and secondary elements
        - Focus on visible features only
        - Use consistent terminology
        
        Return only valid JSON, no additional text.
        """
        
        # Create indexes for better performance
        self._create_indexes()
        
        print(f"🤖 Auto AI Watch Enhancement System Initialized")
        print(f"🔗 Connected to MongoDB: {self.db.name}")
        print(f"🚀 Using Google Gemini: {self.model.model_name}")
    
    def _create_indexes(self):
        """Create database indexes for better search performance"""
        try:
            self.collection.create_index([("colors", 1)])
            self.collection.create_index([("styles", 1)])
            self.collection.create_index([("materials", 1)])
            self.collection.create_index([("belt_type", 1)])
            self.collection.create_index([("ai_analysis.analyzed_at", -1)])
        except Exception as e:
            pass  # Indexes might already exist
    
    def download_and_prepare_image(self, image_url: str) -> Optional[Image.Image]:
        """Download and prepare image for AI analysis"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            response = requests.get(image_url, headers=headers, timeout=15)
            response.raise_for_status()
            
            image = Image.open(io.BytesIO(response.content))
            
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Resize if too large
            max_size = 1024
            if max(image.size) > max_size:
                image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            
            return image
            
        except Exception as e:
            return None
    
    def analyze_watch_image(self, image: Image.Image) -> Dict:
        """Analyze watch image using Gemini AI"""
        try:
            response = self.model.generate_content([
                self.analysis_prompt,
                image
            ])
            
            response_text = response.text.strip()
            
            # Extract JSON from response
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_text = response_text[json_start:json_end]
                analysis = json.loads(json_text)
                
                # Clean and validate the data
                cleaned_analysis = {
                    'colors': self.clean_array_field(analysis.get('colors', [])),
                    'styles': self.clean_array_field(analysis.get('styles', [])),
                    'materials': self.clean_array_field(analysis.get('materials', [])),
                    'belt_type': self.clean_belt_type(analysis.get('belt_type', '')),
                    'category': self.clean_category(analysis.get('category', '')),
                    'gender_target': self.clean_gender(analysis.get('gender_target', '')),
                    'additional_details': analysis.get('additional_details', {})
                }
                
                return cleaned_analysis
            else:
                return self.get_empty_analysis()
                
        except Exception as e:
            return self.get_empty_analysis()
    
    def clean_belt_type(self, belt_type: str) -> str:
        """Clean and standardize belt type"""
        if not belt_type or not isinstance(belt_type, str):
            return "unknown"
        
        belt_lower = belt_type.lower().strip()
        
        # Belt type mapping
        belt_mapping = {
            'leather_belt': ['leather', 'genuine leather', 'cowhide', 'crocodile', 'alligator', 'calfskin'],
            'chain_belt': ['chain', 'chainmail', 'chain links', 'linked chain'],
            'metal_belt': ['metal', 'steel', 'stainless steel', 'bracelet', 'metal bracelet', 'steel bracelet'],
            'rubber_belt': ['rubber', 'silicone', 'sport band', 'elastomer'],
            'fabric_belt': ['fabric', 'nato', 'canvas', 'nylon', 'textile', 'cloth'],
            'ceramic_belt': ['ceramic', 'high-tech ceramic'],
            'mesh_belt': ['mesh', 'milanese', 'metal mesh'],
            'hybrid_belt': ['hybrid', 'combination', 'mixed'],
            'rope_belt': ['rope', 'braided', 'cord']
        }
        
        for standard_type, variants in belt_mapping.items():
            if any(variant in belt_lower for variant in variants):
                return standard_type
        
        return belt_lower.replace(' ', '_')
    
    def clean_category(self, category: str) -> str:
        """Clean and standardize watch category"""
        if not category or not isinstance(category, str):
            return "casual_watch"
        
        category_lower = category.lower().strip()
        
        # Category mapping
        category_mapping = {
            'luxury_watch': ['luxury', 'premium', 'high-end', 'prestige', 'elegant'],
            'sport_watch': ['sport', 'athletic', 'fitness', 'outdoor', 'racing', 'diving'],
            'dress_watch': ['dress', 'formal', 'business', 'professional', 'office'],
            'casual_watch': ['casual', 'everyday', 'lifestyle', 'fashion', 'basic'],
            'smart_watch': ['smart', 'digital', 'connected', 'fitness', 'wearable'],
            'diving_watch': ['diving', 'dive', 'underwater', 'water', 'marine'],
            'pilot_watch': ['pilot', 'aviation', 'aviator', 'flight'],
            'racing_watch': ['racing', 'motorsport', 'chronograph', 'speed'],
            'vintage_watch': ['vintage', 'retro', 'classic', 'heritage', 'traditional']
        }
        
        for standard_category, variants in category_mapping.items():
            if any(variant in category_lower for variant in variants):
                return standard_category
        
        return category_lower.replace(' ', '_')
    
    def clean_gender(self, gender: str) -> str:
        """Clean and standardize gender target"""
        if not gender or not isinstance(gender, str):
            return "unisex"
        
        gender_lower = gender.lower().strip()
        
        if any(term in gender_lower for term in ['men', 'male', 'gentleman']):
            return "mens"
        elif any(term in gender_lower for term in ['women', 'female', 'ladies', 'lady']):
            return "womens"
        else:
            return "unisex"
    
    def clean_array_field(self, field_data: List) -> List[str]:
        """Clean and standardize array fields"""
        if not isinstance(field_data, list):
            return []
        
        cleaned = []
        for item in field_data:
            if isinstance(item, str) and item.strip():
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
                    'minimalistic': ['minimalistic', 'minimal', 'simple', 'clean'],
                    'luxury': ['luxury', 'premium', 'elegant', 'sophisticated'],
                    'sporty': ['sporty', 'sport', 'athletic', 'racing', 'diving'],
                    'casual': ['casual', 'everyday', 'informal', 'relaxed'],
                    'formal': ['formal', 'dress', 'business', 'professional'],
                    'vintage': ['vintage', 'retro', 'classic', 'heritage'],
                    'modern': ['modern', 'contemporary', 'futuristic'],
                    'smartwatch': ['smart', 'digital', 'fitness', 'connected']
                }
                
                # Material standardization
                material_mapping = {
                    'leather': ['leather', 'genuine leather', 'cowhide'],
                    'metal': ['metal', 'steel', 'stainless steel', 'alloy'],
                    'rubber': ['rubber', 'silicone', 'elastomer'],
                    'ceramic': ['ceramic', 'high-tech ceramic'],
                    'titanium': ['titanium', 'ti'],
                    'fabric': ['fabric', 'canvas', 'nylon', 'nato'],
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
                    title_item = item.strip().title()
                    if title_item not in cleaned and len(title_item) > 2:
                        cleaned.append(title_item)
        
        return cleaned[:5]
    
    def get_empty_analysis(self) -> Dict:
        """Return empty analysis structure"""
        return {
            'colors': [],
            'styles': [],
            'materials': [],
            'belt_type': 'unknown',
            'category': 'casual_watch',
            'gender_target': 'unisex',
            'additional_details': {}
        }
    
    def enhance_watch_with_ai(self, watch: Dict) -> Tuple[Dict, bool]:
        """Enhance a single watch product with AI image analysis"""
        watch_name = watch.get('name', 'Unknown')
        image_urls = watch.get('image_urls', [])
        
        self.current_watch = watch_name
        
        if not image_urls:
            return watch, False
        
        # Download and analyze image
        main_image_url = image_urls[0]
        image = self.download_and_prepare_image(main_image_url)
        
        if image is None:
            return watch, False
        
        # Analyze with AI
        analysis = self.analyze_watch_image(image)
        
        if analysis and (analysis['colors'] or analysis['styles'] or analysis['materials'] or analysis['belt_type'] != 'unknown'):
            # Update watch with comprehensive AI analysis
            enhanced_watch = watch.copy()
            enhanced_watch.update({
                'colors': analysis['colors'],
                'styles': analysis['styles'],
                'materials': analysis['materials'],
                'belt_type': analysis['belt_type'],
                'ai_category': analysis['category'],
                'ai_gender_target': analysis['gender_target'],
                'ai_analysis': {
                    'analyzed_at': datetime.now().isoformat(),
                    'image_analyzed': main_image_url,
                    'additional_details': analysis.get('additional_details', {}),
                    'api_model': 'gemini-2.0-flash',
                    'analysis_version': '2.0'
                }
            })
            
            print(f"✅ Enhanced {watch_name}:")
            print(f"   🎨 Colors: {analysis['colors']}")
            print(f"   ✨ Styles: {analysis['styles']}")
            print(f"   🔧 Materials: {analysis['materials']}")
            print(f"   🔗 Belt Type: {analysis['belt_type']}")
            print(f"   📂 Category: {analysis['category']}")
            print(f"   👥 Gender: {analysis['gender_target']}")
            
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
                {"belt_type": {"$exists": False}},
                {"ai_analysis": {"$exists": False}}
            ],
            "image_urls": {"$exists": True, "$ne": []}
        }
        
        cursor = self.collection.find(query)
        if limit:
            cursor = cursor.limit(limit)
        
        return list(cursor)
    
    def display_progress(self):
        """Display real-time progress"""
        while self.is_running:
            # Clear screen
            os.system('cls' if os.name == 'nt' else 'clear')
            
            # Calculate progress
            progress_percent = (self.processed / max(self.total_to_process, 1)) * 100
            elapsed_time = datetime.now() - self.start_time
            
            # Estimate remaining time
            if self.processed > 0:
                avg_time_per_watch = elapsed_time.total_seconds() / self.processed
                remaining_watches = self.total_to_process - self.processed
                estimated_remaining = remaining_watches * avg_time_per_watch
                remaining_hours = int(estimated_remaining // 3600)
                remaining_mins = int((estimated_remaining % 3600) // 60)
                eta = f"{remaining_hours}h {remaining_mins}m"
            else:
                eta = "Calculating..."
            
            # Progress bar
            bar_length = 50
            filled_length = int(bar_length * progress_percent / 100)
            bar = "█" * filled_length + "░" * (bar_length - filled_length)
            
            # Display real-time status
            print("🤖 AUTO AI WATCH ENHANCEMENT - LIVE SCANNING")
            print("=" * 70)
            print(f"📊 Progress: [{bar}] {progress_percent:.1f}%")
            print(f"⏱️ Time Elapsed: {str(elapsed_time).split('.')[0]}")
            print(f"🕐 ETA: {eta}")
            print(f"📈 Stats: {self.processed}/{self.total_to_process} processed | {self.enhanced} enhanced")
            print(f"🔍 Currently Analyzing: {self.current_watch[:60]}...")
            print("=" * 70)
            
            # Recent stats
            total_watches = self.collection.count_documents({})
            ai_enhanced_total = self.collection.count_documents({"ai_analysis": {"$exists": True}})
            completion_percent = (ai_enhanced_total / max(total_watches, 1)) * 100
            
            print(f"🗃️ Database Status:")
            print(f"   Total Watches: {total_watches}")
            print(f"   AI Enhanced: {ai_enhanced_total}")
            print(f"   Overall Completion: {completion_percent:.1f}%")
            
            # Show recent enhancements
            recent = list(self.collection.find(
                {"ai_analysis.analyzed_at": {"$exists": True}},
                {"name": 1, "colors": 1, "styles": 1, "belt_type": 1}
            ).sort("ai_analysis.analyzed_at", -1).limit(3))
            
            if recent:
                print(f"\n🆕 Recently Enhanced:")
                for watch in recent:
                    name = watch.get('name', 'Unknown')[:30]
                    colors = ', '.join(watch.get('colors', [])[:2])
                    belt_type = watch.get('belt_type', 'unknown')
                    print(f"   • {name}: {colors} | {belt_type}")
            
            print(f"\n⏹️ Press Ctrl+C to stop")
            time.sleep(2)
    
    def auto_enhance_all(self, batch_size: int = 25, delay: float = 1.5):
        """Automatically enhance all watches with real-time display"""
        # Get watches to process
        watches_to_process = self.get_watches_needing_enhancement()
        self.total_to_process = len(watches_to_process)
        
        if self.total_to_process == 0:
            print("✅ All watches are already enhanced!")
            return
        
        print(f"🚀 Starting automatic enhancement of {self.total_to_process} watches")
        print(f"⏱️ Rate: 1 watch every {delay} seconds")
        print(f"📦 Processing in batches of {batch_size}")
        print(f"🕐 Estimated time: {(self.total_to_process * delay / 60):.1f} minutes")
        
        input("\n📋 Press Enter to start automatic enhancement...")
        
        self.is_running = True
        self.processed = 0
        self.enhanced = 0
        self.start_time = datetime.now()
        
        # Start progress display in separate thread
        progress_thread = threading.Thread(target=self.display_progress, daemon=True)
        progress_thread.start()
        
        try:
            # Process watches
            for i, watch in enumerate(watches_to_process):
                enhanced_watch, success = self.enhance_watch_with_ai(watch)
                
                if success:
                    # Update in database
                    result = self.collection.replace_one(
                        {"_id": watch["_id"]},
                        enhanced_watch
                    )
                    
                    if result.modified_count > 0:
                        self.enhanced += 1
                
                self.processed += 1
                
                # Rate limiting
                time.sleep(delay)
        
        except KeyboardInterrupt:
            print(f"\n⏹️ Enhancement stopped by user")
        
        finally:
            self.is_running = False
            time.sleep(1)  # Let progress display finish
            
            # Final summary
            os.system('cls' if os.name == 'nt' else 'clear')
            elapsed_time = datetime.now() - self.start_time
            
            print("🎉 AI ENHANCEMENT COMPLETED!")
            print("=" * 50)
            print(f"📈 Total Processed: {self.processed}")
            print(f"✅ Successfully Enhanced: {self.enhanced}")
            print(f"⏱️ Total Time: {str(elapsed_time).split('.')[0]}")
            print(f"⚡ Average Speed: {(self.processed / elapsed_time.total_seconds() * 60):.1f} watches/minute")
            
            # Show final statistics
            self.show_final_summary()
    
    def show_final_summary(self):
        """Show comprehensive final summary"""
        print(f"\n📊 FINAL DATABASE SUMMARY")
        print("=" * 50)
        
        # Get stats
        total_watches = self.collection.count_documents({})
        ai_enhanced = self.collection.count_documents({"ai_analysis": {"$exists": True}})
        with_colors = self.collection.count_documents({"colors": {"$ne": []}})
        with_styles = self.collection.count_documents({"styles": {"$ne": []}})
        with_materials = self.collection.count_documents({"materials": {"$ne": []}})
        with_belt_type = self.collection.count_documents({"belt_type": {"$exists": True, "$ne": "unknown"}})
        
        print(f"Total Watches: {total_watches}")
        print(f"AI Enhanced: {ai_enhanced} ({(ai_enhanced/total_watches*100):.1f}%)")
        print(f"With Colors: {with_colors}")
        print(f"With Styles: {with_styles}")
        print(f"With Materials: {with_materials}")
        print(f"With Belt Types: {with_belt_type}")
        
        # Top belt types
        print(f"\n🔗 Top Belt Types:")
        belt_types = list(self.collection.aggregate([
            {"$group": {"_id": "$belt_type", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 8}
        ]))
        
        for item in belt_types:
            if item['_id'] and item['_id'] != 'unknown':
                print(f"   {item['_id'].replace('_', ' ').title()}: {item['count']}")
        
        # Top colors
        print(f"\n🎨 Top Colors:")
        colors = list(self.collection.aggregate([
            {"$unwind": "$colors"},
            {"$group": {"_id": "$colors", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 8}
        ]))
        
        for item in colors:
            print(f"   {item['_id']}: {item['count']}")
        
        # Top styles
        print(f"\n✨ Top Styles:")
        styles = list(self.collection.aggregate([
            {"$unwind": "$styles"},
            {"$group": {"_id": "$styles", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 6}
        ]))
        
        for item in styles:
            print(f"   {item['_id']}: {item['count']}")
        
        print(f"\n🎉 Your watch database is now AI-enhanced!")
        print(f"🤖 Customers can now search by colors, styles, materials, and belt types!")
    
    def close(self):
        """Close database connection"""
        self.client.close()

def main():
    """Main function - automatically starts enhancement"""
    # Configuration
    MONGODB_URI = "mongodb://admin:strongpassword123@72.62.76.36:27017/?authSource=admin"
    GOOGLE_API_KEY = "AIzaSyBZ8shurgeNDiDj4TlpBk7RUgrQ-G2mJ_0"
    
    print("🤖 AUTOMATIC AI WATCH ENHANCEMENT SYSTEM")
    print("=" * 60)
    print("🚀 This will automatically enhance all watches with AI analysis")
    print("🔍 Extracting: Colors, Styles, Materials, Belt Types")
    print("📊 Real-time progress monitoring included")
    print("=" * 60)
    
    # Initialize the enhancer
    try:
        enhancer = AutoAIWatchEnhancer(MONGODB_URI, GOOGLE_API_KEY)
    except Exception as e:
        print(f"❌ Failed to initialize system: {e}")
        input("Press Enter to exit...")
        return
    
    try:
        # Show current status
        watches_needing = len(enhancer.get_watches_needing_enhancement())
        total_watches = enhancer.collection.count_documents({})
        
        if watches_needing == 0:
            print(f"✅ All {total_watches} watches are already enhanced!")
            enhancer.show_final_summary()
        else:
            print(f"📊 Found {watches_needing} watches that need enhancement (out of {total_watches} total)")
            
            # Ask for batch size
            print(f"\n⚙️ Choose enhancement speed:")
            print(f"1. 🐌 Slow & Safe (2.0 seconds per watch)")
            print(f"2. ⚡ Normal (1.5 seconds per watch) - Recommended")
            print(f"3. 🚀 Fast (1.0 seconds per watch)")
            print(f"4. 🏃 Very Fast (0.5 seconds per watch)")
            
            speed_choice = input(f"\nChoose speed (1-4) [2]: ").strip() or "2"
            
            speed_map = {
                "1": 2.0,
                "2": 1.5,
                "3": 1.0,
                "4": 0.5
            }
            
            delay = speed_map.get(speed_choice, 1.5)
            
            # Start automatic enhancement
            enhancer.auto_enhance_all(batch_size=25, delay=delay)
    
    except KeyboardInterrupt:
        print(f"\n⏹️ Process interrupted by user")
    
    except Exception as e:
        print(f"\n❌ Error: {e}")
    
    finally:
        enhancer.close()
        input("\nPress Enter to exit...")

if __name__ == "__main__":
    main()