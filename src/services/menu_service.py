#!/usr/bin/env python3
"""
Menu Service for VoicePlate - Handles menu-related queries and responses.
"""

import json
import os
from typing import List, Dict, Optional

class MenuService:
    """Service to handle menu-related queries and provide structured responses."""
    
    def __init__(self, menu_file_path: str = "data/menu.json"):
        """Initialize the menu service with menu data."""
        self.menu_file_path = menu_file_path
        self.menu_data = self._load_menu_data()
    
    def _load_menu_data(self) -> Dict:
        """Load menu data from JSON file."""
        try:
            # Get the absolute path relative to the project root
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            full_path = os.path.join(project_root, self.menu_file_path)
            
            with open(full_path, 'r', encoding='utf-8') as file:
                return json.load(file)
        except FileNotFoundError:
            print(f"Warning: Menu file not found at {full_path}")
            return {"menu": []}
        except json.JSONDecodeError:
            print(f"Warning: Invalid JSON in menu file {full_path}")
            return {"menu": []}
    
    def get_full_menu(self) -> str:
        """Get a formatted string of the complete menu."""
        if not self.menu_data.get("menu"):
            return "I'm sorry, I don't have menu information available right now."
        
        menu_text = "Here's our current menu:\n\n"
        
        for category in self.menu_data["menu"]:
            menu_text += f"**{category['category']}:**\n"
            
            for item in category["items"]:
                menu_text += f"• {item['name']} - {item['price']}"
                if item.get('description'):
                    menu_text += f": {item['description']}"
                menu_text += "\n"
            menu_text += "\n"
        
        return menu_text.strip()
    
    def get_category_items(self, category: str) -> str:
        """Get items from a specific category."""
        category_lower = category.lower()
        
        for cat in self.menu_data.get("menu", []):
            if cat["category"].lower() == category_lower:
                items_text = f"Here are our {cat['category']}:\n"
                
                for item in cat["items"]:
                    items_text += f"• {item['name']} - {item['price']}"
                    if item.get('description'):
                        items_text += f": {item['description']}"
                    items_text += "\n"
                
                return items_text.strip()
        
        return f"I don't see {category} on our menu. Would you like to hear about our available categories?"
    
    def search_menu_item(self, item_name: str) -> str:
        """Search for a specific menu item."""
        item_lower = item_name.lower()
        
        for category in self.menu_data.get("menu", []):
            for item in category["items"]:
                if item_lower in item["name"].lower():
                    response = f"{item['name']} is available for {item['price']}"
                    if item.get('description'):
                        response += f". {item['description']}"
                    response += f" You can find it in our {category['category']} section."
                    return response
        
        return f"I don't see {item_name} on our current menu. Would you like to hear about our available options?"
    
    def get_categories(self) -> str:
        """Get a list of available menu categories."""
        if not self.menu_data.get("menu"):
            return "I don't have menu information available right now."
        
        categories = [cat["category"] for cat in self.menu_data["menu"]]
        
        if len(categories) == 1:
            return f"We have {categories[0]} available."
        elif len(categories) == 2:
            return f"We have {categories[0]} and {categories[1]} available."
        else:
            return f"We have {', '.join(categories[:-1])}, and {categories[-1]} available."
    
    def get_prices_info(self) -> str:
        """Get price information for all items."""
        if not self.menu_data.get("menu"):
            return "I don't have pricing information available right now."
        
        price_text = "Here are our current prices:\n\n"
        
        for category in self.menu_data["menu"]:
            for item in category["items"]:
                price_text += f"• {item['name']}: {item['price']}\n"
        
        return price_text.strip()
    
    def is_menu_related_query(self, user_text: str) -> bool:
        """Check if the user's query is menu-related."""
        menu_keywords = [
            'menu', 'food', 'drink', 'price', 'cost', 'order', 'burger', 'cheeseburger',
            'veggie', 'tea', 'lemonade', 'available', 'options', 'what do you have',
            'what can i order', 'how much', 'categories'
        ]
        
        user_lower = user_text.lower()
        return any(keyword in user_lower for keyword in menu_keywords)
    
    def process_menu_query(self, user_text: str) -> str:
        """Process a menu-related query and return appropriate response."""
        user_lower = user_text.lower()
        
        # Full menu requests
        if any(phrase in user_lower for phrase in ['full menu', 'entire menu', 'whole menu', 'all items']):
            return self.get_full_menu()
        
        # Category requests
        if 'burger' in user_lower:
            return self.get_category_items('Burgers')
        if any(word in user_lower for word in ['drink', 'beverage', 'tea', 'lemonade']):
            return self.get_category_items('Drinks')
        
        # Specific item searches
        if 'cheeseburger' in user_lower or 'cheese burger' in user_lower:
            return self.search_menu_item('Classic Cheeseburger')
        if 'veggie' in user_lower:
            return self.search_menu_item('Veggie Burger')
        if 'iced tea' in user_lower or 'tea' in user_lower:
            return self.search_menu_item('Iced Tea')
        if 'lemonade' in user_lower:
            return self.search_menu_item('Lemonade')
        
        # Price requests
        if any(phrase in user_lower for phrase in ['price', 'cost', 'how much']):
            return self.get_prices_info()
        
        # Categories request
        if any(phrase in user_lower for phrase in ['categories', 'what do you have', 'options available']):
            return self.get_categories()
        
        # General menu request
        if 'menu' in user_lower:
            return self.get_full_menu()
        
        # Default menu response
        return "I can help you with our menu! " + self.get_categories() + " Would you like to hear about any specific category?"

# Global menu service instance
menu_service = MenuService() 