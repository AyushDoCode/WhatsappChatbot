"""
AI-Powered Product Search with Context Caching
Uses Gemini AI to recommend products from MongoDB database
Smart product suggestions with pagination (10 products at a time)
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pymongo import MongoClient
import requests
from PIL import Image
from io import BytesIO
import zipfile
import re
import json
import time
from typing import List, Dict
from datetime import timedelta
import os
import base64
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import google.generativeai as genai
from google.generativeai import caching

# Setup logging
logger = logging.getLogger(__name__)

# Initialize Gemini API
GEMINI_API_KEY = os.getenv('Google_api') or os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
GEMINI_MODEL = os.getenv('google_model', 'gemini-2.0-flash-exp')

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    logger.info(f"✅ Gemini configured with model: {GEMINI_MODEL}")
else:
    logger.warning("⚠️ No Gemini API key found. AI search will not work.")

app = FastAPI(title="Text-based Product Search with Images")

# Add CORS middleware to allow frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for testing
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# MongoDB Configuration
DB_NAME = os.getenv("DATABASE_NAME", "watchvine_refined")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "products")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://admin:strongpassword123@72.62.76.36:27017/?authSource=admin")
client = MongoClient(MONGO_URI)
db = client[DB_NAME]
collection = db[COLLECTION_NAME]

# AI Product Recommender with Context Caching
cached_content = None
last_cache_update = 0
CACHE_TTL = 3600  # 1 hour
user_pagination = {}  # Store pagination state: {phone_number: {"products": [...], "sent_count": 0}}

# ============================================================================
# BRAND NAME MAPPING (User input → Database format)
# Website stores brand names with modified spelling for copyright reasons
# ============================================================================
BRAND_MAPPING = {
    # Watch brands
    'fossil': 'fossi_l',
    'tissot': 'tisso_t',
    'armani': 'arman_i',
    'tommy': 'tomm_y',
    'tommy hilfiger': 'tomm_y',
    'rolex': 'role_x',
    'rado': 'rad_o',
    'omega': 'omeg_a',
    'patek': 'Patek_Philippe',
    'patek philippe': 'Patek_Philippe',
    'patek phillips': 'Patek_Philippe',
    'hublot': 'hublo_t',
    'cartier': 'cartie_r',
    'ap': 'Audemars',
    'audemars': 'Audemars',
    'tag': 'tag',
    'tag heuer': 'tag',
    'tag huer': 'tag',
    'mk': 'mic',
    'michael kors': 'mic',
    'alix': 'alix',
    'naviforce': 'naviforce',
    'reward': 'reward',
    'ax': 'ax',
    'armani exchange': 'arman_i',
    
    # Add more as needed
}

def normalize_brand_name(keyword: str) -> str:
    """
    Convert user-friendly brand name to database format.
    Example: "armani" → "arman_i", "rolex" → "role_x"
    """
    keyword_lower = keyword.lower().strip()
    
    # Check exact match first
    if keyword_lower in BRAND_MAPPING:
        return BRAND_MAPPING[keyword_lower]
    
    # Check if keyword contains a brand name
    for user_name, db_name in BRAND_MAPPING.items():
        if user_name in keyword_lower or keyword_lower in user_name:
            return db_name
    
    # Return original if no mapping found
    return keyword


# Generic product type keywords that may not appear in product names
GENERIC_TYPES = ['watch', 'watches', 'shoe', 'shoes', 'bag', 'bags', 'sunglass', 'sunglasses']

def is_generic_type(keyword: str) -> bool:
    """Check if keyword is a generic product type"""
    return keyword.lower() in GENERIC_TYPES

# Temporary folder for images
TEMP_FOLDER = "temp_images"
os.makedirs(TEMP_FOLDER, exist_ok=True)


class SearchRequest(BaseModel):
    query: str  # e.g., "rolex watch", "michael kors bag"
    max_results: int = 10
    min_price: float = None  # Optional: minimum price filter
    max_price: float = None  # Optional: maximum price filter


class RangeSearchRequest(BaseModel):
    category: str  # e.g., "watches", "bags", "shoes", "sunglasses"
    min_price: float  # Minimum price for range
    max_price: float  # Maximum price for range
    max_results: int = 10  # Maximum results to return


def download_image_from_url(url: str, save_path: str) -> bool:
    """Download image from URL and save locally."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            img = Image.open(BytesIO(response.content))
            img.save(save_path)
            return True
        return False
    except Exception as e:
        print(f"Error downloading {url}: {e}")
        return False


