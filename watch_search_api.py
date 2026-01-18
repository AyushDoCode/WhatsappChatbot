#!/usr/bin/env python3
"""
Watch Search API Service
Provides REST API for watch search functionality
"""

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import os
import sys
import logging
from datetime import datetime
from watch_indexer import WatchImageIndexer
from watch_rag_system import WatchRAGSystem
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Configuration
MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://admin:strongpassword123@72.62.76.36:27017/?authSource=admin')
CHROMA_PATH = os.getenv('CHROMA_PATH', './chroma_watch_db')

# Initialize services
indexer = WatchImageIndexer(MONGODB_URI, CHROMA_PATH)
rag_system = WatchRAGSystem(MONGODB_URI)

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        # Test database connection
        stats = indexer.get_indexing_stats()
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'database_stats': stats
        }), 200
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 500

@app.route('/search/text', methods=['POST'])
def search_by_text():
    """Search watches by text query"""
    try:
        data = request.get_json()
        query = data.get('query', '')
        limit = data.get('limit', 10)
        
        if not query:
            return jsonify({'error': 'Query parameter is required'}), 400
        
        # Search using RAG system
        results = rag_system.search_watches(query, limit=limit)
        
        # Format response
        formatted_results = []
        for watch in results:
            formatted_results.append({
                'id': str(watch['_id']),
                'name': watch.get('name', ''),
                'price': watch.get('price', '0'),
                'brand': watch.get('brand', 'Unknown'),
                'colors': watch.get('colors', []),
                'styles': watch.get('styles', []),
                'materials': watch.get('materials', []),
                'belt_type': watch.get('belt_type', 'unknown'),
                'ai_category': watch.get('ai_category', 'casual_watch'),
                'ai_gender_target': watch.get('ai_gender_target', 'unisex'),
                'image_urls': watch.get('image_urls', []),
                'url': watch.get('url', ''),
                'description': watch.get('description', '')[:200],
                'ai_enhanced': 'ai_analysis' in watch
            })
        
        return jsonify({
            'query': query,
            'results_count': len(formatted_results),
            'results': formatted_results
        })
        
    except Exception as e:
        logger.error(f"Error in text search: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/search/image', methods=['POST'])
def search_by_image():
    """Search watches by image similarity"""
    try:
        data = request.get_json()
        image_url = data.get('image_url', '')
        limit = data.get('limit', 5)
        
        if not image_url:
            return jsonify({'error': 'image_url parameter is required'}), 400
        
        # Search using image indexer
        results = indexer.search_similar_watches(image_url, n_results=limit)
        
        return jsonify({
            'query_image': image_url,
            'results_count': len(results),
            'results': results
        })
        
    except Exception as e:
        logger.error(f"Error in image search: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/search/filters', methods=['POST'])
def search_with_filters():
    """Advanced search with multiple filters"""
    try:
        data = request.get_json()
        
        filters = {
            'brand': data.get('brand'),
            'colors': data.get('colors', []),
            'styles': data.get('styles', []),
            'materials': data.get('materials', []),
            'belt_type': data.get('belt_type'),
            'ai_category': data.get('category'),
            'ai_gender_target': data.get('gender_target'),
            'price_min': data.get('price_min'),
            'price_max': data.get('price_max'),
            'gender': data.get('gender')
        }
        
        limit = data.get('limit', 20)
        
        # Build MongoDB query
        mongo_query = {}
        
        if filters['brand']:
            mongo_query['brand'] = {'$regex': filters['brand'], '$options': 'i'}
        
        if filters['colors']:
            mongo_query['colors'] = {'$in': filters['colors']}
        
        if filters['styles']:
            mongo_query['styles'] = {'$in': filters['styles']}
        
        if filters['materials']:
            mongo_query['materials'] = {'$in': filters['materials']}
        
        if filters['belt_type']:
            mongo_query['belt_type'] = filters['belt_type']
        
        if filters['ai_category']:
            mongo_query['ai_category'] = filters['ai_category']
        
        if filters['ai_gender_target']:
            mongo_query['ai_gender_target'] = filters['ai_gender_target']
        
        if filters['gender']:
            mongo_query['gender'] = filters['gender']
        
        if filters['price_min'] or filters['price_max']:
            price_query = {}
            if filters['price_min']:
                price_query['$gte'] = str(filters['price_min'])
            if filters['price_max']:
                price_query['$lte'] = str(filters['price_max'])
            mongo_query['price'] = price_query
        
        # Execute search
        cursor = indexer.collection.find(mongo_query).limit(limit)
        results = list(cursor)
        
        # Format response
        formatted_results = []
        for watch in results:
            formatted_results.append({
                'id': str(watch['_id']),
                'name': watch.get('name', ''),
                'price': watch.get('price', '0'),
                'brand': watch.get('brand', 'Unknown'),
                'colors': watch.get('colors', []),
                'styles': watch.get('styles', []),
                'materials': watch.get('materials', []),
                'belt_type': watch.get('belt_type', 'unknown'),
                'ai_category': watch.get('ai_category', 'casual_watch'),
                'ai_gender_target': watch.get('ai_gender_target', 'unisex'),
                'image_urls': watch.get('image_urls', []),
                'url': watch.get('url', ''),
                'gender': watch.get('gender', 'Unisex')
            })
        
        return jsonify({
            'filters_applied': {k: v for k, v in filters.items() if v},
            'results_count': len(formatted_results),
            'results': formatted_results
        })
        
    except Exception as e:
        logger.error(f"Error in filtered search: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/stats', methods=['GET'])
def get_stats():
    """Get database and indexing statistics"""
    try:
        # Get indexing stats
        indexing_stats = indexer.get_indexing_stats()
        
        # Get RAG system stats
        rag_stats = rag_system.get_database_stats()
        
        return jsonify({
            'indexing_stats': indexing_stats,
            'database_stats': rag_stats,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/filters/options', methods=['GET'])
def get_filter_options():
    """Get available filter options"""
    try:
        # Get unique values for filters
        brands = indexer.collection.distinct('brand')
        colors = []
        styles = []
        materials = []
        belt_types = indexer.collection.distinct('belt_type')
        genders = indexer.collection.distinct('gender')
        
        # Get unique colors, styles, materials
        for field in ['colors', 'styles', 'materials']:
            pipeline = [
                {'$unwind': f'${field}'},
                {'$group': {'_id': f'${field}'}},
                {'$sort': {'_id': 1}}
            ]
            values = [item['_id'] for item in indexer.collection.aggregate(pipeline)]
            
            if field == 'colors':
                colors = values
            elif field == 'styles':
                styles = values
            elif field == 'materials':
                materials = values
        
        return jsonify({
            'brands': sorted([b for b in brands if b]),
            'colors': sorted(colors),
            'styles': sorted(styles),
            'materials': sorted(materials),
            'belt_types': sorted([bt for bt in belt_types if bt and bt != 'unknown']),
            'genders': sorted([g for g in genders if g])
        })
        
    except Exception as e:
        logger.error(f"Error getting filter options: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/chat', methods=['POST'])
def chat_query():
    """Natural language chat interface"""
    try:
        data = request.get_json()
        message = data.get('message', '')
        
        if not message:
            return jsonify({'error': 'Message parameter is required'}), 400
        
        # Use RAG system for natural language processing
        results = rag_system.search_watches(message, limit=5)
        response_text = rag_system.format_watch_response(results, message)
        
        return jsonify({
            'user_message': message,
            'bot_response': response_text,
            'results_count': len(results),
            'results': [{
                'id': str(watch['_id']),
                'name': watch.get('name', ''),
                'price': watch.get('price', '0'),
                'brand': watch.get('brand', 'Unknown'),
                'image_urls': watch.get('image_urls', []),
                'url': watch.get('url', '')
            } for watch in results]
        })
        
    except Exception as e:
        logger.error(f"Error in chat query: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8002, debug=False)