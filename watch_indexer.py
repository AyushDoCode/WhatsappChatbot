#!/usr/bin/env python3
"""
Watch-Only Image Indexer with Vector Database
Enhanced for watch products with AI-extracted features
"""

import os
import sys
import numpy as np
import pymongo
from pymongo import MongoClient
import chromadb
from chromadb.utils import embedding_functions
import requests
from PIL import Image
import io
import time
import logging
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import json
import hashlib

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('watch_indexer.log'),
        logging.StreamHandler()
    ]
)

class WatchImageIndexer:
    def __init__(self, mongodb_uri: str, chroma_path: str = "./chroma_watch_db"):
        """Initialize the Watch Image Indexer"""
        # MongoDB connection
        self.mongodb_uri = mongodb_uri
        self.client = MongoClient(mongodb_uri)
        self.db = self.client['watchvine_refined']
        self.collection = self.db['products']
        
        # ChromaDB setup for image vectors
        self.chroma_client = chromadb.PersistentClient(path=chroma_path)
        
        # Create or get collection
        try:
            self.vector_collection = self.chroma_client.get_collection("watch_images")
        except:
            # Create new collection with embedding function
            embedding_fn = embedding_functions.OpenCLIPEmbeddingFunction(
                model_name="ViT-B-32",
                checkpoint="openai"
            )
            self.vector_collection = self.chroma_client.create_collection(
                name="watch_images",
                embedding_function=embedding_fn
            )
        
        # HTTP session for image downloads
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        # Statistics
        self.total_watches = 0
        self.processed_watches = 0
        self.indexed_images = 0
        self.skipped_watches = 0
        
        logging.info("Watch Image Indexer initialized")
    
    def download_image(self, image_url: str) -> Optional[Image.Image]:
        """Download and process image for indexing"""
        try:
            response = self.session.get(image_url, timeout=10)
            response.raise_for_status()
            
            # Open image
            image = Image.open(io.BytesIO(response.content))
            
            # Convert to RGB if needed
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Resize for consistent indexing
            max_size = 512
            if max(image.size) > max_size:
                image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            
            return image
            
        except Exception as e:
            logging.error(f"Error downloading image {image_url}: {e}")
            return None
    
    def create_image_id(self, watch_id: str, image_url: str) -> str:
        """Create unique ID for image"""
        combined = f"{watch_id}_{image_url}"
        return hashlib.md5(combined.encode()).hexdigest()
    
    def create_watch_metadata(self, watch: Dict) -> Dict:
        """Create comprehensive metadata for watch"""
        metadata = {
            'watch_id': str(watch['_id']),
            'watch_name': watch.get('name', ''),
            'price': watch.get('price', '0'),
            'category': watch.get('category', 'Watch'),
            'url': watch.get('url', ''),
            'brand': watch.get('brand', 'Unknown'),
            'colors': json.dumps(watch.get('colors', [])),
            'styles': json.dumps(watch.get('styles', [])),
            'materials': json.dumps(watch.get('materials', [])),
            'belt_type': watch.get('belt_type', 'unknown'),
            'gender': watch.get('gender', 'Unisex'),
            'price_range': watch.get('price_range', 'Unknown'),
            'indexed_at': datetime.now().isoformat(),
            'has_ai_analysis': 'ai_analysis' in watch
        }
        
        # Add AI analysis details if available
        if 'ai_analysis' in watch:
            ai_details = watch['ai_analysis'].get('additional_details', {})
            metadata.update({
                'dial_color': ai_details.get('dial_color', ''),
                'strap_material': ai_details.get('strap_material', ''),
                'strap_color': ai_details.get('strap_color', ''),
                'watch_type': ai_details.get('watch_type', ''),
                'case_material': ai_details.get('case_material', '')
            })
        
        return metadata
    
    def create_searchable_text(self, watch: Dict, metadata: Dict) -> str:
        """Create comprehensive searchable text"""
        text_parts = [
            watch.get('name', ''),
            watch.get('category', ''),
            watch.get('brand', ''),
            watch.get('description', ''),
            ' '.join(watch.get('colors', [])),
            ' '.join(watch.get('styles', [])),
            ' '.join(watch.get('materials', [])),
            watch.get('belt_type', '').replace('_', ' '),
            watch.get('gender', ''),
            watch.get('price_range', ''),
            metadata.get('dial_color', ''),
            metadata.get('strap_material', ''),
            metadata.get('watch_type', '')
        ]
        
        # Add specifications if available
        if 'specifications' in watch:
            text_parts.extend(watch['specifications'])
        
        return ' '.join(filter(None, text_parts)).lower()
    
    def index_watch_images(self, watch: Dict) -> int:
        """Index all images for a single watch"""
        watch_id = str(watch['_id'])
        watch_name = watch.get('name', 'Unknown')
        image_urls = watch.get('image_urls', [])
        
        if not image_urls:
            logging.warning(f"No images found for watch: {watch_name}")
            return 0
        
        # Create metadata
        metadata = self.create_watch_metadata(watch)
        searchable_text = self.create_searchable_text(watch, metadata)
        
        indexed_count = 0
        
        for i, image_url in enumerate(image_urls):
            try:
                # Create unique image ID
                image_id = self.create_image_id(watch_id, image_url)
                
                # Check if already indexed
                try:
                    existing = self.vector_collection.get(ids=[image_id])
                    if existing['ids']:
                        logging.info(f"Image already indexed: {watch_name} - Image {i+1}")
                        indexed_count += 1
                        continue
                except:
                    pass  # Image not found, continue with indexing
                
                # Download and process image
                image = self.download_image(image_url)
                if image is None:
                    continue
                
                # Create image-specific metadata
                image_metadata = metadata.copy()
                image_metadata.update({
                    'image_url': image_url,
                    'image_index': i,
                    'is_primary_image': i == 0
                })
                
                # Add to vector database
                self.vector_collection.add(
                    ids=[image_id],
                    images=[image],
                    metadatas=[image_metadata],
                    documents=[searchable_text]
                )
                
                indexed_count += 1
                logging.info(f"Indexed image {i+1}/{len(image_urls)} for: {watch_name}")
                
                # Small delay to avoid overwhelming the system
                time.sleep(0.1)
                
            except Exception as e:
                logging.error(f"Error indexing image {i+1} for {watch_name}: {e}")
                continue
        
        return indexed_count
    
    def get_watches_to_index(self, limit: Optional[int] = None) -> List[Dict]:
        """Get watches that need indexing"""
        # Find watches with images
        query = {
            'image_urls': {'$exists': True, '$ne': []},
            'category': {'$regex': 'watch', '$options': 'i'}
        }
        
        cursor = self.collection.find(query)
        if limit:
            cursor = cursor.limit(limit)
        
        return list(cursor)
    
    def index_all_watches(self, batch_size: int = 50, limit: Optional[int] = None):
        """Index all watches in batches"""
        logging.info("Starting watch indexing process...")
        
        # Get watches to index
        watches = self.get_watches_to_index(limit)
        self.total_watches = len(watches)
        
        if self.total_watches == 0:
            logging.info("No watches found to index")
            return
        
        logging.info(f"Found {self.total_watches} watches to index")
        
        start_time = time.time()
        
        # Process in batches
        for i in range(0, self.total_watches, batch_size):
            batch_end = min(i + batch_size, self.total_watches)
            batch_watches = watches[i:batch_end]
            batch_num = (i // batch_size) + 1
            total_batches = (self.total_watches + batch_size - 1) // batch_size
            
            logging.info(f"Processing batch {batch_num}/{total_batches} ({len(batch_watches)} watches)")
            
            for watch in batch_watches:
                try:
                    watch_name = watch.get('name', 'Unknown')
                    
                    # Index watch images
                    indexed_images = self.index_watch_images(watch)
                    
                    if indexed_images > 0:
                        self.indexed_images += indexed_images
                        self.processed_watches += 1
                        logging.info(f"✅ Processed: {watch_name} ({indexed_images} images)")
                    else:
                        self.skipped_watches += 1
                        logging.warning(f"⚠️ Skipped: {watch_name} (no indexable images)")
                    
                except Exception as e:
                    self.skipped_watches += 1
                    logging.error(f"❌ Error processing watch {watch.get('name', 'Unknown')}: {e}")
                    continue
            
            # Progress update
            progress = ((i + len(batch_watches)) / self.total_watches) * 100
            elapsed_time = time.time() - start_time
            
            logging.info(f"📊 Progress: {progress:.1f}% | "
                        f"Processed: {self.processed_watches} | "
                        f"Images: {self.indexed_images} | "
                        f"Time: {elapsed_time/60:.1f}min")
            
            # Delay between batches
            time.sleep(1)
        
        # Final summary
        total_time = time.time() - start_time
        self.log_indexing_summary(total_time)
    
    def log_indexing_summary(self, total_time: float):
        """Log comprehensive indexing summary"""
        logging.info("=" * 60)
        logging.info("WATCH INDEXING COMPLETED")
        logging.info("=" * 60)
        logging.info(f"Total watches processed: {self.processed_watches}")
        logging.info(f"Total images indexed: {self.indexed_images}")
        logging.info(f"Watches skipped: {self.skipped_watches}")
        logging.info(f"Total time: {total_time/60:.1f} minutes")
        logging.info(f"Average speed: {(self.indexed_images / total_time * 60):.1f} images/minute")
        
        # Database statistics
        try:
            total_vectors = self.vector_collection.count()
            logging.info(f"Total vectors in database: {total_vectors}")
        except:
            logging.info("Could not get vector database count")
        
        logging.info("=" * 60)
    
    def search_similar_watches(self, query_image_url: str, n_results: int = 5) -> List[Dict]:
        """Search for similar watches using image"""
        try:
            # Download query image
            query_image = self.download_image(query_image_url)
            if query_image is None:
                return []
            
            # Search in vector database
            results = self.vector_collection.query(
                query_images=[query_image],
                n_results=n_results,
                include=['metadatas', 'distances']
            )
            
            # Format results
            formatted_results = []
            for i, metadata in enumerate(results['metadatas'][0]):
                result = {
                    'watch_id': metadata['watch_id'],
                    'watch_name': metadata['watch_name'],
                    'price': metadata['price'],
                    'brand': metadata['brand'],
                    'colors': json.loads(metadata.get('colors', '[]')),
                    'styles': json.loads(metadata.get('styles', '[]')),
                    'belt_type': metadata.get('belt_type', 'unknown'),
                    'image_url': metadata['image_url'],
                    'similarity_score': 1 - results['distances'][0][i],  # Convert distance to similarity
                    'url': metadata.get('url', '')
                }
                formatted_results.append(result)
            
            return formatted_results
            
        except Exception as e:
            logging.error(f"Error searching similar watches: {e}")
            return []
    
    def search_watches_by_text(self, query_text: str, n_results: int = 10) -> List[Dict]:
        """Search watches by text query"""
        try:
            # Search in vector database
            results = self.vector_collection.query(
                query_texts=[query_text.lower()],
                n_results=n_results,
                include=['metadatas', 'distances']
            )
            
            # Format results
            formatted_results = []
            seen_watches = set()
            
            for i, metadata in enumerate(results['metadatas'][0]):
                watch_id = metadata['watch_id']
                
                # Avoid duplicate watches (same watch, different images)
                if watch_id in seen_watches:
                    continue
                seen_watches.add(watch_id)
                
                result = {
                    'watch_id': watch_id,
                    'watch_name': metadata['watch_name'],
                    'price': metadata['price'],
                    'brand': metadata['brand'],
                    'colors': json.loads(metadata.get('colors', '[]')),
                    'styles': json.loads(metadata.get('styles', '[]')),
                    'belt_type': metadata.get('belt_type', 'unknown'),
                    'image_url': metadata['image_url'],
                    'relevance_score': 1 - results['distances'][0][i],
                    'url': metadata.get('url', '')
                }
                formatted_results.append(result)
            
            return formatted_results
            
        except Exception as e:
            logging.error(f"Error searching watches by text: {e}")
            return []
    
    def get_indexing_stats(self) -> Dict:
        """Get current indexing statistics"""
        try:
            total_watches = self.collection.count_documents({})
            watches_with_images = self.collection.count_documents({
                'image_urls': {'$exists': True, '$ne': []}
            })
            ai_enhanced_watches = self.collection.count_documents({
                'ai_analysis': {'$exists': True}
            })
            
            vector_count = self.vector_collection.count()
            
            return {
                'total_watches': total_watches,
                'watches_with_images': watches_with_images,
                'ai_enhanced_watches': ai_enhanced_watches,
                'total_vectors': vector_count,
                'indexing_coverage': (vector_count / max(watches_with_images, 1)) * 100
            }
            
        except Exception as e:
            logging.error(f"Error getting indexing stats: {e}")
            return {}
    
    def close(self):
        """Close database connections"""
        self.client.close()
        logging.info("Database connections closed")

def main():
    """Main function for testing and manual execution"""
    MONGODB_URI = "mongodb://admin:strongpassword123@72.62.76.36:27017/?authSource=admin"
    
    indexer = WatchImageIndexer(MONGODB_URI)
    
    try:
        print("🔍 Watch Image Indexer")
        print("1. Index all watches")
        print("2. Index limited watches (for testing)")
        print("3. Show indexing statistics")
        print("4. Test image search")
        print("5. Test text search")
        
        choice = input("Choose option (1-5): ").strip()
        
        if choice == "1":
            indexer.index_all_watches()
        elif choice == "2":
            limit = int(input("Enter number of watches to index: "))
            indexer.index_all_watches(limit=limit)
        elif choice == "3":
            stats = indexer.get_indexing_stats()
            print("📊 Indexing Statistics:")
            for key, value in stats.items():
                print(f"   {key}: {value}")
        elif choice == "4":
            image_url = input("Enter image URL for search: ")
            results = indexer.search_similar_watches(image_url)
            print(f"Found {len(results)} similar watches:")
            for i, result in enumerate(results, 1):
                print(f"   {i}. {result['watch_name']} - {result['brand']} (Score: {result['similarity_score']:.3f})")
        elif choice == "5":
            query = input("Enter search query: ")
            results = indexer.search_watches_by_text(query)
            print(f"Found {len(results)} matching watches:")
            for i, result in enumerate(results, 1):
                print(f"   {i}. {result['watch_name']} - {result['brand']} (Score: {result['relevance_score']:.3f})")
        else:
            print("Invalid choice")
            
    except KeyboardInterrupt:
        logging.info("Indexer stopped by user")
    finally:
        indexer.close()

if __name__ == "__main__":
    main()