def search_products_by_price_range(category: str, min_price: float, max_price: float, max_results: int = 10) -> List[Dict]:
    """
    Search products by price range within a specific category.
    Returns all products in the category between min_price and max_price.
    
    Example: category="watches", min_price=1500, max_price=2000
    Returns all watches priced between ₹1500 and ₹2000
    """
    try:
        # Build query for category and price range
        query = {
            "$and": [
                {"category_key": category.lower()},  # Match category
                {
                    "$expr": {
                        "$and": [
                            {"$gte": [{"$toDouble": "$price"}, min_price]},
                            {"$lte": [{"$toDouble": "$price"}, max_price]}
                        ]
                    }
                }
            ]
        }
        
        # Execute search
        results = list(collection.find(
            query,
            {"name": 1, "price": 1, "image_urls": 1, "url": 1, "category": 1, "category_key": 1}
        ).limit(max_results))
        
        print(f"🔍 RANGE Search: Category='{category}', Price: ₹{min_price} - ₹{max_price}")
        print(f"✅ Found {len(results)} products in price range")
        
        return results
        
    except Exception as e:
        print(f"❌ Error in range search: {e}")
        return []


def get_or_create_product_cache():
    """
    Creates or retrieves cached content with ALL MongoDB products
    This cache contains the entire product database for AI to search from
    """
    global cached_content, last_cache_update
    
    if not GEMINI_API_KEY:
        return None
    
    current_time = time.time()
    
    # If cache is still valid, return it
    if cached_content and (current_time - last_cache_update < CACHE_TTL):
        logger.info(f"♻️ Using existing product cache")
        return cached_content
    
    try:
        # Fetch ALL products from MongoDB
        logger.info("📦 Loading all products from MongoDB...")
        all_products = list(collection.find(
            {},
            {"_id": 0, "name": 1, "price": 1, "category": 1, "category_key": 1, "url": 1, "image_urls": 1}
        ))
        
        total_products = len(all_products)
        logger.info(f"✅ Loaded {total_products} products from database")
        
        # Convert to JSON string for caching
        products_json = json.dumps(all_products, default=str, indent=2)
        
        # Estimate token count
        estimated_tokens = len(products_json) / 4
        logger.info(f"📊 Product data size: ~{int(estimated_tokens)} tokens")
        
        if estimated_tokens < 1000:
            logger.warning("⚠️ Product data too small for caching, using direct AI calls")
            return None
        
        # Create system instruction with product data
        system_instruction = f"""You are a smart product recommendation AI for WatchVine - a luxury accessories store.

Your task: Recommend products from the product database based on user queries.

PRODUCT DATABASE ({total_products} products):
{products_json}

CRITICAL RULES:
1. ALWAYS respond in valid JSON format ONLY
2. When user asks for products (e.g., "show me women watches", "gents watch", "fossil ladies watch"):
   - Search the product database above
   - Filter by category_key (mens_watch, womens_watch, mens_sunglasses, etc.)
   - Return maximum 10 products at a time
   - Include: name, price, category, category_key, url, image_urls (first image only)

3. GENDER/CATEGORY DETECTION:
   - "ladies watch" / "women watch" → category_key: "womens_watch"
   - "gents watch" / "men watch" → category_key: "mens_watch"
   - "ladies sunglasses" → category_key: "womens_sunglasses"
   - "mens sunglasses" → category_key: "mens_sunglasses"
   - "ladies shoes" → category_key: "womens_shoes"
   - "mens shoes" → category_key: "mens_shoes"
   - "bag" / "handbag" → category_key: "handbag"
   
4. BRAND FILTERING:
   - If brand mentioned (fossil, rolex, armani, etc.), filter products by that brand
   - Example: "fossil ladies watch" → Filter womens_watch category + name contains "fossil"
   
5. PRICE FILTERING:
   - "under 5000" → max_price: 5000
   - "above 3000" → min_price: 3000
   - "between 2000 to 5000" → min_price: 2000, max_price: 5000

6. PAGINATION:
   - Always send maximum 10 products per response
   - If user says "show more" / "next" / "more products", send next 10 products
   
7. MORE IMAGES REQUEST:
   - If user asks "show me more images" for a specific product, return ALL image_urls for that product

OUTPUT FORMAT (JSON ONLY):
{{
  "action": "show_products" | "show_more_images" | "chat",
  "products": [
    {{
      "name": "Product Name",
      "price": "1234.00",
      "category": "Men's Watches",
      "category_key": "mens_watch",
      "url": "https://...",
      "image_url": "https://...jpg" (first image only)
    }}
  ],
  "total_found": 50,
  "message": "Found 50 products. Showing 10..."
}}

IMPORTANT: Return ONLY JSON, no explanations, no markdown, no extra text."""

        # Create cache
        logger.info(f"🆕 Creating new product cache with model: {GEMINI_MODEL}...")
        
        # Ensure model has 'models/' prefix
        model_name = GEMINI_MODEL if GEMINI_MODEL.startswith('models/') else f'models/{GEMINI_MODEL}'
        
        cached_content = caching.CachedContent.create(
            model=model_name,
            display_name="watchvine_products_cache",
            system_instruction=system_instruction,
            ttl=timedelta(hours=2)
        )
        
        last_cache_update = current_time
        logger.info(f"✅ Product cache created: {cached_content.name}")
        return cached_content
        
    except Exception as e:
        logger.error(f"❌ Cache creation failed: {e}")
        return None


