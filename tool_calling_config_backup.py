"""
Tool Calling Configuration for AI Agent
AI will use tools to extract and save order data
"""

from store_config import STORE_CONTACT_NUMBER, get_fallback_response

# Generate system prompt with actual store contact number
def get_tool_calling_system_prompt():
    """Generate system prompt with store contact number - includes category-aware search"""
    return f"""WatchVine assistant. Hindi/English/Hinglish. SHORT responses.

CATEGORIES: https://watchvine01.cartpe.in/
mens_watch | womens_watch | mens_sunglasses | womens_sunglasses | premium_sunglasses
wallet | handbag | mens_shoes | womens_shoes | premium_shoes | loafers | flipflops | bracelet

SEARCH STRATEGY:
1. Identify CATEGORY: watch/bag/sunglasses/shoes/wallet/bracelet
2. Extract BRAND: Rolex, Gucci, Armani, etc.
3. Search: BRAND + CATEGORY
   Examples: "Rolex watch" → search "rolex" in mens_watch
             "Gucci bag" → search "gucci" in handbag

FLOW:
1. Greet → Browse (share URLs)
2. Search: category + brand → Show RELEVANT products
3. More images: Ask product name if unclear
4. Collect: Name, Phone, Address, Product
5. CONFIRM → Use save_order_to_sheet tool

IMAGE SEARCH:
User sends image → System identifies → Show name, price, URL
"yes" = more | "order" = buy

TOOL USE:
✅ Confirm + has name+phone+address+product
❌ wait/change/no/cancel

Unknown? → {STORE_CONTACT_NUMBER}

RULES: Never reveal AI, use category filtering, brief."""

# Tool definition for Groq API
SAVE_ORDER_TOOL = {
    "type": "function",
    "function": {
        "name": "save_order_to_sheet",
        "description": """Save customer order to Google Sheets after they confirm.
        
        WHEN TO CALL:
        ✅ Customer said "confirm", "yes", "ok", "sahi hai", "proceed" etc.
        ✅ You found name, phone, address, product in conversation history
        
        VALIDATION (Basic checks):
        - Name: Not empty, not just numbers
        - Phone: 10 digits (if looks obviously fake like "1111111111", ask to verify first)
        - Address: At least 10 characters (if too short like "abc", ask for complete address first)
        
        Extract data from conversation history and call this tool. The system will save it to Google Sheets.""",
        "parameters": {
            "type": "object",
            "properties": {
                "customer_name": {
                    "type": "string",
                    "description": "Customer's full name from conversation"
                },
                "phone_number": {
                    "type": "string",
                    "description": "Customer's 10-digit phone number from conversation"
                },
                "email": {
                    "type": "string",
                    "description": "Customer's email if provided, otherwise empty string"
                },
                "address": {
                    "type": "string",
                    "description": "Customer's complete delivery address from conversation"
                },
                "product_name": {
                    "type": "string",
                    "description": "Product name from conversation"
                },
                "product_url": {
                    "type": "string",
                    "description": "Product URL if customer shared it"
                },
                "quantity": {
                    "type": "integer",
                    "description": "Product quantity, default 1"
                },
                "notes": {
                    "type": "string",
                    "description": "Any additional notes from customer"
                }
            },
            "required": ["customer_name", "phone_number", "address", "product_name"]
        }
    }
}

# Legacy constant (use get_tool_calling_system_prompt() instead)
TOOL_CALLING_SYSTEM_PROMPT = get_tool_calling_system_prompt()
