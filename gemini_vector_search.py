#!/usr/bin/env python3
"""
Gemini Vector Search System for MongoDB
Uses Gemini text embeddings for semantic product search
"""

import google.generativeai as genai
import pymongo
from pymongo import MongoClient
import numpy as np
from typing import List, Dict, Optional, Tuple
import logging
import time
import json
from datetime import datetime

class GeminiVectorSearch:
    def __init__(self, mongodb_uri: str, google_api_key: str, collection_name: str = "products"):
        """Initialize Gemini Vector Search"""
        # Configure Gemini API
        genai.configure(api_key=google_api_key)
        self.model = genai.GenerativeModel('gemini-pro')
        
        # MongoDB setup
        self.client = MongoClient(mongodb_uri)
        self.db = self.client['watchvine_refined']
        self.collection = self.db[collection_name]
        
        # Create vector search index if not exists
        self._create_vector_index()
        
        logging.info("Gemini Vector Search initialized")
    
    def _create_vector_index(self):
        """Create vector search index in MongoDB"""
        try:
            # Create vector search index for embeddings
            index_definition = {
                "mappings": {
                    "dynamic": True,
                    "fields": {
                        "text_embedding": {
                            "type": "knnVector",
                            "dimensions": 768,  # Gemini embedding dimension
                            "similarity": "cosine"
                        }
                    }
                }
            }
            
            # Check if index exists
            existing_indexes = list(self.collection.list_search_indexes())
            if not any(idx.get('name') == 'vector_index' for idx in existing_indexes):
                self.collection.create_search_index(
                    index_definition, 
                    name="vector_index"
                )
                logging.info("Vector search index created")
        except Exception as e:
            logging.warning(f"Vector index creation: {e}")
    
    def generate_text_embedding(self, text: str) -> List[float]:
        """Generate text embedding using Gemini"""
        try:
            # Use Gemini embedding model
            result = genai.embed_content(
                model="models/embedding-001",
                content=text,
                task_type="retrieval_query"
            )
            return result['embedding']
        except Exception as e:
            logging.error(f"Error generating embedding: {e}")
            return []
    
    def create_searchable_text(self, product: Dict) -> str:
        """Create comprehensive searchable text for product"""
        text_parts = [
            product.get('name', ''),
            product.get('brand', ''),
            product.get('category', ''),
            product.get('description', ''),
            ' '.join(product.get('colors', [])),
            ' '.join(product.get('styles', [])),
            ' '.join(product.get('materials', [])),
            product.get('belt_type', '').replace('_', ' '),
            product.get('ai_category', '').replace('_', ' '),
            product.get('ai_gender_target', ''),
            product.get('price_range', ''),
            f"price {product.get('price', '0')} rupees"
        ]
        
        # Add AI analysis details
        if 'ai_analysis' in product:
            details = product['ai_analysis'].get('additional_details', {})
            text_parts.extend([
                details.get('dial_color', ''),
                details.get('strap_material', ''),
                details.get('watch_type', ''),
                details.get('case_material', ''),
                ' '.join(details.get('design_elements', []))
            ])
        
        return ' '.join(filter(None, text_parts)).lower()
    
    def index_products(self, batch_size: int = 50):
        """Index all products with embeddings"""
        logging.info("Starting product indexing...")
        
        # Get products without embeddings
        unindexed_query = {"text_embedding": {"$exists": False}}
        products = list(self.collection.find(unindexed_query))
        
        if not products:
            logging.info("All products already indexed")
            return
        
        logging.info(f"Indexing {len(products)} products...")
        
        indexed_count = 0
        for i in range(0, len(products), batch_size):
            batch = products[i:i + batch_size]
            
            for product in batch:
                try:
                    # Create searchable text
                    searchable_text = self.create_searchable_text(product)
                    
                    # Generate embedding
                    embedding = self.generate_text_embedding(searchable_text)
                    
                    if embedding:
                        # Update product with embedding
                        self.collection.update_one(
                            {"_id": product["_id"]},
                            {
                                "$set": {
                                    "text_embedding": embedding,
                                    "searchable_text": searchable_text,
                                    "indexed_at": datetime.now().isoformat()
                                }
                            }
                        )
                        indexed_count += 1
                    
                    time.sleep(0.1)  # Rate limiting
                    
                except Exception as e:
                    logging.error(f"Error indexing product {product.get('name')}: {e}")
            
            logging.info(f"Indexed {min(i + batch_size, len(products))}/{len(products)} products")
            time.sleep(1)  # Batch delay
        
        logging.info(f"Indexing complete. Indexed {indexed_count} products")
    
    def vector_search(self, query: str, limit: int = 5) -> List[Dict]:
        """Perform vector search using query"""
        try:
            # Generate query embedding
            query_embedding = self.generate_text_embedding(query)
            
            if not query_embedding:
                return []
            
            # MongoDB vector search pipeline
            pipeline = [
                {
                    "$vectorSearch": {
                        "index": "vector_index",
                        "path": "text_embedding",
                        "queryVector": query_embedding,
                        "numCandidates": 100,
                        "limit": limit
                    }
                },
                {
                    "$project": {
                        "name": 1,
                        "brand": 1,
                        "price": 1,
                        "image_urls": 1,
                        "url": 1,
                        "colors": 1,
                        "styles": 1,
                        "materials": 1,
                        "belt_type": 1,
                        "ai_category": 1,
                        "ai_gender_target": 1,
                        "description": 1,
                        "score": {"$meta": "vectorSearchScore"}
                    }
                }
            ]
            
            results = list(self.collection.aggregate(pipeline))
            return results
            
        except Exception as e:
            logging.error(f"Vector search error: {e}")
            return []
    
    def hybrid_search(self, query: str, filters: Dict = None, limit: int = 5) -> List[Dict]:
        """Combine vector search with traditional filters"""
        try:
            # Generate query embedding
            query_embedding = self.generate_text_embedding(query)
            
            if not query_embedding:
                return []
            
            # Build filter stage
            match_stage = {}
            if filters:
                if filters.get('colors'):
                    match_stage['colors'] = {"$in": filters['colors']}
                if filters.get('brand'):
                    match_stage['brand'] = {"$regex": filters['brand'], "$options": "i"}
                if filters.get('price_max'):
                    match_stage['price'] = {"$lte": str(filters['price_max'])}
                if filters.get('belt_type'):
                    match_stage['belt_type'] = filters['belt_type']
                if filters.get('ai_category'):
                    match_stage['ai_category'] = filters['ai_category']
            
            # Build pipeline
            pipeline = [
                {
                    "$vectorSearch": {
                        "index": "vector_index",
                        "path": "text_embedding",
                        "queryVector": query_embedding,
                        "numCandidates": 200,
                        "limit": limit * 3  # Get more candidates for filtering
                    }
                }
            ]
            
            # Add filter stage if filters exist
            if match_stage:
                pipeline.append({"$match": match_stage})
            
            # Project and limit
            pipeline.extend([
                {
                    "$project": {
                        "name": 1,
                        "brand": 1,
                        "price": 1,
                        "image_urls": 1,
                        "url": 1,
                        "colors": 1,
                        "styles": 1,
                        "materials": 1,
                        "belt_type": 1,
                        "ai_category": 1,
                        "ai_gender_target": 1,
                        "description": 1,
                        "score": {"$meta": "vectorSearchScore"}
                    }
                },
                {"$limit": limit}
            ])
            
            results = list(self.collection.aggregate(pipeline))
            return results
            
        except Exception as e:
            logging.error(f"Hybrid search error: {e}")
            return []
    
    def get_indexing_stats(self) -> Dict:
        """Get indexing statistics"""
        total_products = self.collection.count_documents({})
        indexed_products = self.collection.count_documents({"text_embedding": {"$exists": True}})
        
        return {
            "total_products": total_products,
            "indexed_products": indexed_products,
            "indexing_percentage": (indexed_products / max(total_products, 1)) * 100
        }
    
    def close(self):
        """Close database connection"""
        self.client.close()

# Test function
if __name__ == "__main__":
    MONGODB_URI = "mongodb://admin:strongpassword123@72.62.76.36:27017/?authSource=admin"
    GOOGLE_API_KEY = "AIzaSyBZ8shurgeNDiDj4TlpBk7RUgrQ-G2mJ_0"
    
    search = GeminiVectorSearch(MONGODB_URI, GOOGLE_API_KEY)
    
    # Test search
    results = search.vector_search("black luxury watch")
    print(f"Found {len(results)} results")
    
    for result in results:
        print(f"- {result.get('name')} (Score: {result.get('score', 0):.3f})")
    
    search.close()