def search_products_by_text(query: str, max_results: int = 10, category_filter: str = None, min_price: float = None, max_price: float = None) -> List[Dict]:
    """
    OLD WORKING METHOD: Keyword-based search with category filtering
    Searches products in MongoDB with proper category_key filtering
    
    Example: "fossil ladies watch" with category_filter="womens_watch" 
             → Searches "fossil" in ONLY womens_watch category
    """
    
    # Split query into keywords
    keywords = [kw.strip().lower() for kw in query.strip().split() if len(kw.strip()) > 1]
    
    if not keywords and not category_filter:
        return []
    
    # STEP 1: Normalize brand names (rolex → role_x, armani → arman_i, etc.)
    normalized_keywords = []
    essential_keywords = []
    
    # If no keywords but category_filter provided, do category-only search
    if not keywords and category_filter:
        logger.info(f"📂 Category-only search: {category_filter}")
        and_conditions = []
    elif keywords:
        for keyword in keywords:
            normalized = normalize_brand_name(keyword)
            
            # Skip generic type keywords if no brand specified
            if is_generic_type(normalized) and len(keywords) > 1:
                logger.info(f"⏭️ Skipping generic type: '{keyword}'")
                continue
            
            normalized_keywords.append(normalized)
            essential_keywords.append(normalized)
        
        # Log the transformation
        if normalized_keywords != keywords:
            logger.info(f"🔄 Keywords: {keywords} → {normalized_keywords}")
        
        keywords = essential_keywords if essential_keywords else []
        
        # Build patterns for ALL keywords
        patterns = []
        for keyword in keywords:
            if keyword.endswith('s'):
                base = keyword[:-1]
                pattern = re.compile(f"{re.escape(base)}e?s?", re.IGNORECASE)
            elif keyword in ['watch', 'shoe', 'bag', 'glass', 'sunglass']:
                pattern = re.compile(f"{re.escape(keyword)}e?s?", re.IGNORECASE)
            else:
                pattern = re.compile(re.escape(keyword), re.IGNORECASE)
            patterns.append(pattern)
        
        and_conditions = [{"name": {"$regex": pattern}} for pattern in patterns]
    else:
        and_conditions = []
    
    # STEP 2: Add category filter (MOST IMPORTANT)
    if category_filter:
        and_conditions.append({"category_key": category_filter})
        logger.info(f"✅ Category filter: {category_filter}")
    
    # STEP 3: Add price filters
    if min_price is not None or max_price is not None:
        price_conditions = []
        if min_price is not None:
            price_conditions.append({"$gte": [{"$toDouble": "$price"}, min_price]})
        if max_price is not None:
            price_conditions.append({"$lte": [{"$toDouble": "$price"}, max_price]})
        
        and_conditions.append({"$expr": {"$and": price_conditions}})
        logger.info(f"💰 Price filter: ₹{min_price or 0}-₹{max_price or '∞'}")
    
    # Execute search
    if not and_conditions:
        # If no conditions, return empty (don't return all products)
        return []
    
    results = list(collection.find(
        {"$and": and_conditions} if len(and_conditions) > 1 else and_conditions[0],
        {"name": 1, "price": 1, "image_urls": 1, "url": 1, "category": 1, "category_key": 1}
    ).limit(max_results))
    
    logger.info(f"🔍 Found {len(results)} products for query: '{query}'")
    
    return results


@app.get("/")
async def root():
    return {
        "service": "Text-based Product Search with Images",
        "endpoints": {
            "/search": "POST - Search products by text and get images",
            "/search/range": "POST - Search products by price range within category",
            "/search/images": "POST - Search and download images as ZIP",
            "/search/images-list": "POST - Search and get images as base64 (for WhatsApp)",
            "/products/count": "GET - Get total products in database",
            "/health": "GET - Health check"
        }
    }


