#!/usr/bin/env python3
"""
Test Watch System - Complete Integration Test
Tests all components of the watch system
"""

import requests
import time
import json
import logging
from datetime import datetime
from typing import Dict, List

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class WatchSystemTester:
    def __init__(self, base_url: str = "http://localhost"):
        self.base_url = base_url
        self.bot_api = f"{base_url}:8000"
        self.search_api = f"{base_url}:8002"
        
        # Test results
        self.test_results = {
            'api_health': False,
            'search_api_health': False,
            'text_search': False,
            'image_search': False,
            'filtered_search': False,
            'chat_interface': False,
            'system_stats': False
        }
    
    def test_api_health(self) -> bool:
        """Test main bot API health"""
        try:
            response = requests.get(f"{self.bot_api}/health", timeout=10)
            if response.status_code == 200:
                data = response.json()
                logging.info(f"✅ Bot API Health: {data.get('status', 'unknown')}")
                return True
            else:
                logging.error(f"❌ Bot API Health Check Failed: {response.status_code}")
                return False
        except Exception as e:
            logging.error(f"❌ Bot API Connection Error: {e}")
            return False
    
    def test_search_api_health(self) -> bool:
        """Test search API health"""
        try:
            response = requests.get(f"{self.search_api}/health", timeout=10)
            if response.status_code == 200:
                data = response.json()
                logging.info(f"✅ Search API Health: {data.get('status', 'unknown')}")
                
                # Show database stats
                db_stats = data.get('database_stats', {})
                logging.info(f"   Total Watches: {db_stats.get('total_watches', 'N/A')}")
                logging.info(f"   AI Enhanced: {db_stats.get('ai_enhanced_watches', 'N/A')}")
                logging.info(f"   Vector Count: {db_stats.get('total_vectors', 'N/A')}")
                
                return True
            else:
                logging.error(f"❌ Search API Health Check Failed: {response.status_code}")
                return False
        except Exception as e:
            logging.error(f"❌ Search API Connection Error: {e}")
            return False
    
    def test_text_search(self) -> bool:
        """Test text-based search functionality"""
        try:
            test_queries = [
                "luxury watches",
                "black watches",
                "rolex",
                "silver metal belt",
                "sporty watches"
            ]
            
            for query in test_queries:
                payload = {
                    "query": query,
                    "limit": 3
                }
                
                response = requests.post(
                    f"{self.search_api}/search/text",
                    json=payload,
                    timeout=10
                )
                
                if response.status_code == 200:
                    data = response.json()
                    results_count = data.get('results_count', 0)
                    logging.info(f"✅ Text Search '{query}': {results_count} results")
                    
                    # Show sample result
                    if data.get('results'):
                        sample = data['results'][0]
                        logging.info(f"   Sample: {sample.get('name', 'N/A')} - {sample.get('brand', 'N/A')}")
                else:
                    logging.error(f"❌ Text Search Failed for '{query}': {response.status_code}")
                    return False
                
                time.sleep(0.5)  # Rate limiting
            
            return True
            
        except Exception as e:
            logging.error(f"❌ Text Search Error: {e}")
            return False
    
    def test_image_search(self) -> bool:
        """Test image-based search functionality"""
        try:
            # Use a sample image URL (you can replace with actual watch image)
            test_image_url = "https://cdn.cartpe.in/images/gallery_md/6960cd2ca908c0.jpeg"
            
            payload = {
                "image_url": test_image_url,
                "limit": 3
            }
            
            response = requests.post(
                f"{self.search_api}/search/image",
                json=payload,
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                results_count = data.get('results_count', 0)
                logging.info(f"✅ Image Search: {results_count} similar watches found")
                
                # Show similarity scores
                for i, result in enumerate(data.get('results', [])[:3], 1):
                    score = result.get('similarity_score', 0)
                    name = result.get('watch_name', 'N/A')
                    logging.info(f"   {i}. {name} (Similarity: {score:.3f})")
                
                return True
            else:
                logging.error(f"❌ Image Search Failed: {response.status_code}")
                return False
                
        except Exception as e:
            logging.error(f"❌ Image Search Error: {e}")
            return False
    
    def test_filtered_search(self) -> bool:
        """Test advanced filtered search"""
        try:
            test_filters = [
                {
                    "colors": ["Silver", "Black"],
                    "limit": 5
                },
                {
                    "belt_type": "metal_belt",
                    "limit": 5
                },
                {
                    "styles": ["Luxury"],
                    "price_min": 1000,
                    "limit": 3
                }
            ]
            
            for i, filters in enumerate(test_filters, 1):
                response = requests.post(
                    f"{self.search_api}/search/filters",
                    json=filters,
                    timeout=10
                )
                
                if response.status_code == 200:
                    data = response.json()
                    results_count = data.get('results_count', 0)
                    filters_applied = data.get('filters_applied', {})
                    logging.info(f"✅ Filtered Search {i}: {results_count} results")
                    logging.info(f"   Filters: {filters_applied}")
                else:
                    logging.error(f"❌ Filtered Search {i} Failed: {response.status_code}")
                    return False
                
                time.sleep(0.5)
            
            return True
            
        except Exception as e:
            logging.error(f"❌ Filtered Search Error: {e}")
            return False
    
    def test_chat_interface(self) -> bool:
        """Test natural language chat interface"""
        try:
            test_messages = [
                "Show me black luxury watches",
                "I want a watch with leather belt",
                "Find sporty watches under 2000",
                "Show me rolex watches",
                "I need a formal watch for office"
            ]
            
            for message in test_messages:
                payload = {
                    "message": message
                }
                
                response = requests.post(
                    f"{self.search_api}/chat",
                    json=payload,
                    timeout=10
                )
                
                if response.status_code == 200:
                    data = response.json()
                    results_count = data.get('results_count', 0)
                    bot_response = data.get('bot_response', '')
                    logging.info(f"✅ Chat: '{message}' -> {results_count} results")
                    logging.info(f"   Bot: {bot_response[:100]}...")
                else:
                    logging.error(f"❌ Chat Failed for '{message}': {response.status_code}")
                    return False
                
                time.sleep(0.5)
            
            return True
            
        except Exception as e:
            logging.error(f"❌ Chat Interface Error: {e}")
            return False
    
    def test_system_stats(self) -> bool:
        """Test system statistics endpoint"""
        try:
            response = requests.get(f"{self.search_api}/stats", timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                indexing_stats = data.get('indexing_stats', {})
                database_stats = data.get('database_stats', {})
                
                logging.info("✅ System Statistics:")
                logging.info(f"   Total Watches: {indexing_stats.get('total_watches', 'N/A')}")
                logging.info(f"   AI Enhanced: {indexing_stats.get('ai_enhanced_watches', 'N/A')}")
                logging.info(f"   Vector Images: {indexing_stats.get('total_vectors', 'N/A')}")
                logging.info(f"   Indexing Coverage: {indexing_stats.get('indexing_coverage', 0):.1f}%")
                
                # Show top brands
                top_brands = database_stats.get('top_brands', [])
                if top_brands:
                    logging.info("   Top Brands:")
                    for brand in top_brands[:5]:
                        logging.info(f"     - {brand.get('_id', 'Unknown')}: {brand.get('count', 0)}")
                
                return True
            else:
                logging.error(f"❌ Stats Failed: {response.status_code}")
                return False
                
        except Exception as e:
            logging.error(f"❌ Stats Error: {e}")
            return False
    
    def run_all_tests(self) -> Dict:
        """Run all system tests"""
        logging.info("🧪 STARTING COMPLETE WATCH SYSTEM TESTS")
        logging.info("=" * 50)
        
        start_time = time.time()
        
        # Run tests
        tests = [
            ('API Health Check', self.test_api_health, 'api_health'),
            ('Search API Health Check', self.test_search_api_health, 'search_api_health'),
            ('Text Search Test', self.test_text_search, 'text_search'),
            ('Image Search Test', self.test_image_search, 'image_search'),
            ('Filtered Search Test', self.test_filtered_search, 'filtered_search'),
            ('Chat Interface Test', self.test_chat_interface, 'chat_interface'),
            ('System Stats Test', self.test_system_stats, 'system_stats')
        ]
        
        for test_name, test_func, result_key in tests:
            logging.info(f"\n🔍 Running: {test_name}")
            try:
                result = test_func()
                self.test_results[result_key] = result
                if result:
                    logging.info(f"✅ {test_name} PASSED")
                else:
                    logging.error(f"❌ {test_name} FAILED")
            except Exception as e:
                logging.error(f"❌ {test_name} ERROR: {e}")
                self.test_results[result_key] = False
            
            time.sleep(1)  # Delay between tests
        
        # Summary
        total_time = time.time() - start_time
        passed_tests = sum(1 for result in self.test_results.values() if result)
        total_tests = len(self.test_results)
        
        logging.info("\n" + "=" * 50)
        logging.info("📊 TEST SUMMARY")
        logging.info("=" * 50)
        logging.info(f"Tests Passed: {passed_tests}/{total_tests}")
        logging.info(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
        logging.info(f"Total Time: {total_time:.1f} seconds")
        
        if passed_tests == total_tests:
            logging.info("🎉 ALL TESTS PASSED! System is working perfectly!")
        else:
            logging.warning(f"⚠️  {total_tests - passed_tests} tests failed. Check the logs above.")
        
        return self.test_results

def main():
    """Main test execution"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Test Watch System')
    parser.add_argument('--host', default='localhost', help='Host address')
    parser.add_argument('--test', choices=['all', 'api', 'search', 'chat'], 
                       default='all', help='Test type to run')
    
    args = parser.parse_args()
    
    tester = WatchSystemTester(f"http://{args.host}")
    
    if args.test == 'all':
        results = tester.run_all_tests()
    elif args.test == 'api':
        results = {
            'api_health': tester.test_api_health(),
            'search_api_health': tester.test_search_api_health()
        }
    elif args.test == 'search':
        results = {
            'text_search': tester.test_text_search(),
            'image_search': tester.test_image_search(),
            'filtered_search': tester.test_filtered_search()
        }
    elif args.test == 'chat':
        results = {
            'chat_interface': tester.test_chat_interface()
        }
    
    # Print final status
    success = all(results.values())
    exit_code = 0 if success else 1
    
    if success:
        print("\n🎊 WATCH SYSTEM IS FULLY OPERATIONAL!")
    else:
        print("\n🔧 WATCH SYSTEM NEEDS ATTENTION!")
    
    exit(exit_code)

if __name__ == "__main__":
    main()