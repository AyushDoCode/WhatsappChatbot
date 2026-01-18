#!/usr/bin/env python3
"""
Monitor the progress of AI image enhancement
"""

import pymongo
from pymongo import MongoClient
import time
from datetime import datetime

MONGODB_URI = "mongodb://admin:strongpassword123@72.62.76.36:27017/?authSource=admin"

def monitor_progress():
    client = MongoClient(MONGODB_URI)
    db = client['watchvine_refined']
    collection = db['products']
    
    print("🔍 AI Enhancement Progress Monitor")
    print("=" * 50)
    
    # Get baseline stats
    total_watches = collection.count_documents({})
    ai_enhanced = collection.count_documents({"ai_analysis": {"$exists": True}})
    
    with_colors = collection.count_documents({"colors": {"$ne": []}})
    with_styles = collection.count_documents({"styles": {"$ne": []}})
    with_materials = collection.count_documents({"materials": {"$ne": []}})
    
    needs_enhancement = collection.count_documents({
        "$or": [
            {"colors": {"$size": 0}},
            {"styles": {"$size": 0}},
            {"materials": {"$size": 0}},
            {"ai_analysis": {"$exists": False}}
        ],
        "image_urls": {"$exists": True, "$ne": []}
    })
    
    print(f"📊 Current Stats ({datetime.now().strftime('%H:%M:%S')})")
    print(f"Total watches: {total_watches}")
    print(f"AI-enhanced: {ai_enhanced}")
    print(f"With colors: {with_colors}")
    print(f"With styles: {with_styles}")
    print(f"With materials: {with_materials}")
    print(f"Still need enhancement: {needs_enhancement}")
    print(f"Completion: {((ai_enhanced / total_watches) * 100):.1f}%")
    
    # Show recent AI enhancements
    recent = list(collection.find(
        {"ai_analysis.analyzed_at": {"$exists": True}},
        {"name": 1, "colors": 1, "styles": 1, "materials": 1, "ai_analysis.analyzed_at": 1}
    ).sort("ai_analysis.analyzed_at", -1).limit(5))
    
    if recent:
        print(f"\n🆕 Recently Enhanced:")
        for watch in recent:
            name = watch.get('name', 'Unknown')[:30]
            colors = ', '.join(watch.get('colors', [])[:3])
            styles = ', '.join(watch.get('styles', [])[:2])
            print(f"  • {name}: {colors} | {styles}")
    
    # Show top extracted values
    print(f"\n🎨 Top Colors Found:")
    colors_agg = list(collection.aggregate([
        {"$unwind": "$colors"},
        {"$group": {"_id": "$colors", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 8}
    ]))
    
    for item in colors_agg:
        print(f"  {item['_id']}: {item['count']}")
    
    print(f"\n✨ Top Styles Found:")
    styles_agg = list(collection.aggregate([
        {"$unwind": "$styles"},
        {"$group": {"_id": "$styles", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 6}
    ]))
    
    for item in styles_agg:
        print(f"  {item['_id']}: {item['count']}")
    
    client.close()

if __name__ == "__main__":
    monitor_progress()