@app.post("/search")
async def search_products(request: SearchRequest):
    """
    Search products by text query and return product info with image URLs.
    
    Example request:
    {
        "query": "rolex",
        "max_results": 10
    }
    """
    if not request.query or len(request.query.strip()) < 2:
        raise HTTPException(status_code=400, detail="Query must be at least 2 characters")
    
    # Search in MongoDB
    products = search_products_by_text(request.query, request.max_results, None, request.min_price, request.max_price)
    
    if not products:
        return JSONResponse(
            status_code=404,
            content={
                "status": "no_match",
                "message": f"No products found matching '{request.query}'",
                "total_results": 0
            }
        )
    
    # Format results
    results = []
    total_images = 0
    
    for product in products:
        product_data = {
            "product_name": product.get("name", "Unknown"),
            "price": product.get("price", "N/A"),
            "product_url": product.get("url", ""),
            "images": product.get("image_urls", []),
            "image_count": len(product.get("image_urls", []))
        }
        results.append(product_data)
        total_images += product_data["image_count"]
    
    return {
        "status": "success",
        "query": request.query,
        "total_products": len(results),
        "total_images": total_images,
        "products": results
    }


@app.post("/search/range")
async def search_products_in_range(request: RangeSearchRequest):
    """
    Search products by price range within a specific category.
    Returns all products in that price range with images.
    
    Example request:
    {
        "category": "watches",
        "min_price": 1500,
        "max_price": 2000,
        "max_results": 20
    }
    """
    if not request.category or len(request.category.strip()) < 2:
        raise HTTPException(status_code=400, detail="Category must be at least 2 characters")
    
    if request.min_price < 0 or request.max_price < 0:
        raise HTTPException(status_code=400, detail="Prices must be positive")
    
    if request.min_price > request.max_price:
        raise HTTPException(status_code=400, detail="Min price cannot be greater than max price")
    
    # Search products in price range
    products = search_products_by_price_range(request.category, request.min_price, request.max_price, request.max_results)
    
    if not products:
        return JSONResponse(
            status_code=404,
            content={
                "status": "no_match",
                "message": f"No products found in {request.category} category between ₹{request.min_price} and ₹{request.max_price}",
                "total_results": 0
            }
        )
    
    # Format results
    results = []
    total_images = 0
    
    for product in products:
        product_data = {
            "product_name": product.get("name", "Unknown"),
            "price": product.get("price", "N/A"),
            "product_url": product.get("url", ""),
            "images": product.get("image_urls", []),
            "image_count": len(product.get("image_urls", []))
        }
        results.append(product_data)
        total_images += product_data["image_count"]
    
    return {
        "status": "success",
        "category": request.category,
        "price_range": f"₹{request.min_price} - ₹{request.max_price}",
        "total_products": len(results),
        "total_images": total_images,
        "products": results
    }


@app.post("/search/download")
async def search_and_download_images(request: SearchRequest):
    """
    Search products and download all images as ZIP file.
    Returns a downloadable ZIP containing all product images.
    
    Example request:
    {
        "query": "rolex",
        "max_results": 5
    }
    """
    if not request.query or len(request.query.strip()) < 2:
        raise HTTPException(status_code=400, detail="Query must be at least 2 characters")
    
    # Search products
    products = search_products_by_text(request.query, request.max_results, None, request.min_price, request.max_price)
    
    if not products:
        raise HTTPException(
            status_code=404, 
            detail=f"No products found matching '{request.query}'"
        )
    
    # Create ZIP file in memory
    zip_buffer = BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        image_counter = 1
        
        for product_idx, product in enumerate(products, 1):
            product_name = product.get("name", "Unknown")
            # Sanitize product name for folder
            safe_name = re.sub(r'[^\w\s-]', '', product_name).strip().replace(' ', '_')[:50]
            price = product.get("price", "N/A")
            image_urls = product.get("image_urls", [])
            
            # Create product info text file
            info_content = f"Product: {product_name}\n"
            info_content += f"Price: ₹{price}\n"
            info_content += f"URL: {product.get('url', 'N/A')}\n"
            info_content += f"Images: {len(image_urls)}\n"
            
            zip_file.writestr(f"{safe_name}/product_info.txt", info_content)
            
            # Download and add images
            for img_idx, img_url in enumerate(image_urls, 1):
                try:
                    # Download image
                    temp_path = os.path.join(TEMP_FOLDER, f"temp_{image_counter}.jpg")
                    
                    if download_image_from_url(img_url, temp_path):
                        # Add to ZIP
                        zip_file.write(
                            temp_path, 
                            f"{safe_name}/image_{img_idx}.jpg"
                        )
                        # Cleanup
                        os.remove(temp_path)
                        image_counter += 1
                        
                except Exception as e:
                    print(f"Error processing image {img_url}: {e}")
                    continue
    
    # Prepare ZIP for download
    zip_buffer.seek(0)
    
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename={request.query.replace(' ', '_')}_products.zip"
        }
    )


