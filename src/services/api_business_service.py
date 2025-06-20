#!/usr/bin/env python3
"""
API Business Service for VoicePlate - Handles business details from external API.
"""

import logging
import aiohttp
import asyncio
from typing import Dict, Optional, Any
from datetime import datetime, timedelta
import json

class APIBusinessService:
    """Service to fetch and process business details from external API."""
    
    def __init__(self):
        """Initialize the API business service."""
        self.logger = logging.getLogger(__name__)
        self.api_url = "https://tb-services.applova.io/business/web/BIZ_a1sg647ega23/details"
        self.headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Accept-Encoding': 'gzip, deflate',
            'User-Agent': 'VoicePlate/1.0'
        }
        
        # Cache settings
        self.business_cache = None
        self.cache_expiry = None
        self.cache_duration = timedelta(minutes=30)  # Cache for 30 minutes (business info changes less frequently)
        
    async def _fetch_business_data(self) -> Optional[Dict[str, Any]]:
        """Fetch business data from the external API."""
        try:
            self.logger.info("🔄 Fetching business data from API...")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(self.api_url, headers=self.headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.logger.info("✅ Business data fetched successfully")
                        return data
                    else:
                        self.logger.error(f"❌ API request failed with status {response.status}")
                        return None
                        
        except Exception as e:
            self.logger.error(f"❌ Error fetching business data: {str(e)}")
            return None
    
    def _is_cache_valid(self) -> bool:
        """Check if the current cache is still valid."""
        if self.business_cache is None or self.cache_expiry is None:
            return False
        return datetime.now() < self.cache_expiry
    
    async def get_business_data(self, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        """
        Get business data, using cache if available and valid.
        
        Args:
            force_refresh: Force refresh from API even if cache is valid
            
        Returns:
            Business data or None if unavailable
        """
        # Use cache if valid and not forcing refresh
        if not force_refresh and self._is_cache_valid():
            self.logger.debug("📋 Using cached business data")
            return self.business_cache
        
        # Fetch fresh data from API
        api_response = await self._fetch_business_data()
        if api_response:
            self.business_cache = api_response
            self.cache_expiry = datetime.now() + self.cache_duration
            self.logger.info("💾 Business data cached successfully")
            return self.business_cache
        
        # Return cached data if API fails and we have cache
        if self.business_cache:
            self.logger.warning("⚠️ API failed, using cached business data")
            return self.business_cache
        
        return None
    
    def _get_current_day_of_week(self) -> str:
        """Get current day of week in format expected by API (e.g., 'MONDAY', 'TUESDAY', etc.)."""
        return datetime.now().strftime('%A').upper()
    
    def _format_time_range(self, hours_data: Dict[str, Any]) -> str:
        """Format time range from hours data."""
        if not hours_data:
            return "Not available"
        
        start_time = hours_data.get('from', '')
        end_time = hours_data.get('to', '')
        
        if start_time and end_time:
            # Convert from 24-hour format to more readable format
            try:
                # Parse times
                start_hour = int(start_time.split(':')[0])
                start_min = start_time.split(':')[1]
                end_hour = int(end_time.split(':')[0])
                end_min = end_time.split(':')[1]
                
                # Format to 12-hour format
                start_ampm = "AM" if start_hour < 12 else "PM"
                end_ampm = "AM" if end_hour < 12 else "PM"
                
                # Convert hours
                start_display_hour = start_hour if start_hour <= 12 else start_hour - 12
                start_display_hour = 12 if start_display_hour == 0 else start_display_hour
                
                end_display_hour = end_hour if end_hour <= 12 else end_hour - 12
                end_display_hour = 12 if end_display_hour == 0 else end_display_hour
                
                # Handle 24-hour operation (00:00 to 23:59)
                if start_time == "00:00" and end_time == "23:59":
                    return "24 hours"
                
                return f"{start_display_hour}:{start_min} {start_ampm} to {end_display_hour}:{end_min} {end_ampm}"
            except:
                # Fallback to original format if parsing fails
                return f"{start_time} to {end_time}"
        
        return "Not available"
    
    def _get_hours_for_day(self, hours_list: list, day_of_week: str) -> Optional[Dict[str, Any]]:
        """Get hours for a specific day of the week."""
        if not hours_list:
            return None
        
        for hours_entry in hours_list:
            if hours_entry.get('dayOfWeek') == day_of_week:
                return hours_entry
        return None
    
    def is_business_related_query(self, user_text: str) -> bool:
        """Check if the user's query is business/restaurant details related."""
        business_keywords = [
            'open', 'opening hours', 'hours', 'close', 'closing', 'when do you open', 'when do you close',
            'delivery', 'deliver', 'do you deliver', 'delivery hours', 'delivery time',
            'restaurant hours', 'store hours', 'business hours', 'operating hours',
            'what time', 'today', 'tomorrow', 'open today', 'closed today',
            'location', 'address', 'where are you', 'phone', 'contact', 'call',
            'restaurant info', 'business info', 'about the restaurant', 'about the store',
            'phone number', 'telephone', 'email', 'contact info', 'contact information',
            'name of restaurant', 'restaurant name', 'business name', 'what is your name',
            'tell me about', 'information about', 'about your', 'what\'s the name',
            'who are you', 'restaurant details', 'business details'
        ]
        
        user_lower = user_text.lower()
        return any(keyword in user_lower for keyword in business_keywords)
    
    async def process_business_query(self, query: str) -> str:
        """
        Process a business-related query and return formatted response.
        
        Args:
            query: User's business query
            
        Returns:
            Formatted business response
        """
        try:
            business_data = await self.get_business_data()
            if not business_data:
                return "I'm sorry, I'm having trouble accessing our business information right now. Please try again in a moment."
            
            query_lower = query.lower()
            current_day = self._get_current_day_of_week()
            
            # Handle contact information queries
            if any(term in query_lower for term in ['phone', 'contact', 'call', 'telephone', 'phone number', 'contact info', 'contact information']):
                contact_numbers = business_data.get('contactNumbers', [])
                if contact_numbers:
                    return f"You can reach us at {contact_numbers[0]}."
                else:
                    return "Please visit us at our location for contact information."
            
            # Handle email queries
            if 'email' in query_lower:
                email = business_data.get('email', '')
                if email:
                    return f"You can email us at {email}."
                else:
                    return "Please contact us by phone or visit our location."
            
            # Handle address/location queries
            if any(term in query_lower for term in ['location', 'address', 'where are you', 'where is']):
                address = business_data.get('address', '')
                if address:
                    return f"We're located at {address}."
                else:
                    return "Please contact us for our location information."
            
            # Handle business name queries
            if any(term in query_lower for term in ['name', 'restaurant name', 'business name', 'what is your name']):
                business_name = business_data.get('businessName', '')
                if business_name:
                    return f"We are {business_name}."
                else:
                    return "Thank you for calling our restaurant."
            
            # Handle delivery-related queries
            if any(term in query_lower for term in ['delivery', 'deliver', 'do you deliver']):
                delivery_supported = business_data.get('deliverySupported', False)
                
                if not delivery_supported:
                    return "We don't currently offer delivery service."
                
                delivery_hours = business_data.get('deliveryHours', [])
                if delivery_hours:
                    today_delivery = self._get_hours_for_day(delivery_hours, current_day)
                    if today_delivery:
                        time_range = self._format_time_range(today_delivery)
                        return f"Yes, we offer delivery! Our delivery hours today are {time_range}."
                    else:
                        # Check which days delivery is available
                        delivery_days = [entry.get('dayOfWeek', '') for entry in delivery_hours]
                        if delivery_days:
                            # Convert to readable format
                            readable_days = []
                            for day in delivery_days:
                                if day:
                                    readable_days.append(day.capitalize())
                            
                            if len(readable_days) == 1:
                                return f"Yes, we offer delivery on {readable_days[0]}s. We're not delivering today, but you can call us to place an order for {readable_days[0]}."
                            elif len(readable_days) == 2:
                                return f"Yes, we offer delivery on {readable_days[0]}s and {readable_days[1]}s. We're not delivering today, but please call us for more information."
                            else:
                                days_text = ', '.join(readable_days[:-1]) + f', and {readable_days[-1]}s'
                                return f"Yes, we offer delivery on {days_text}. We're not delivering today, but please call us for more information."
                        else:
                            return "Yes, we offer delivery service, but we're not delivering today. Please call us for more information."
                else:
                    return "Yes, we offer delivery service. Please contact us for delivery hours."
            
            # Handle store hours queries
            if any(term in query_lower for term in ['open', 'hours', 'close', 'operating', 'business hours', 'store hours']):
                open_hours = business_data.get('openHours', [])
                
                if open_hours:
                    today_hours = self._get_hours_for_day(open_hours, current_day)
                    if today_hours:
                        time_range = self._format_time_range(today_hours)
                        if 'today' in query_lower:
                            if time_range == "24 hours":
                                return "We're open 24 hours today."
                            else:
                                return f"We're open today from {time_range}."
                        else:
                            if time_range == "24 hours":
                                return "Our store is open 24 hours today."
                            else:
                                return f"Our store hours today are {time_range}."
                    else:
                        return "I don't have today's store hours available. Please contact us for current hours."
                else:
                    return "Please contact us for our current store hours."
            
            # Handle general business info queries
            if any(term in query_lower for term in ['about', 'info', 'restaurant', 'business']):
                response_parts = []
                
                # Add business name
                business_name = business_data.get('businessName', '')
                if business_name:
                    response_parts.append(f"We are {business_name}.")
                
                # Add delivery info if available
                if business_data.get('deliverySupported'):
                    response_parts.append("We offer delivery service.")
                
                # Add today's hours if available
                open_hours = business_data.get('openHours', [])
                if open_hours:
                    today_hours = self._get_hours_for_day(open_hours, current_day)
                    if today_hours:
                        time_range = self._format_time_range(today_hours)
                        response_parts.append(f"Today we're open {time_range}.")
                
                if response_parts:
                    return " ".join(response_parts)
                else:
                    return "Thank you for your interest in our restaurant. Please contact us for more information."
            
            # Default response for unhandled business queries
            return "I can help you with our store hours, delivery information, contact details, and general business information. What would you like to know?"
            
        except Exception as e:
            self.logger.error(f"❌ Error processing business query: {e}")
            return "I'm sorry, I'm having trouble accessing our business information right now. Please try again in a moment."

# Global API business service instance
api_business_service = APIBusinessService() 