#!/usr/bin/env python3
"""
Run the complete watch database enhancement process
"""

import sys
from watch_enhancer import WatchEnhancer
from watch_rag_system import WatchRAGSystem

def main():
    MONGODB_URI = "mongodb://admin:strongpassword123@72.62.76.36:27017/?authSource=admin"
    
    print("=== STARTING WATCH DATABASE ENHANCEMENT ===\n")
    
    # Step 1: Enhance existing database
    print("Step 1: Enhancing existing watch products...")
    enhancer = WatchEnhancer(MONGODB_URI)
    
    try:
        # Run the enhancement
        processed = enhancer.enhance_all_watches(batch_size=50)
        print(f"✅ Enhanced {processed} watch products")
        
        # Get summary
        enhancer.get_enhancement_summary()
        
    finally:
        enhancer.close()
    
    print("\n" + "="*60)
    
    # Step 2: Test the RAG system
    print("\nStep 2: Testing enhanced RAG system...")
    rag = WatchRAGSystem(MONGODB_URI)
    
    try:
        # Test with sample queries
        test_queries = [
            "show me black watches",
            "I want a luxury watch for men",
            "find rolex watches",
            "show me minimalistic watches",
            "get me audemars piguet watches"
        ]
        
        print("\n=== RAG SYSTEM TEST ===")
        for i, query in enumerate(test_queries, 1):
            print(f"\nTest {i}: '{query}'")
            results = rag.search_watches(query, limit=3)
            print(f"Found {len(results)} matches")
            
            if results:
                for j, watch in enumerate(results, 1):
                    print(f"  {j}. {watch.get('brand', 'Unknown')} - {watch.get('name', 'Unnamed')[:50]}... (₹{watch.get('price', 'N/A')})")
        
        # Show database statistics
        print(f"\n=== DATABASE STATISTICS ===")
        stats = rag.get_database_stats()
        print(f"Total watches: {stats['total_watches']}")
        print(f"Top brands: {[b['_id'] for b in stats['top_brands'][:5]]}")
        gender_dist = [f"{g['_id']}: {g['count']}" for g in stats['gender_distribution']]
        print(f"Gender distribution: {gender_dist}")
        
    finally:
        rag.close()
    
    print(f"\n✅ ENHANCEMENT COMPLETE!")
    print(f"\nYour watch database is now ready for intelligent chatbot queries!")
    print(f"\nCustomers can now ask questions like:")
    print(f"  - 'Show me black Rolex watches'")
    print(f"  - 'I want a minimalistic watch'")
    print(f"  - 'Find luxury watches for men'")
    print(f"  - 'Show me watches under ₹2000'")

if __name__ == "__main__":
    main()