def download_and_convert_to_base64(image_url: str) -> str:
    """Download image and convert to base64 string (plain base64, no prefix)."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        response = requests.get(image_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            # Convert to base64 - NO PREFIX for Evolution API
            base64_string = base64.b64encode(response.content).decode('utf-8')
            return base64_string
        return None
    except Exception as e:
        print(f"Error downloading {image_url}: {e}")
        return None


def download_all_images_parallel(image_urls: List[str], max_workers: int = 10) -> List[str]:
    """Download multiple images in parallel and return base64 strings in order."""
    base64_images = [None] * len(image_urls)  # Pre-allocate list to maintain order
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all downloads and keep track of their index
        future_to_index = {
            executor.submit(download_and_convert_to_base64, url): idx 
            for idx, url in enumerate(image_urls)
        }
        
        # Collect results and place them in correct position
        for future in as_completed(future_to_index):
            idx = future_to_index[future]
            try:
                result = future.result()
                if result:
                    base64_images[idx] = result
            except Exception as e:
                print(f"Error in parallel download at index {idx}: {e}")
    
    # Filter out None values (failed downloads)
    return [img for img in base64_images if img is not None]


@app.post("/search/images-list")
async def search_and_get_images(request: SearchRequest):
    """
    Search products and return images as base64 (FAST - Parallel download).
    Optimized for WhatsApp bot integration with parallel image processing.
    """
    if not request.query or len(request.query.strip()) < 2:
        raise HTTPException(status_code=400, detail="Query must be at least 2 characters")
    
    # Search products
    products = search_products_by_text(request.query, request.max_results, None, request.min_price, request.max_price)
    
    if not products:
        return {
            "status": "no_match",
            "message": f"No products found matching '{request.query}'",
            "products": []
        }
    
    results = []
    
    # Collect all image URLs for parallel download
    all_image_urls = []
    product_image_mapping = []  # Track which images belong to which product
    
    for product in products:
        product_name = product.get("name", "Unknown")
        price = product.get("price", "N/A")
        image_urls = product.get("image_urls", [])
        
        if image_urls:
            # Take all images (not just first one)
            product_image_mapping.append({
                "product_name": product_name,
                "price": price,
                "product_url": product.get("url", ""),
                "start_index": len(all_image_urls),
                "image_count": len(image_urls)
            })
            all_image_urls.extend(image_urls)
    
    # Download all images in parallel
    print(f"Downloading {len(all_image_urls)} images in parallel...")
    base64_images = download_all_images_parallel(all_image_urls, max_workers=15)
    
    # Map base64 images back to products
    for product_info in product_image_mapping:
        start_idx = product_info["start_index"]
        end_idx = start_idx + product_info["image_count"]
        
        # Get base64 images for this product
        product_images = []
        for i in range(start_idx, end_idx):
            if i < len(base64_images):
                product_images.append(base64_images[i])
        
        if product_images:
            results.append({
                "product_name": product_info["product_name"],
                "price": product_info["price"],
                "product_url": product_info["product_url"],
                "images_base64": product_images,
                "total_images": len(product_images)
            })
    
    return {
        "status": "success",
        "query": request.query,
        "total_products": len(results),
        "total_images": len(base64_images),
        "products": results
    }


@app.get("/products/count")
async def get_product_count():
    """Get total number of products in database."""
    count = collection.count_documents({})
    return {
        "total_products": count,
        "database": DB_NAME,
        "collection": COLLECTION_NAME
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    try:
        # Test MongoDB connection
        collection.find_one()
        db_status = "connected"
    except:
        db_status = "disconnected"
    
    return {
        "status": "healthy",
        "database": db_status,
        "total_products": collection.count_documents({})
    }


if __name__ == "__main__":
    import uvicorn
    
    print("="*80)
    print("🚀 Text-based Product Search API with Image Download")
    print("="*80)
    print("\nEndpoints:")
    print("  POST /search              - Search products by text")
    print("  POST /search/download     - Download images as ZIP")
    print("  POST /search/images-list  - Get images as base64 (for WhatsApp)")
    print("  GET  /products/count      - Get total products")
    print("  GET  /health              - Health check")
    print("\nStarting server on http://localhost:8001")
    print("="*80)
    
    uvicorn.run(app, host="0.0.0.0", port=8001)
