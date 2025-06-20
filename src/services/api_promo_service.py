#!/usr/bin/env python3
"""
API Promo Service for VoicePlate - Handles promo codes from external API.
"""

import logging
import aiohttp
import asyncio
from typing import Dict, Optional, Any, List
from datetime import datetime, timedelta, timezone
import json

class APIPromoService:
    """Service to fetch and process promo codes from external API."""
    
    def __init__(self):
        """Initialize the API promo service."""
        self.logger = logging.getLogger(__name__)
        self.api_url = "https://tb-services.applova.io/mgmt/merchants/businesses/BIZ_a1sg647ega23/promo/"
        self.headers = {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer eyJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJodHRwczpcL1wvc2VydmljZXMuYXBwdGl6ZXIuaW8iLCJzdWIiOiJCSVpfYTFzZzY0N2VnYTIzfHNoZWxvbWkiLCJ0eXBlIjoibWVyY2hhbnQiLCJleHAiOjE3ODE5NDYyNzZ9.sNufNK3x-Bxlt_BxhrCxH3x7jHxAO0BK8OQublzpdco'
        }
        
        # Cache settings
        self.promo_cache = None
        self.cache_expiry = None
        self.cache_duration = timedelta(minutes=15)  # Cache for 15 minutes (promos might change more frequently)
        
    async def _fetch_promo_data(self) -> Optional[Dict[str, Any]]:
        """Fetch promo data from the external API."""
        try:
            self.logger.info("🔄 Fetching promo codes from API...")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(self.api_url, headers=self.headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.logger.info("✅ Promo codes fetched successfully")
                        return data
                    else:
                        self.logger.error(f"❌ Promo API request failed with status {response.status}")
                        return None
                        
        except Exception as e:
            self.logger.error(f"❌ Error fetching promo codes: {str(e)}")
            return None
    
    def _is_cache_valid(self) -> bool:
        """Check if the current cache is still valid."""
        if self.promo_cache is None or self.cache_expiry is None:
            return False
        return datetime.now() < self.cache_expiry
    
    async def get_promo_data(self, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        """
        Get promo data, using cache if available and valid.
        
        Args:
            force_refresh: Force refresh from API even if cache is valid
            
        Returns:
            Promo data or None if unavailable
        """
        # Use cache if valid and not forcing refresh
        if not force_refresh and self._is_cache_valid():
            self.logger.debug("📋 Using cached promo data")
            return self.promo_cache
        
        # Fetch fresh data from API
        api_response = await self._fetch_promo_data()
        if api_response:
            self.promo_cache = api_response
            self.cache_expiry = datetime.now() + self.cache_duration
            self.logger.info("💾 Promo data cached successfully")
            return self.promo_cache
        
        # Return cached data if API fails and we have cache
        if self.promo_cache:
            self.logger.warning("⚠️ Promo API failed, using cached data")
            return self.promo_cache
        
        return None
    
    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse date string in ISO format."""
        try:
            if date_str:
                # Handle both with and without timezone info
                if date_str.endswith('Z'):
                    return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                elif '+' in date_str or date_str.endswith(('00:00', '23:59')):
                    return datetime.fromisoformat(date_str)
                else:
                    # Assume it's a date without time
                    return datetime.fromisoformat(date_str + 'T00:00:00')
        except Exception as e:
            self.logger.warning(f"⚠️ Could not parse date '{date_str}': {e}")
        return None
    
    def _is_promo_active(self, promo: Dict[str, Any]) -> bool:
        """Check if a promo is currently active based on start and expiry dates."""
        now = datetime.now(timezone.utc)  # Make timezone-aware
        
        # Get promo period information
        promo_period = promo.get('promoPeriod', {})
        expiry_rule = promo_period.get('expiryPromoRule', {})
        
        start_date_str = expiry_rule.get('startDate', '')
        expiry_date_str = expiry_rule.get('expiryDate', '')
        
        start_date = self._parse_date(start_date_str)
        expiry_date = self._parse_date(expiry_date_str)
        
        # If we can't parse dates, assume it's active
        if not start_date and not expiry_date:
            return True
        
        # Convert parsed dates to UTC if they're not already timezone-aware
        if start_date and start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=timezone.utc)
        if expiry_date and expiry_date.tzinfo is None:
            expiry_date = expiry_date.replace(tzinfo=timezone.utc)
        
        # Check if current time is within the promo period
        if start_date and now < start_date:
            return False  # Promo hasn't started yet
        
        if expiry_date and now > expiry_date:
            return False  # Promo has expired
        
        return True
    
    def _format_promo_info(self, promo: Dict[str, Any]) -> str:
        """Format promo information for conversational response."""
        try:
            promo_title = promo.get('title', 'Special offer')
            promo_code = promo.get('promoCode', '')
            description = promo.get('description', '')
            
            # Extract discount information from promoCriteria
            criteria = promo.get('promoCriteria', {})
            total_amount = criteria.get('totalAmount', {})
            promo_base = total_amount.get('promoCodeBase', '')
            percentage = total_amount.get('percentage', 0)
            amount = total_amount.get('amount')
            
            # Build the response
            response_parts = []
            
            # Add promo title and code
            if promo_code:
                response_parts.append(f"We have '{promo_title}' with code {promo_code}")
            else:
                response_parts.append(f"We have '{promo_title}'")
            
            # Add discount information
            if promo_base == 'PERCENTAGE_BASED' and percentage:
                response_parts.append(f"offering {percentage}% off")
            elif promo_base == 'FIXED_AMOUNT' and amount:
                response_parts.append(f"offering ${amount} off")
            elif percentage:
                response_parts.append(f"offering {percentage}% off")
            elif amount:
                response_parts.append(f"offering ${amount} off")
            
            # Add description if available and not too long and different from title
            if description and len(description) < 100 and description.lower() != promo_title.lower():
                response_parts.append(f"- {description}")
            
            return ". ".join(response_parts) + "."
            
        except Exception as e:
            self.logger.warning(f"⚠️ Error formatting promo info: {e}")
            return "We have a special promotion available."
    
    def is_promo_related_query(self, user_text: str) -> bool:
        """Check if the user's query is promo/promotion related."""
        promo_keywords = [
            'promo', 'promo code', 'promo codes', 'promotion', 'promotions',
            'discount', 'discounts', 'deal', 'deals', 'offer', 'offers',
            'special offer', 'special offers', 'coupon', 'coupons',
            'sale', 'sales', 'voucher', 'vouchers', 'code', 'codes',
            'percentage off', 'percent off', 'money off', 'dollars off',
            'any deals', 'any offers', 'any promotions', 'any discounts',
            'what deals', 'what offers', 'what promotions', 'what discounts',
            'current deals', 'current offers', 'current promotions',
            'available deals', 'available offers', 'available promotions',
            'special pricing', 'reduced price', 'reduced prices'
        ]
        
        user_lower = user_text.lower()
        return any(keyword in user_lower for keyword in promo_keywords)
    
    async def process_promo_query(self, query: str) -> str:
        """
        Process a promo-related query and return formatted response.
        
        Args:
            query: User's promo query
            
        Returns:
            Formatted promo response
        """
        try:
            promo_data = await self.get_promo_data()
            if not promo_data:
                return "I'm sorry, I'm having trouble accessing our current promotions right now. Please try again in a moment or check our website."
            
            # Extract promo list from response - updated to use 'promoPlans'
            promos = promo_data.get('promoPlans', []) if isinstance(promo_data.get('promoPlans'), list) else []
            
            if not promos:
                return "We don't have any active promotions at the moment. Please check back later or visit our website for updates."
            
            # Filter active promos
            active_promos = [promo for promo in promos if self._is_promo_active(promo)]
            
            if not active_promos:
                return "We don't have any active promotions at the moment. Please check back later or visit our website for updates."
            
            # Format response based on number of active promos
            if len(active_promos) == 1:
                return self._format_promo_info(active_promos[0])
            elif len(active_promos) <= 3:
                # List multiple promos
                promo_descriptions = []
                for promo in active_promos[:3]:  # Limit to 3 for voice response
                    promo_descriptions.append(self._format_promo_info(promo))
                
                return "We have several promotions available: " + " Also, ".join(promo_descriptions)
            else:
                # Too many promos, give a general response
                return f"We currently have {len(active_promos)} active promotions! Please visit our website or ask about specific offers for details."
            
        except Exception as e:
            self.logger.error(f"❌ Error processing promo query: {e}")
            return "I'm sorry, I'm having trouble accessing our current promotions right now. Please try again in a moment."

# Global API promo service instance
api_promo_service = APIPromoService() 