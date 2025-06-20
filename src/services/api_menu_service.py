#!/usr/bin/env python3
"""
API Menu Service for VoicePlate - Handles dynamic menu data from external API.
"""

import logging
import aiohttp
import asyncio
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
import json

class APIMenuService:
    """Service to fetch and process menu data from external API."""
    
    def __init__(self):
        """Initialize the API menu service."""
        self.logger = logging.getLogger(__name__)
        self.api_url = "https://tb-services.applova.io/business/web/BIZ_a1sg647ega23/categories/full"
        self.headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Accept-Encoding': 'gzip, deflate',
            'User-Agent': 'VoicePlate/1.0'
        }
        
        # Cache settings
        self.menu_cache = None
        self.cache_expiry = None
        self.cache_duration = timedelta(minutes=15)  # Cache for 15 minutes
        
    async def _fetch_menu_data(self) -> Optional[Dict[str, Any]]:
        """Fetch menu data from the external API."""
        try:
            self.logger.info("🔄 Fetching menu data from API...")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(self.api_url, headers=self.headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.logger.info("✅ Menu data fetched successfully")
                        return data
                    else:
                        self.logger.error(f"❌ API request failed with status {response.status}")
                        return None
                        
        except Exception as e:
            self.logger.error(f"❌ Error fetching menu data: {str(e)}")
            return None
    
    def _is_cache_valid(self) -> bool:
        """Check if the current cache is still valid."""
        if self.menu_cache is None or self.cache_expiry is None:
            return False
        return datetime.now() < self.cache_expiry
    
    def _process_product(self, product_full_details: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Process a single product according to the specified conditions.
        
        Args:
            product_full_details: Product data from API (contains productSummary and product)
            
        Returns:
            Processed product dict or None if product should be excluded
        """
        product_summary = product_full_details.get('productSummary', {})
        product = product_full_details.get('product', {})
        
        # Check if product meets our criteria
        if not (product_summary.get('activeForOrderAheadWebstore', False)):
            return None
        
        # Get the product ID from either summary or product
        product_id = product.get('productId') or product_summary.get('productId')
        
        # Extract pricing information
        price_info = product_summary.get('price', {})
        price = price_info.get('lowest', 0) if price_info else 0
        
        # Extract product information
        processed_product = {
            'id': product_id,
            'name': product.get('name') or product_summary.get('name', 'Unknown Item'),
            'description': product.get('description') or product_summary.get('description', ''),
            'price': price,
            'alcoholic': product.get('alcoholicProduct', False),
            'category_ids': product.get('categories', []),
            'dietary_info': {
                'vegetarian': product.get('vegetarian', False),
                'vegan': product.get('vegan', False),
                'gluten_free': product.get('glutenFree', False),
                'dairy_free': product.get('dairyFree', False)
            },
            # Include any other relevant fields
            'available': True,
            'image_url': product_summary.get('image', '') or (product.get('images', [{}])[0] if product.get('images') else ''),
            'thumb_image_url': product_summary.get('thumbImage', '') or (product.get('thumbImages', [{}])[0] if product.get('thumbImages') else ''),
            'rating': product_summary.get('rating', 0),
            'tags': product.get('tags', []),
            'deliverable': product.get('deliverable', False),
            'variants': product.get('variants', {}),
            'add_ons': product.get('addOns', [])
        }
        
        return processed_product
    
    def _process_menu_response(self, api_response: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process the API response and structure it for our use.
        
        Args:
            api_response: Raw API response
            
        Returns:
            Processed menu structure
        """
        processed_menu = {
            'categories': {},
            'products': {},
            'last_updated': datetime.now().isoformat()
        }
        
        # Process categories and their products
        categories_data = api_response.get('categories', [])
        for category_data in categories_data:
            category = category_data.get('category', {})
            category_id = category.get('categoryId')
            
            if category_id and category.get('active', False):
                processed_menu['categories'][category_id] = {
                    'id': category_id,
                    'name': category.get('name', 'Unknown Category'),
                    'description': category.get('description', ''),
                    'active': category.get('active', False),
                    'priority': category.get('priority', 0),
                    'image': category.get('image', ''),
                    'items_count': category.get('itemsCount', 0),
                    'active_for_webstore': category.get('activeForOrderAheadWebstore', False)
                }
                
                # Process products in this category
                products_full_details = category_data.get('productsFullDetails', [])
                for product_data in products_full_details:
                    processed_product = self._process_product(product_data)
                    
                    if processed_product:
                        product_id = processed_product['id']
                        # If product already exists, merge category information
                        if product_id in processed_menu['products']:
                            # Add this category to existing product if not already there
                            existing_categories = processed_menu['products'][product_id]['category_ids']
                            if category_id not in existing_categories:
                                existing_categories.append(category_id)
                        else:
                            processed_menu['products'][product_id] = processed_product
        
        return processed_menu
    
    async def get_menu_data(self, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        """
        Get menu data, using cache if available and valid.
        
        Args:
            force_refresh: Force refresh from API even if cache is valid
            
        Returns:
            Processed menu data or None if unavailable
        """
        # Use cache if valid and not forcing refresh
        if not force_refresh and self._is_cache_valid():
            self.logger.debug("📋 Using cached menu data")
            return self.menu_cache
        
        # Fetch fresh data from API
        api_response = await self._fetch_menu_data()
        if api_response:
            # Process the response
            self.menu_cache = self._process_menu_response(api_response)
            self.cache_expiry = datetime.now() + self.cache_duration
            self.logger.info(f"💾 Menu data cached with {len(self.menu_cache.get('products', {}))} products")
            return self.menu_cache
        
        # Return cached data if API fails and we have cache
        if self.menu_cache:
            self.logger.warning("⚠️ API failed, using cached menu data")
            return self.menu_cache
        
        return None
    
    def _format_price(self, price: float) -> str:
        """Format price for display."""
        if price == 0:
            return "Price not available"
        return f"${price:.2f}"
    
    async def get_full_menu_text(self) -> str:
        """Get a formatted string of the complete menu."""
        menu_data = await self.get_menu_data()
        
        if not menu_data or not menu_data.get('products'):
            return "I'm sorry, I don't have menu information available right now."
        
        # Group products by category
        category_products = {}
        categories = menu_data.get('categories', {})
        products = menu_data.get('products', {})
        
        for product in products.values():
            for cat_id in product.get('category_ids', []):
                if cat_id in categories:
                    cat_name = categories[cat_id]['name']
                    if cat_name not in category_products:
                        category_products[cat_name] = []
                    category_products[cat_name].append(product)
        
        # Build menu text
        menu_text = "Here's our current menu:\n\n"
        
        for category_name, items in category_products.items():
            menu_text += f"**{category_name}:**\n"
            
            for item in items:
                menu_text += f"• {item['name']} - {self._format_price(item['price'])}"
                if item.get('description'):
                    menu_text += f": {item['description']}"
                
                # Add dietary information
                dietary_info = []
                if item['dietary_info']['vegetarian']:
                    dietary_info.append("Vegetarian")
                if item['dietary_info']['vegan']:
                    dietary_info.append("Vegan")
                if item['dietary_info']['gluten_free']:
                    dietary_info.append("Gluten-Free")
                if item['alcoholic']:
                    dietary_info.append("Contains Alcohol")
                
                if dietary_info:
                    menu_text += f" ({', '.join(dietary_info)})"
                
                menu_text += "\n"
            menu_text += "\n"
        
        return menu_text.strip()
    
    async def search_menu_items(self, search_term: str) -> str:
        """Search for menu items by name or description."""
        menu_data = await self.get_menu_data()
        
        if not menu_data or not menu_data.get('products'):
            return "I'm sorry, I don't have menu information available right now."
        
        search_lower = search_term.lower()
        found_items = []
        
        products = list(menu_data.get('products', {}).values())
        categories = menu_data.get('categories', {})
        
        for product in products:
            if (search_lower in product['name'].lower() or 
                search_lower in product.get('description', '').lower()):
                
                # Get category names
                category_names = []
                for cat_id in product.get('category_ids', []):
                    if cat_id in categories:
                        category_names.append(categories[cat_id]['name'])
                
                found_items.append({
                    'product': product,
                    'categories': category_names
                })
        
        if not found_items:
            return f"I don't see any items matching '{search_term}' on our current menu. Would you like to hear about our available options?"
        
        if len(found_items) == 1:
            item = found_items[0]
            product = item['product']
            response = f"{product['name']} is available for {self._format_price(product['price'])}"
            if product.get('description'):
                response += f". {product['description']}"
            if item['categories']:
                response += f" You can find it in our {', '.join(item['categories'])} section."
            return response
        else:
            response = f"I found {len(found_items)} items matching '{search_term}':\n"
            for item in found_items[:5]:  # Limit to first 5 results
                product = item['product']
                response += f"• {product['name']} - {self._format_price(product['price'])}\n"
            if len(found_items) > 5:
                response += f"... and {len(found_items) - 5} more items."
            return response
    
    async def get_categories(self) -> str:
        """Get a list of available menu categories."""
        menu_data = await self.get_menu_data()
        
        if not menu_data or not menu_data.get('categories'):
            return "I don't have menu information available right now."
        
        categories = [cat['name'] for cat in menu_data['categories'].values() if cat['active']]
        
        if len(categories) == 0:
            return "No categories are currently available."
        elif len(categories) == 1:
            return f"We have {categories[0]} available."
        elif len(categories) == 2:
            return f"We have {categories[0]} and {categories[1]} available."
        else:
            return f"We have {', '.join(categories[:-1])}, and {categories[-1]} available."
    
    def is_menu_related_query(self, user_text: str) -> bool:
        """Check if the user's query is menu-related."""
        menu_keywords = [
            'menu', 'food', 'drink', 'beverage', 'beverages', 'price', 'cost', 'order', 'available', 'options', 
            'what do you have', 'what can i order', 'how much', 'categories',
            'vegetarian', 'vegan', 'gluten free', 'dairy free', 'alcoholic', 'alcohol',
            'special', 'promotion', 'deal', 'offer', 'items', 'today',
            'coffee', 'tea', 'soda', 'juice', 'water', 'soft drink',
            'dessert', 'sweet', 'cake', 'ice cream', 'snack',
            'lunch', 'dinner', 'breakfast', 'meal', 'eat', 'hungry',
            'sandwich', 'burger', 'pizza', 'salad', 'soup', 'pasta',
            'spicy', 'mild', 'hot', 'cold', 'fresh', 'healthy',
            'serve', 'selling', 'cooking', 'chef', 'kitchen'
        ]
        
        user_lower = user_text.lower()
        return any(keyword in user_lower for keyword in menu_keywords)
    
    def _validate_query_against_menu(self, query: str, menu_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate if a query has matching products in the menu and provide context about availability.
        
        Args:
            query: User's menu-related query
            menu_data: Processed menu data
            
        Returns:
            Dict with validation results and suggestions
        """
        query_lower = query.lower()
        
        # Common search terms
        search_terms = {
            'hot': ['hot', 'warm', 'heated'],
            'cold': ['cold', 'chilled', 'frozen', 'ice'],
            'beverage': ['beverage', 'drink', 'coffee', 'tea', 'soda', 'juice'],
            'alcoholic': ['alcohol', 'alcoholic', 'beer', 'wine', 'cocktail'],
            'dessert': ['dessert', 'sweet', 'cake', 'ice cream', 'cookie'],
            'vegan': ['vegan', 'plant-based'],
            'vegetarian': ['vegetarian', 'veggie'],
            'spicy': ['spicy', 'hot sauce', 'chili'],
            'healthy': ['healthy', 'salad', 'fresh'],
        }
        
        # Check what categories the query might be asking about
        mentioned_categories = []
        for category, terms in search_terms.items():
            if any(term in query_lower for term in terms):
                mentioned_categories.append(category)
        
        # Get actual products
        products = list(menu_data.get('products', {}).values())
        
        # Check if we have products matching the query categories
        matching_products = []
        available_categories = []
        
        for product in products:
            product_name = product.get('name', '').lower()
            product_description = product.get('description', '').lower()
            
            # Check for cold items
            if 'cold' in mentioned_categories:
                if any(term in product_name or term in product_description 
                      for term in ['ice', 'frozen', 'cold', 'granita']):
                    matching_products.append(product)
                    if 'cold' not in available_categories:
                        available_categories.append('cold')
            
            # Check for desserts
            if 'dessert' in mentioned_categories:
                if any(term in product_name or term in product_description 
                      for term in ['ice cream', 'cake', 'tiramisu', 'granita', 'dessert']):
                    matching_products.append(product)
                    if 'dessert' not in available_categories:
                        available_categories.append('dessert')
            
            # Check for alcoholic items
            if 'alcoholic' in mentioned_categories:
                if product.get('alcoholic', False):
                    matching_products.append(product)
                    if 'alcoholic' not in available_categories:
                        available_categories.append('alcoholic')
        
        return {
            'mentioned_categories': mentioned_categories,
            'available_categories': available_categories,
            'matching_products': matching_products,
            'has_matches': len(matching_products) > 0
        }

    async def process_menu_query(self, query: str) -> str:
        """
        Process a menu-related query and return formatted menu information.
        
        Args:
            query: User's menu query
            
        Returns:
            Formatted menu response
        """
        try:
            menu_data = await self.get_menu_data()
            if not menu_data:
                return "I'm sorry, I'm having trouble accessing our menu information right now. Please try again in a moment."
            
            # Validate query against actual menu
            validation = self._validate_query_against_menu(query, menu_data)
            
            categories = menu_data.get('categories', {})
            products = list(menu_data.get('products', {}).values())
            query_lower = query.lower()  # Define query_lower here
            
            if not products:
                return "I'm sorry, our menu information is currently unavailable. Please try again later."
            
            # Check if query asks about specific unavailable categories
            mentioned_categories = validation.get('mentioned_categories', [])
            available_categories = validation.get('available_categories', [])
            
            # Build response based on what's actually available
            response_parts = []
            
            # If asking about beverages/drinks specifically
            if 'beverage' in mentioned_categories or any(term in query_lower for term in ['beverage', 'drink', 'drinks']):
                # Look for beverage-like items
                beverage_like_items = []
                for product in products:
                    product_name = product.get('name', '').lower()
                    # Consider granita and other cold items as beverage-like
                    if any(term in product_name for term in ['granita', 'drink', 'juice', 'water', 'soda', 'tea', 'coffee']):
                        beverage_like_items.append(product)
                
                if beverage_like_items:
                    response_parts.append("For beverages, we have:")
                    for product in beverage_like_items[:3]:
                        price = product.get('price', 0)
                        response_parts.append(f"{product['name']} for ${price:.2f}")
                    return " ".join(response_parts)
                else:
                    response_parts.append("We don't currently have traditional beverages like coffee or tea.")
                    response_parts.append(f"However, we do have refreshing options like {products[0]['name']} for ${products[0]['price']:.2f}.")
                    return " ".join(response_parts)
            
            # If asking about hot beverages specifically
            if 'beverage' in mentioned_categories and 'hot' in mentioned_categories:
                if not any('hot' in cat or 'beverage' in cat for cat in available_categories):
                    response_parts.append("We don't currently have hot beverages available.")
                    response_parts.append(f"However, we do have these items: {', '.join([p['name'] for p in products[:3]])}.")
                    return " ".join(response_parts)
            
            # If asking about alcoholic items
            if 'alcoholic' in mentioned_categories:
                alcoholic_products = [p for p in products if p.get('alcoholic', False)]
                if not alcoholic_products:
                    response_parts.append("We don't currently offer any alcoholic beverages.")
                    response_parts.append(f"Our available items include: {', '.join([p['name'] for p in products[:3]])}.")
                    return " ".join(response_parts)
            
            # If query has matches, show them
            if validation.get('has_matches'):
                matching_products = validation.get('matching_products', [])
                if matching_products:
                    response_parts.append("Here are the items that match your request:")
                    for product in matching_products[:3]:  # Limit to 3 items for voice
                        price = product.get('price', 0)
                        response_parts.append(f"{product['name']} for ${price:.2f}")
                    return " ".join(response_parts)
            
            # General menu response - show categories first, then some products
            if categories:
                response_parts.append(f"We have {len(categories)} categories: {', '.join(categories.keys())}.")
            
            if products:
                response_parts.append("Some of our popular items include:")
                for product in products[:4]:  # Show first 4 products
                    price = product.get('price', 0)
                    response_parts.append(f"{product['name']} for ${price:.2f}")
            
            return " ".join(response_parts)
            
        except Exception as e:
            self.logger.error(f"❌ Error processing menu query: {e}")
            return "I'm sorry, I'm having trouble accessing our menu information right now. Please try again in a moment."

# Global API menu service instance
api_menu_service = APIMenuService() 