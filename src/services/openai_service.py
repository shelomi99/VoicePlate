"""
OpenAI Service Module
Handles AI conversations, speech-to-text, and text-to-speech processing.
"""

import os
import logging
import tempfile
from typing import List, Dict, Optional, Tuple
from openai import OpenAI
from config.settings import settings

class OpenAIService:
    """Service class for OpenAI API interactions."""
    
    def __init__(self):
        """Initialize OpenAI service with API key and configuration."""
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model
        self.tts_model = settings.openai_tts_model
        self.tts_voice = settings.openai_tts_voice
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

You can help with:
- Menu information and pricing
- General information and questions
- Basic customer service inquiries  
- Routing calls to appropriate departments
- Taking messages and contact information

For menu-related questions, you have access to current menu information that will be provided when needed.

Remember: Your responses will be converted to speech, so write them as you would speak them."""

    def generate_response(self, user_message: str, conversation_history: List[Dict] = None, menu_context: str = None) -> str:
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
            messages = [{"role": "system", "content": self.system_prompt}]
            
            # Add menu context if provided
            if menu_context:
                menu_system_message = f"Current menu information: {menu_context}\n\nUse this information to answer the user's menu-related question. Keep your response conversational and easy to understand when spoken aloud."
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
                messages=messages,
                max_tokens=150,  # Keep responses concise for voice
                temperature=0.7,
                top_p=0.9
            )
            
            ai_response = response.choices[0].message.content.strip()
            self.logger.info(f"✅ AI response generated: {ai_response[:50]}...")
            
            return ai_response
            
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
            
            transcribed_text = transcript.strip()
            self.logger.info(f"✅ Speech converted to text: {transcribed_text[:100]}...")
            
            return transcribed_text
            
        except Exception as e:
            self.logger.error(f"❌ Error converting speech to text: {str(e)}")
            return None

    def text_to_speech(self, text: str, output_path: str = None) -> Optional[str]:
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
                voice=self.tts_voice,
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

    def process_conversation_turn(self, user_input: str, conversation_history: List[Dict] = None) -> Tuple[str, List[Dict]]:
        """
        Process a complete conversation turn: generate AI response and update history.
        
        Args:
            user_input: User's input text
            conversation_history: Previous conversation context
            
        Returns:
            Tuple of (ai_response, updated_conversation_history)
        """
        try:
            # Check if this is a menu-related query
            menu_context = None
            try:
                from src.services.menu_service import menu_service
                if menu_service.is_menu_related_query(user_input):
                    menu_context = menu_service.process_menu_query(user_input)
                    self.logger.info(f"🍽️ Menu context provided for query: {user_input[:30]}...")
            except Exception as e:
                self.logger.warning(f"⚠️ Could not load menu service: {e}")
            
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