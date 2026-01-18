#!/usr/bin/env python3
"""
Enhanced RAG (Retrieval-Augmented Generation) System for Watch Products
Provides intelligent search and recommendations for watch queries
"""

import pymongo
from pymongo import MongoClient
import re
from typing import List, Dict, Optional
import json
from datetime import datetime
from collections import defaultdict

class WatchRAGSystem:
    def __init__(self, mongodb_uri: str):
        self.mongodb_uri = mongodb_uri
        self.client = MongoClient(mongodb_uri)
        self.db = self.client['watchvine_refined']
        self.collection = self.db['products']
        
        # Create indexes for better search performance
        try:
            self.collection.create_index([("searchable_text", "text")])
            self.collection.create_index([("brand", 1)])
            self.collection.create_index([("colors", 1)])
            self.collection.create_index([("styles", 1)])
            self.collection.create_index([("gender", 1)])
            self.collection.create_index([("price_range", 1)])
        except:
            pass  # Indexes might already exist
    
    def parse_user_query(self, query: str) -> Dict:
        """Parse user query to extract search criteria"""
        query_lower = query.lower()
        
        parsed = {
            'brands': [],
            'colors': [],
            'styles': [],
            'materials': [],
            'gender': None,
            'price_preferences': [],
            'keywords': []
        }
        
        # Brand detection
        brand_patterns = {
            'rolex': r'\b(rolex|rlx)\b',
            'audemars_piguet': r'\b(audemars[_\s]*piguet|ap)\b',
            'patek_philippe': r'\b(patek[_\s]*philippe|pp)\b',
            'omega': r'\b(omega)\b',
            'casio': r'\b(casio)\b',
            'seiko': r'\b(seiko)\b',
            'citizen': r'\b(citizen)\b',
            'tissot': r'\b(tissot)\b',
            'fossil': r'\b(fossil)\b',
            'apple': r'\b(apple|iwatch)\b',
            'samsung': r'\b(samsung)\b',
            'garmin': r'\b(garmin)\b',
            'maybach': r'\b(maybach)\b'
        }
        
        for brand, pattern in brand_patterns.items():
            if re.search(pattern, query_lower):
                parsed['brands'].append(brand.replace('_', ' ').title())
        
        # Color detection
        color_patterns = {
            'black': r'\b(black|dark)\b',
            'white': r'\b(white|light)\b',
            'silver': r'\b(silver|steel|stainless)\b',
            'gold': r'\b(gold|golden)\b',
            'rose_gold': r'\b(rose[_\s]*gold|pink[_\s]*gold)\b',
            'blue': r'\b(blue|navy)\b',
            'red': r'\b(red|burgundy)\b',
            'green': r'\b(green|olive)\b',
            'brown': r'\b(brown|tan|leather)\b',
            'gray': r'\b(gray|grey)\b'
        }
        
        for color, pattern in color_patterns.items():
            if re.search(pattern, query_lower):
                parsed['colors'].append(color.replace('_', ' ').title())
        
        # Style detection
        style_patterns = {
            'minimalistic': r'\b(minimal|minimalist|simple|clean|sleek|elegant)\b',
            'sporty': r'\b(sport|sporty|athletic|diving|racing|fitness)\b',
            'luxury': r'\b(luxury|premium|expensive|high[_\s]*end|prestigious)\b',
            'casual': r'\b(casual|everyday|daily|informal)\b',
            'formal': r'\b(formal|dress|business|professional|office)\b',
            'vintage': r'\b(vintage|retro|classic|old[_\s]*style)\b',
            'modern': r'\b(modern|contemporary|new|latest)\b',
            'smartwatch': r'\b(smart|digital|fitness|health|connected)\b'
        }
        
        for style, pattern in style_patterns.items():
            if re.search(pattern, query_lower):
                parsed['styles'].append(style.title())
        
        # Gender detection
        if re.search(r'\b(men|male|guy|man)\b', query_lower):
            parsed['gender'] = 'Men'
        elif re.search(r'\b(women|female|girl|lady|ladies)\b', query_lower):
            parsed['gender'] = 'Women'
        
        # Price preferences
        if re.search(r'\b(cheap|budget|affordable|low[_\s]*price|under[_\s]*1000)\b', query_lower):
            parsed['price_preferences'].append('Budget (Under ₹1000)')
        elif re.search(r'\b(expensive|luxury|premium|high[_\s]*end|above[_\s]*5000)\b', query_lower):
            parsed['price_preferences'].append('Luxury (₹5000+)')
        elif re.search(r'\b(mid[_\s]*range|moderate|average)\b', query_lower):
            parsed['price_preferences'].append('Mid-Range (₹1000-2500)')
        
        # Extract keywords
        keywords = re.findall(r'\b\w+\b', query_lower)
        stop_words = {'show', 'me', 'find', 'get', 'want', 'need', 'looking', 'for', 'a', 'an', 'the', 'and', 'or', 'but', 'with', 'which', 'that', 'is', 'are', 'should', 'be', 'have', 'has', 'can', 'will', 'would', 'could'}
        parsed['keywords'] = [word for word in keywords if word not in stop_words]
        
        return parsed
    
    def build_search_query(self, parsed_query: Dict) -> Dict:
        """Build MongoDB query from parsed user query"""
        mongo_query = {"$and": []}
        
        # Brand filter
        if parsed_query['brands']:
            mongo_query["$and"].append({
                "brand": {"$in": parsed_query['brands']}
            })
        
        # Color filter
        if parsed_query['colors']:
            mongo_query["$and"].append({
                "colors": {"$in": parsed_query['colors']}
            })
        
        # Style filter
        if parsed_query['styles']:
            mongo_query["$and"].append({
                "styles": {"$in": parsed_query['styles']}
            })
        
        # Gender filter
        if parsed_query['gender']:
            mongo_query["$and"].append({
                "gender": parsed_query['gender']
            })
        
        # Price preference filter
        if parsed_query['price_preferences']:
            mongo_query["$and"].append({
                "price_range": {"$in": parsed_query['price_preferences']}
            })
        
        # Text search for keywords
        if parsed_query['keywords']:
            keyword_patterns = []
            for keyword in parsed_query['keywords']:
                keyword_patterns.append({
                    "searchable_text": {"$regex": keyword, "$options": "i"}
                })
            
            if keyword_patterns:
                mongo_query["$and"].append({
                    "$or": keyword_patterns
                })
        
        # If no specific filters, return all watches
        if not mongo_query["$and"]:
            return {}
        
        return mongo_query
    
    def search_watches(self, user_query: str, limit: int = 10) -> List[Dict]:
        """Search for watches based on user query"""
        # Parse the query
        parsed = self.parse_user_query(user_query)
        
        # Build MongoDB query
        mongo_query = self.build_search_query(parsed)
        
        # Execute search
        results = list(self.collection.find(mongo_query).limit(limit))
        
        # If no results with strict matching, try looser search
        if not results and mongo_query:
            # Try with just brand and gender if specified
            loose_query = {}
            if parsed['brands']:
                loose_query["brand"] = {"$in": parsed['brands']}
            elif parsed['gender']:
                loose_query["gender"] = parsed['gender']
            
            if loose_query:
                results = list(self.collection.find(loose_query).limit(limit))
        
        # If still no results, try text search only
        if not results and parsed['keywords']:
            text_query = {
                "$or": [
                    {"searchable_text": {"$regex": keyword, "$options": "i"}}
                    for keyword in parsed['keywords']
                ]
            }
            results = list(self.collection.find(text_query).limit(limit))
        
        return results
    
    def format_watch_response(self, watches: List[Dict], user_query: str) -> str:
        """Format search results into a user-friendly response"""
        if not watches:
            return "Sorry, I couldn't find any watches matching your criteria. Please try different search terms or browse our collection."
        
        response = f"I found {len(watches)} watch{'es' if len(watches) > 1 else ''} for you:\n\n"
        
        for i, watch in enumerate(watches, 1):
            brand = watch.get('brand', 'Unknown Brand')
            name = watch.get('name', 'Unnamed Watch')
            price = watch.get('price', 'Price not available')
            colors = ', '.join(watch.get('colors', ['Not specified']))
            styles = ', '.join(watch.get('styles', ['Classic']))
            
            response += f"**{i}. {brand} - {name}**\n"
            response += f"   💰 Price: ₹{price}\n"
            if colors != 'Not specified':
                response += f"   🎨 Colors: {colors}\n"
            if styles != 'Classic':
                response += f"   ✨ Style: {styles}\n"
            response += f"   🔗 [View Product]({watch.get('url', '#')})\n\n"
        
        return response
    
    def get_recommendations(self, user_preferences: Dict, limit: int = 5) -> List[Dict]:
        """Get watch recommendations based on user preferences"""
        query = {}
        
        if user_preferences.get('gender'):
            query['gender'] = user_preferences['gender']
        
        if user_preferences.get('price_range'):
            query['price_range'] = user_preferences['price_range']
        
        if user_preferences.get('style'):
            query['styles'] = {"$in": [user_preferences['style']]}
        
        return list(self.collection.find(query).limit(limit))
    
    def get_database_stats(self) -> Dict:
        """Get statistics about the watch database"""
        total_watches = self.collection.count_documents({})
        
        # Brand distribution
        brand_pipeline = [
            {"$group": {"_id": "$brand", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 10}
        ]
        brands = list(self.collection.aggregate(brand_pipeline))
        
        # Gender distribution
        gender_pipeline = [
            {"$group": {"_id": "$gender", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        genders = list(self.collection.aggregate(gender_pipeline))
        
        # Price range distribution
        price_pipeline = [
            {"$group": {"_id": "$price_range", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        price_ranges = list(self.collection.aggregate(price_pipeline))
        
        return {
            'total_watches': total_watches,
            'top_brands': brands,
            'gender_distribution': genders,
            'price_distribution': price_ranges
        }
    
    def close(self):
        """Close database connection"""
        self.client.close()

# Test function
def test_rag_system():
    """Test the RAG system with sample queries"""
    MONGODB_URI = "mongodb://admin:strongpassword123@72.62.76.36:27017/?authSource=admin"
    
    rag = WatchRAGSystem(MONGODB_URI)
    
    test_queries = [
        "show me black rolex watches",
        "I want a minimalistic watch for men",
        "find luxury watches above 5000",
        "show me women's watches",
        "get me sporty watches",
        "I need a watch with gold color",
        "show me audemars piguet watches"
    ]
    
    print("=== TESTING RAG SYSTEM ===\n")
    
    for i, query in enumerate(test_queries, 1):
        print(f"Query {i}: {query}")
        parsed = rag.parse_user_query(query)
        print(f"Parsed: {parsed}")
        
        results = rag.search_watches(query, limit=3)
        print(f"Found {len(results)} results")
        
        if results:
            response = rag.format_watch_response(results, query)
            print(f"Response:\n{response}")
        
        print("-" * 80)
    
    # Show database stats
    stats = rag.get_database_stats()
    print(f"Database Stats: {stats}")
    
    rag.close()

if __name__ == "__main__":
    test_rag_system()