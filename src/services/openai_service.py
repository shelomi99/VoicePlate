"""
OpenAI Service Module
Handles AI conversations, speech-to-text, and text-to-speech processing.
"""

import os
import logging
import tempfile
from typing import List, Dict, Optional, Tuple, Any
from openai import OpenAI
from config.settings import settings

class OpenAIService:
    """Service class for OpenAI API interactions."""
    
    def __init__(self):
        """Initialize OpenAI service with API key and configuration."""
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model
        self.tts_model = settings.openai_tts_model
        self.tts_voice = settings.openai_tts_voice  # Type will be validated by OpenAI API
        self.logger = logging.getLogger(__name__)
        
        # System prompt for the call answering agent
        self.system_prompt = """You are VoicePlate, a helpful and professional AI call answering assistant for Applova - a smart restaurant and retail tech company.

Key guidelines:
- Be concise and clear in your responses (aim for 2-3 sentences max)
- Maintain a friendly, professional tone
- If you don't know something, be honest about it
- For complex questions, offer to connect them with a human
- Always end responses naturally, as they will be spoken aloud
- Avoid using special characters, formatting, or lists in responses
- Keep responses conversational and easy to understand when spoken

⚠️ CRITICAL MENU RULES - FOLLOW EXACTLY:
- ONLY mention products that are EXPLICITLY listed in the provided menu context
- NEVER mention coffee, tea, burgers, sandwiches, or any items unless they appear in the exact menu list
- If asked about items not in the menu context, say "We don't currently have [item] available"
- If the menu context says "We don't have X", repeat that information accurately
- DO NOT invent, assume, or suggest any food/drink items not specifically provided
- When in doubt, be honest about what's actually available

You can help with:
- Menu information and pricing (only for items actually on the menu)
- General information and questions
- Basic customer service inquiries  
- Routing calls to appropriate departments
- Taking messages and contact information

Remember: Your responses will be converted to speech, so write them as you would speak them."""

    def _validate_response_against_menu(self, ai_response: str, menu_context: Optional[str]) -> str:
        """
        Validate AI response to ensure it only mentions products from the menu context.
        
        Args:
            ai_response: The AI's generated response
            menu_context: The menu context that was provided to the AI
            
        Returns:
            Validated response (corrected if necessary)
        """
        if not menu_context:
            return ai_response
        
        # Common problematic products that AI tends to hallucinate
        prohibited_items = [
            'coffee', 'tea', 'soda', 'burger', 'sandwich', 'salad', 'wrap', 
            'fries', 'chips', 'soup', 'pasta', 'chicken', 'beef', 'fish',
            'bread', 'toast', 'bagel', 'muffin', 'cookie', 'brownie',
            'smoothie', 'latte', 'cappuccino', 'espresso', 'juice',
            'water', 'cola', 'pepsi', 'sprite', 'beer', 'wine'
        ]
        
        ai_response_lower = ai_response.lower()
        
        # Check if AI mentioned prohibited items
        mentioned_prohibited = []
        for item in prohibited_items:
            if item in ai_response_lower and item not in menu_context.lower():
                mentioned_prohibited.append(item)
        
        # If AI mentioned prohibited items, provide a corrected response
        if mentioned_prohibited:
            self.logger.warning(f"⚠️ AI mentioned prohibited items: {mentioned_prohibited}")
            
            # Extract actual products from menu context
            actual_products = []
            if "Watermelon Granita" in menu_context:
                actual_products.append("Watermelon Granita")
            if "Vanilla Ice Cream" in menu_context:
                actual_products.append("Vanilla Ice Cream")
            if "Tiramisu" in menu_context:
                actual_products.append("Tiramisu")
            if "Chocolate Cake" in menu_context:
                actual_products.append("Chocolate Cake")
            if "Pizza" in menu_context:
                actual_products.append("Pizza")
            
            if actual_products:
                return f"Our available items include {', '.join(actual_products)}. We don't currently have {', '.join(mentioned_prohibited[:2])} available."
            else:
                return "I'm sorry, let me check our current menu availability for you."
        
        return ai_response

    def generate_response(self, user_message: str, conversation_history: Optional[List[Dict[str, str]]] = None, menu_context: Optional[str] = None) -> str:
        """
        Generate AI response using OpenAI GPT.
        
        Args:
            user_message: The user's input message
            conversation_history: Previous conversation context
            menu_context: Menu information if this is a menu-related query
            
        Returns:
            AI generated response string
        """
        try:
            # Build conversation messages
            messages: List[Dict[str, Any]] = [{"role": "system", "content": self.system_prompt}]
            
            # Add menu context if provided
            if menu_context:
                menu_system_message = f"""🚨 STRICT MENU INFORMATION - READ CAREFULLY:
{menu_context}

🚫 ABSOLUTE RESTRICTIONS:
- The above menu information is COMPLETE and EXHAUSTIVE
- Do NOT mention any items that are not listed above
- Do NOT mention: coffee, tea, burgers, sandwiches, or any common restaurant items unless explicitly listed
- If asked about items not listed above, respond with "We don't currently have [item] available"
- If the menu context above says "We don't have X", use that exact information

✅ ONLY USE:
- Products explicitly named in the menu context above
- Prices exactly as provided above
- Information about availability exactly as stated above

Keep your response conversational and easy to understand when spoken aloud."""
                messages.append({"role": "system", "content": menu_system_message})
            
            # Add conversation history if provided
            if conversation_history:
                messages.extend(conversation_history)
            
            # Add current user message
            messages.append({"role": "user", "content": user_message})
            
            self.logger.info(f"🤖 Generating AI response for: {user_message[:50]}...")
            
            # Generate response
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,  # type: ignore
                max_tokens=150,  # Keep responses concise for voice
                temperature=0.3,  # Lower temperature for more accurate responses
                top_p=0.9
            )
            
            ai_response = response.choices[0].message.content
            if ai_response:
                ai_response = ai_response.strip()
                self.logger.info(f"✅ AI response generated: {ai_response[:50]}...")
                return self._validate_response_against_menu(ai_response, menu_context)
            else:
                return "I apologize, but I'm having trouble processing your request right now. Please try again or hold for a human representative."
            
        except Exception as e:
            self.logger.error(f"❌ Error generating AI response: {str(e)}")
            return "I apologize, but I'm having trouble processing your request right now. Please try again or hold for a human representative."

    def speech_to_text(self, audio_file_path: str) -> Optional[str]:
        """
        Convert speech audio file to text using OpenAI Whisper.
        
        Args:
            audio_file_path: Path to the audio file
            
        Returns:
            Transcribed text or None if failed
        """
        try:
            self.logger.info(f"🎙️ Converting speech to text: {audio_file_path}")
            
            with open(audio_file_path, "rb") as audio_file:
                transcript = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="text"
                )
            
            # transcript is already a string when response_format="text"
            transcribed_text = str(transcript).strip()
            self.logger.info(f"✅ Speech converted to text: {transcribed_text[:100]}...")
            
            return transcribed_text
            
        except Exception as e:
            self.logger.error(f"❌ Error converting speech to text: {str(e)}")
            return None

    def text_to_speech(self, text: str, output_path: Optional[str] = None) -> Optional[str]:
        """
        Convert text to speech using OpenAI TTS.
        
        Args:
            text: Text to convert to speech
            output_path: Optional path to save audio file
            
        Returns:
            Path to generated audio file or None if failed
        """
        try:
            self.logger.info(f"🔊 Converting text to speech: {text[:50]}...")
            
            # Create output path if not provided
            if not output_path:
                temp_dir = tempfile.gettempdir()
                output_path = os.path.join(temp_dir, f"tts_{os.getpid()}_{hash(text)}.mp3")
            
            # Generate speech
            response = self.client.audio.speech.create(
                model=self.tts_model,
                voice=self.tts_voice,  # type: ignore
                input=text,
                response_format="mp3"
            )
            
            # Save to file
            with open(output_path, "wb") as f:
                f.write(response.content)
            
            self.logger.info(f"✅ Text converted to speech: {output_path}")
            return output_path
            
        except Exception as e:
            self.logger.error(f"❌ Error converting text to speech: {str(e)}")
            return None

    async def process_conversation_turn(self, user_input: str, conversation_history: Optional[List[Dict[str, str]]] = None) -> Tuple[str, List[Dict[str, str]]]:
        """
        Process a complete conversation turn: generate AI response and update history.
        
        Args:
            user_input: User's input text
            conversation_history: Previous conversation context
            
        Returns:
            Tuple of (ai_response, updated_conversation_history)
        """
        try:
            # Check if this is a promo-related query first (highest priority)
            promo_context = None
            try:
                from src.services.api_promo_service import api_promo_service
                if api_promo_service.is_promo_related_query(user_input):
                    promo_context = await api_promo_service.process_promo_query(user_input)
                    self.logger.info(f"🎁 Promo context provided for query: {user_input[:30]}...")
                    # Return promo response directly as it's already processed
                    ai_response = promo_context
                    
                    # Update conversation history
                    if conversation_history is None:
                        conversation_history = []
                    
                    updated_history = conversation_history.copy()
                    updated_history.append({"role": "user", "content": user_input})
                    updated_history.append({"role": "assistant", "content": ai_response})
                    
                    # Keep history manageable (last 10 messages)
                    if len(updated_history) > 10:
                        updated_history = updated_history[-10:]
                    
                    return ai_response, updated_history
                    
            except Exception as e:
                self.logger.warning(f"⚠️ Could not load API promo service: {e}")
            
            # Check if this is a business-related query (second priority)
            business_context = None
            try:
                from src.services.api_business_service import api_business_service
                if api_business_service.is_business_related_query(user_input):
                    business_context = await api_business_service.process_business_query(user_input)
                    self.logger.info(f"🏪 Business context provided for query: {user_input[:30]}...")
                    # Return business response directly as it's already processed
                    ai_response = business_context
                    
                    # Update conversation history
                    if conversation_history is None:
                        conversation_history = []
                    
                    updated_history = conversation_history.copy()
                    updated_history.append({"role": "user", "content": user_input})
                    updated_history.append({"role": "assistant", "content": ai_response})
                    
                    # Keep history manageable (last 10 messages)
                    if len(updated_history) > 10:
                        updated_history = updated_history[-10:]
                    
                    return ai_response, updated_history
                    
            except Exception as e:
                self.logger.warning(f"⚠️ Could not load API business service: {e}")
            
            # Check if this is a menu-related query (third priority, if not promo or business-related)
            menu_context = None
            try:
                from src.services.api_menu_service import api_menu_service
                if api_menu_service.is_menu_related_query(user_input):
                    menu_context = await api_menu_service.process_menu_query(user_input)
                    self.logger.info(f"🍽️ Menu context provided for query: {user_input[:30]}...")
            except Exception as e:
                self.logger.warning(f"⚠️ Could not load API menu service: {e}")
                # Fallback to static menu service
                try:
                    from src.services.menu_service import menu_service
                    if menu_service.is_menu_related_query(user_input):
                        menu_context = menu_service.process_menu_query(user_input)
                        self.logger.info(f"🍽️ Fallback menu context provided for query: {user_input[:30]}...")
                except Exception as fallback_e:
                    self.logger.warning(f"⚠️ Could not load fallback menu service: {fallback_e}")
            
            # Generate AI response with menu context if applicable
            ai_response = self.generate_response(user_input, conversation_history, menu_context)
            
            # Update conversation history
            if conversation_history is None:
                conversation_history = []
            
            # Add user message and AI response to history
            updated_history = conversation_history.copy()
            updated_history.append({"role": "user", "content": user_input})
            updated_history.append({"role": "assistant", "content": ai_response})
            
            # Keep history manageable (last 10 messages)
            if len(updated_history) > 10:
                updated_history = updated_history[-10:]
            
            return ai_response, updated_history
            
        except Exception as e:
            self.logger.error(f"❌ Error processing conversation turn: {str(e)}")
            fallback_response = "I'm sorry, I encountered an issue. Could you please repeat your question?"
            return fallback_response, conversation_history or []

# Global OpenAI service instance
openai_service = OpenAIService() 