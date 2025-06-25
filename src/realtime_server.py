#!/usr/bin/env python3
"""
VoicePlate Realtime-Only Server
A unified FastAPI server that handles both Twilio webhooks and WebSocket connections
for OpenAI Realtime API integration.
"""

import os
import sys
import logging
import asyncio
import json
import base64
import time
from typing import Dict, Any, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException, Form
from fastapi.responses import Response, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from twilio.twiml.voice_response import VoiceResponse, Connect, Stream
from twilio.request_validator import RequestValidator
import uvicorn

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import settings
from src.services.realtime_service import RealtimeService
from src.services.openai_service import openai_service

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

class RealtimeServer:
    """Unified server for VoicePlate Realtime API integration."""
    
    def __init__(self):
        """Initialize the realtime server."""
        self.logger = logging.getLogger(__name__)
        self.realtime_service = RealtimeService()
        
        # Session management
        self.active_sessions: Dict[str, Dict[str, Any]] = {}
        self.call_sessions: Dict[str, Dict[str, Any]] = {}
        
        # Disable Twilio request validator in development
        self.validator = None  # Disabled for development
        
        self.logger.info("🚀 VoicePlate Realtime Server initialized")

    def validate_twilio_request(self, request: Request) -> bool:
        """Validate that the request is actually from Twilio."""
        # Always return True in development mode
        self.logger.debug("🔓 Twilio signature validation disabled (development mode)")
        return True

    async def handle_voice_webhook(self, request: Request, call_data: Dict[str, str]) -> Response:
        """Handle incoming Twilio voice webhook for realtime processing."""
        
        # Log incoming request for monitoring
        self.logger.info(f"📞 WEBHOOK: {call_data.get('CallSid')} from {call_data.get('From')} to {call_data.get('To')}")
        
        # Validate request is from Twilio
        if not self.validate_twilio_request(request):
            self.logger.warning("Invalid Twilio request received")
            # In development, continue anyway
            pass
        
        # Extract call information
        call_sid = call_data.get('CallSid', '')
        from_number = call_data.get('From', '')
        to_number = call_data.get('To', '')
        call_status = call_data.get('CallStatus', '')
        
        # Validate required fields
        if not call_sid or not from_number or not to_number:
            self.logger.error(f"❌ Missing required call data: {call_data}")
            response = VoiceResponse()
            response.say("Sorry, there was an error processing your call.", voice=getattr(settings, 'voice_type', 'alice'))
            response.hangup()
            return Response(content=str(response), media_type='text/xml')
        
        self.logger.info(f"📞 Incoming realtime call: {call_sid} from {from_number} to {to_number} (Status: {call_status})")
        
        try:
            # Check if realtime API should be used based on configuration
            use_realtime_api = getattr(settings, 'use_realtime_api', False)
            
            if use_realtime_api:
                self.logger.info(f"🚀 Using OpenAI Realtime API for enhanced voice processing")
                return await self._handle_realtime_voice_response(call_sid, from_number, to_number)
            else:
                # Fallback to traditional approach
                self.logger.info(f"🔄 Using traditional voice response for trial account compatibility")
                return await self._handle_traditional_voice_response(call_sid, from_number, to_number)
            
        except Exception as e:
            self.logger.error(f"❌ Error handling voice webhook: {e}")
            
            # Fallback response
            response = VoiceResponse()
            response.say(
                "I'm sorry, our AI assistant is temporarily unavailable. Please try calling back in a moment.",
                voice=getattr(settings, 'voice_type', 'alice'),
                language='en-US'
            )
            response.hangup()
            
            return Response(content=str(response), media_type='text/xml')

    async def _handle_traditional_voice_response(self, call_sid: str, from_number: str, to_number: str) -> Response:
        """Handle voice calls using traditional approach (works on trial accounts)."""
        
        response = VoiceResponse()
        
        # Welcome message
        response.say(
            "Hi there! Thanks for calling Food Fusion. How can I assist you today?",
            voice=getattr(settings, 'voice_type', 'alice'),
            language='en-US'
        )
        
        # Gather user input
        gather = response.gather(
            input='speech',
            action=f"{getattr(settings, 'base_webhook_url', f'http://{settings.host}:{settings.port}')}/process-speech",
            speech_timeout='auto',
            timeout=10,
            method='POST'
        )
        
        # If no input received
        response.say(
            "I didn't hear anything. Please call back if you need assistance. Thank you for calling VoicePlate!",
            voice=getattr(settings, 'voice_type', 'alice'),
            language='en-US'
        )
        response.hangup()
        
        # Store call session
        self.call_sessions[call_sid] = {
            'from_number': from_number,
            'to_number': to_number,
            'start_time': time.time(),
            'status': 'traditional_voice',
            'conversation_history': []
        }
        
        twiml_content = str(response)
        self.logger.info(f"✅ Traditional voice response for call {call_sid}")
        
        return Response(content=twiml_content, media_type='text/xml')

    async def _handle_realtime_voice_response(self, call_sid: str, from_number: str, to_number: str) -> Response:
        """Handle voice calls using realtime approach (for paid accounts)."""
        
        response = VoiceResponse()
        
        # Welcome message
        response.say(
            "Hi there! Thanks for calling Food Fusion. How can I assist you today?",
            voice=getattr(settings, 'voice_type', 'alice'),
            language='en-US'
        )
        
        # Connect to Media Streams for real-time processing
        connect = Connect()
        
        # Construct WebSocket URL (same server, different endpoint)
        base_url = getattr(settings, 'base_webhook_url', f'http://{settings.host}:{settings.port}')
        if base_url.startswith('https://'):
            websocket_url = base_url.replace('https://', 'wss://') + '/ws/media'
        elif base_url.startswith('http://'):
            websocket_url = base_url.replace('http://', 'ws://') + '/ws/media'
        else:
            websocket_url = f"wss://{base_url}/ws/media"
        
        # Create Media Stream
        stream = Stream(url=websocket_url)
        stream.parameter(name='track', value='both_tracks')
        stream.parameter(name='statusCallback', value=f"{base_url}/stream/status")
        
        connect.append(stream)
        response.append(connect)
        
        # Store call session
        self.call_sessions[call_sid] = {
            'from_number': from_number,
            'to_number': to_number,
            'start_time': time.time(),
            'status': 'connecting'
        }

        twiml_content = str(response)
        self.logger.info(f"✅ Realtime response for call {call_sid}")
        self.logger.debug(f"🔗 WebSocket URL: {websocket_url}")
        
        return Response(content=twiml_content, media_type='text/xml')

    async def process_speech(self, request: Request) -> Response:
        """Process speech input from Twilio and generate AI response."""
        
        # Parse request data
        form_data = await request.form()
        call_sid = str(form_data.get("CallSid", ""))
        speech_result = str(form_data.get("SpeechResult", "")).strip()
        confidence_str = str(form_data.get("Confidence", "0"))
        
        try:
            confidence = float(confidence_str)
        except (ValueError, TypeError):
            confidence = 0.0
        
        if not call_sid:
            self.logger.error("❌ No CallSid provided in speech processing request")
            return self._create_error_response("Missing call information")
        
        if not speech_result:
            self.logger.warning(f"⚠️ No speech result for call {call_sid}")
            return self._create_no_input_response()
        
        self.logger.info(f"🎤 Speech processing for call {call_sid}: '{speech_result}' (confidence: {confidence})")
        
        # Get conversation history for this call
        conversation_history = self.call_sessions.get(call_sid, {}).get('conversation_history', [])
        
        # Process with OpenAI (now async)
        try:
            ai_response, updated_history = await openai_service.process_conversation_turn(
                speech_result, conversation_history
            )
            
            # Update conversation history
            if call_sid in self.call_sessions:
                self.call_sessions[call_sid]['conversation_history'] = updated_history
            
        except Exception as e:
            self.logger.error(f"❌ Error processing conversation: {e}")
            ai_response = "I'm sorry, I encountered an issue. Could you please repeat your question?"
        
        self.logger.info(f"🤖 AI response for {call_sid}: {ai_response[:100]}...")
        
        # Create TwiML response
        response = VoiceResponse()
        
        # Add AI response
        response.say(
            ai_response,
            voice=getattr(settings, 'voice_type', 'alice'),
            language=getattr(settings, 'language', 'en-US')
        )
        
        # Continue conversation or end call based on response
        if self._should_continue_conversation(ai_response):
            # Gather more input
            gather = response.gather(
                input='speech',
                action=f"{getattr(settings, 'base_webhook_url', f'http://{settings.host}:{settings.port}')}/process-speech",
                speech_timeout='auto',
                timeout=10,
                method='POST'
            )
        else:
            # End the call
            response.say("Thank you for calling VoicePlate! Have a great day!")
            response.hangup()
        
        twiml_content = str(response)
        self.logger.info(f"✅ Speech response for call {call_sid}")
        
        return Response(content=twiml_content, media_type='text/xml')

    def _create_error_response(self, error_message: str) -> Response:
        """Create an error response TwiML."""
        response = VoiceResponse()
        response.say(
            "Sorry, there was an error processing your request. Please try again.",
            voice=getattr(settings, 'voice_type', 'alice'),
            language=getattr(settings, 'language', 'en-US')
        )
        response.hangup()
        return Response(content=str(response), media_type='text/xml')

    def _create_no_input_response(self) -> Response:
        """Create a response for when no speech input is detected."""
        response = VoiceResponse()
        response.say(
            "I didn't hear anything. Please speak clearly and tell me how I can help you.",
            voice=getattr(settings, 'voice_type', 'alice'),
            language=getattr(settings, 'language', 'en-US')
        )
        
        # Try to gather again
        gather = response.gather(
            input='speech',
            action=f"{getattr(settings, 'base_webhook_url', f'http://{settings.host}:{settings.port}')}/process-speech",
            speech_timeout='auto',
            timeout=10,
            method='POST'
        )
        
        # Final fallback
        response.say(
            "Thank you for calling VoicePlate. Please call back if you need assistance.",
            voice=getattr(settings, 'voice_type', 'alice'),
            language=getattr(settings, 'language', 'en-US')
        )
        response.hangup()
        
        return Response(content=str(response), media_type='text/xml')

    def _should_continue_conversation(self, ai_response: str) -> bool:
        """Determine if the conversation should continue based on the AI response."""
        # Define end-of-conversation indicators
        end_phrases = [
            "thank you for calling",
            "have a great day",
            "goodbye",
            "call back",
            "talk to a human",
            "transfer you",
            "end this call"
        ]
        
        response_lower = ai_response.lower()
        
        # Check if response contains end phrases
        for phrase in end_phrases:
            if phrase in response_lower:
                return False
        
        # Continue conversation by default
        return True

    async def handle_stream_status(self, request: Request, status_data: Dict[str, str]) -> JSONResponse:
        """Handle Media Stream status callbacks from Twilio."""
        
        # Validate request is from Twilio
        if not self.validate_twilio_request(request):
            self.logger.warning("Invalid Twilio request received in stream status")
            raise HTTPException(status_code=403, detail="Forbidden")
        
        # Get stream status information
        call_sid = status_data.get('CallSid')
        stream_sid = status_data.get('StreamSid')
        status = status_data.get('Status')
        
        self.logger.info(f"📊 Stream status for call {call_sid}, stream {stream_sid}: {status}")
        
        # Update call session status
        if call_sid in self.call_sessions:
            self.call_sessions[call_sid]['stream_status'] = status
        
        return JSONResponse(content={"status": "ok"})

    async def handle_websocket_connection(self, websocket: WebSocket):
        """Handle WebSocket connection from Twilio Media Streams."""
        await websocket.accept()
        
        # Generate session ID
        session_id = f"realtime_{int(time.time())}_{hash(websocket)}"
        
        self.logger.info(f"🎧 New WebSocket connection established: {session_id}")
        self.logger.info(f"🔍 DEBUGGING: WebSocket connection from: {websocket.client}")
        
        # Initialize session
        self.active_sessions[session_id] = {
            'websocket': websocket,
            'call_sid': None,
            'stream_sid': None,
            'connected_at': time.time(),
            'status': 'connecting',
            'realtime_connected': False
        }
        
        try:
            self.logger.info(f"🔍 DEBUGGING: Starting WebSocket lifecycle for {session_id}")
            await self._handle_websocket_lifecycle(session_id, websocket)
        except WebSocketDisconnect:
            self.logger.info(f"📞 WebSocket disconnected: {session_id}")
        except Exception as e:
            self.logger.error(f"❌ Error in WebSocket connection {session_id}: {str(e)}")
            import traceback
            self.logger.error(f"❌ Full traceback: {traceback.format_exc()}")
        finally:
            await self._cleanup_session(session_id)

    async def _handle_websocket_lifecycle(self, session_id: str, websocket: WebSocket):
        """Handle the complete lifecycle of a WebSocket session."""
        
        # Wait for Twilio stream start
        stream_info = await self._wait_for_stream_start(session_id, websocket)
        if not stream_info:
            return
        
        # Initialize OpenAI Realtime connection
        success = await self._initialize_realtime_connection(session_id)
        if not success:
            self.logger.error(f"❌ Failed to initialize realtime connection for {session_id}")
            await websocket.close(code=1011, reason="Failed to connect to OpenAI")
            return
        
        # Start bidirectional audio streaming
        await self._start_audio_streaming(session_id, websocket)

    async def _wait_for_stream_start(self, session_id: str, websocket: WebSocket, timeout: int = 10) -> Optional[Dict[str, Any]]:
        """Wait for Twilio to send the initial stream start message."""
        self.logger.info(f"⏳ Waiting for stream start from Twilio for session {session_id}")
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                message = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
                data = json.loads(message)
                
                if data.get('event') == 'start':
                    # Extract stream information
                    start_data = data.get('start', {})
                    call_sid = start_data.get('callSid')
                    stream_sid = data.get('streamSid')
                    
                    # Update session
                    self.active_sessions[session_id].update({
                        'call_sid': call_sid,
                        'stream_sid': stream_sid,
                        'status': 'started'
                    })
                    
                    # Update call session
                    if call_sid in self.call_sessions:
                        self.call_sessions[call_sid]['status'] = 'streaming'
                        self.call_sessions[call_sid]['stream_sid'] = stream_sid
                    
                    self.logger.info(f"✅ Stream started for session {session_id}, call {call_sid}, stream {stream_sid}")
                    return data
                    
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                self.logger.error(f"❌ Error waiting for stream start: {e}")
                return None
        
        self.logger.error(f"❌ Timeout waiting for stream start for session {session_id}")
        return None

    async def _initialize_realtime_connection(self, session_id: str) -> bool:
        """Initialize OpenAI Realtime API connection for this session."""
        try:
            self.logger.info(f"🔗 Initializing OpenAI Realtime connection for session {session_id}")
            
            # Generate a unique realtime session ID
            import time
            realtime_session_id = f"realtime_{int(time.time())}"
            
            # Connect to OpenAI Realtime API
            success = await self.realtime_service.connect(realtime_session_id)
            if not success:
                self.logger.error(f"❌ Failed to connect to OpenAI for session {session_id}")
                return False
            
            # Store the realtime session ID for this WebSocket session
            self.active_sessions[session_id]['realtime_session_id'] = realtime_session_id
            self.active_sessions[session_id]['realtime_connected'] = True
            
            # Wait a moment for the connection to stabilize
            await asyncio.sleep(0.5)
            
            # Verify the connection is still active before sending configuration
            session_info = await self.realtime_service.get_session_info(realtime_session_id)
            if not session_info or session_info.get('state') != 'connected':
                self.logger.error(f"❌ OpenAI session {realtime_session_id} not in connected state")
                return False
            
            # Configure the session with restaurant-specific instructions and function calling
            session_config = {
                "type": "session.update",
                "session": {
                    "modalities": ["text", "audio"],
                    "instructions": self._get_system_instructions(),
                    "voice": settings.realtime_voice,
                    "input_audio_format": settings.realtime_input_audio_format,
                    "output_audio_format": settings.realtime_output_audio_format,
                    "input_audio_transcription": {"model": "whisper-1"},
                    "turn_detection": {
                        "type": settings.realtime_turn_detection,
                        "threshold": 0.6,  # Slightly higher threshold for cleaner detection
                        "prefix_padding_ms": 200,  # Reduced padding for faster response
                        "silence_duration_ms": 800  # Longer silence for better conversation flow
                    },
                    "temperature": 0.7,  # Optimized for more natural conversation
                    "max_response_output_tokens": 150,  # Shorter responses for voice
                    "tools": self._get_function_definitions()
                }
            }
            
            # Send session configuration with retry logic
            config_success = False
            for attempt in range(3):  # Try up to 3 times
                try:
                    await self.realtime_service.send_message(session_config, realtime_session_id)
                    self.logger.info(f"✅ Session configuration sent successfully (attempt {attempt + 1})")
                    config_success = True
                    break
                except Exception as e:
                    self.logger.warning(f"⚠️ Configuration attempt {attempt + 1} failed: {e}")
                    if attempt < 2:  # Don't wait after the last attempt
                        await asyncio.sleep(1)
            
            if not config_success:
                self.logger.error(f"❌ Failed to configure OpenAI session after 3 attempts")
                return False
            
            # Final verification that the session is still connected
            await asyncio.sleep(0.2)  # Brief wait for configuration to be processed
            final_session_info = await self.realtime_service.get_session_info(realtime_session_id)
            if not final_session_info or final_session_info.get('state') != 'connected':
                self.logger.error(f"❌ OpenAI session {realtime_session_id} disconnected after configuration")
                return False
            
            self.logger.info(f"✅ OpenAI Realtime connection fully established for session {session_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to initialize realtime connection for {session_id}: {e}")
            import traceback
            self.logger.error(f"❌ Full traceback: {traceback.format_exc()}")
            return False

    def _get_function_definitions(self) -> list:
        """Get function definitions for dynamic API fetching."""
        return [
            {
                "type": "function",
                "name": "get_menu_information",
                "description": "Fetch current menu items, prices, and categories from the restaurant's menu API. Use this when customers ask about food, drinks, menu items, prices, or what's available.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The customer's menu-related question or search term"
                        }
                    },
                    "required": ["query"]
                }
            },
            {
                "type": "function", 
                "name": "get_business_information",
                "description": "Fetch current business information including store hours, delivery hours, contact info, and location details. Use this when customers ask about opening hours, closing times, delivery, location, or contact information.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The customer's business-related question"
                        }
                    },
                    "required": ["query"]
                }
            },
            {
                "type": "function",
                "name": "get_promotion_information", 
                "description": "Fetch current promotions, deals, discounts, and special offers. Use this when customers ask about promotions, deals, discounts, coupons, or special offers.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The customer's promotion-related question"
                        }
                    },
                    "required": ["query"]
                }
            }
        ]

    def _get_system_instructions(self) -> str:
        """Get the optimized system instructions for the OpenAI Realtime session."""
        return """You are VoicePlate, a friendly and professional AI call assistant for FoodFusion TB restaurant.

🚨 CRITICAL RULE: NEVER say "I don't know" - ALWAYS use function calls to get real data!

🎯 PHONE CONVERSATION STYLE:
- Keep responses SHORT and conversational (1-2 sentences max)
- Sound natural and friendly, like a helpful restaurant staff member
- Speak at a comfortable pace for phone calls
- Use simple, clear language that's easy to understand over the phone

🚨 MANDATORY FUNCTION CALLING RULES:
You MUST call functions for ANY business-related question. DO NOT guess or say you don't know!

1. 📋 MENU QUESTIONS → ALWAYS call get_menu_information() FIRST
   - "What's on your menu?" → Call function immediately
   - "Do you have pizza?" → Call function immediately  
   - "What desserts do you have?" → Call function immediately
   - "How much does X cost?" → Call function immediately
   - ANY food/drink question → Call function immediately

2. 🏪 BUSINESS QUESTIONS → ALWAYS call get_business_information() FIRST
   - "Are you open?" → Call function immediately
   - "What time do you close?" → Call function immediately
   - "Do you deliver?" → Call function immediately
   - "What's your phone number?" → Call function immediately
   - "Where are you located?" → Call function immediately
   - ANY hours/location/contact question → Call function immediately

3. 🎁 PROMOTION QUESTIONS → ALWAYS call get_promotion_information() FIRST
   - "Any deals?" → Call function immediately
   - "Do you have promotions?" → Call function immediately
   - "Any discounts?" → Call function immediately
   - "Special offers?" → Call function immediately
   - ANY promotion/deal/discount question → Call function immediately

🗣️ CONVERSATION PATTERNS:

STEP 1: IMMEDIATELY call the appropriate function
STEP 2: Use the exact data returned from the function
STEP 3: Respond naturally with that real data

For MENU questions:
- Say: "Let me check our current menu for you..."
- Call get_menu_information() immediately
- Then: "We have [exact items from API] for [exact prices from API]"

For BUSINESS questions:
- Say: "Let me check that information for you..."
- Call get_business_information() immediately  
- Then: Use EXACT information from API response

For PROMOTION questions:
- Say: "Let me see what deals we have available..."
- Call get_promotion_information() immediately
- Then: "We currently have [exact promotion from API] with code [exact code] offering [exact discount]"

🚫 NEVER SAY:
- "I don't know"
- "I'm not sure"
- "Let me transfer you"
- "I don't have that information"
- "We typically..." or "We usually..."
- ANY vague response about business information

✅ ALWAYS DO:
- Call the appropriate function IMMEDIATELY when asked about menu/hours/promotions
- Wait for the function response
- Use ONLY the exact information from the API response
- If function fails, say "Let me get someone who can help you with that specific information"

📞 PHONE ETIQUETTE:
- Greet warmly: "Hi! Thanks for calling FoodFusion TB, how can I help you today?"
- ALWAYS use functions for business questions
- Be conversational but use real data
- Ask if they need anything else before ending

🔄 CONVERSATION FLOW:
1. Listen to customer question
2. Identify if it's menu/business/promotion related
3. IMMEDIATELY call appropriate function  
4. Use exact API data in response
5. Ask if they need anything else

EXAMPLE CONVERSATIONS:

Customer: "Are you open right now?"
You: "Let me check our current hours for you..." [CALL get_business_information()]
You: [After API response] "Yes, we're open 24 hours!"

Customer: "Do you have any pizza?"
You: "Let me check our menu for you..." [CALL get_menu_information()]  
You: [After API response] "We have [specific pizza items with prices from API]"

Customer: "Any deals today?"
You: "Let me see what promotions we have available..." [CALL get_promotion_information()]
You: [After API response] "We have [exact promotion name] with code [exact code] offering [exact discount]"

REMEMBER: Your job is to help customers by getting them accurate, real-time information. ALWAYS use the functions - that's why they exist!"""

    async def _start_audio_streaming(self, session_id: str, websocket: WebSocket):
        """Start bidirectional audio streaming between Twilio and OpenAI."""
        self.logger.info(f"🎧 Starting bidirectional audio streaming for session {session_id}")
        
        # Create tasks for both directions - combine inbound handling into one task
        tasks = [
            asyncio.create_task(self._handle_twilio_messages(session_id, websocket)),
            asyncio.create_task(self._handle_outbound_audio(session_id, websocket))
        ]
        
        try:
            # Wait for any task to complete (or fail)
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            
            # Cancel remaining tasks
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                    
        except Exception as e:
            self.logger.error(f"❌ Error in audio streaming for session {session_id}: {e}")
        finally:
            self.logger.info(f"🛑 Audio streaming ended for session {session_id}")

    async def _handle_twilio_messages(self, session_id: str, websocket: WebSocket):
        """Handle all messages from Twilio (both audio and control messages)."""
        self.logger.info(f"📱 Starting Twilio message handler for session {session_id}")
        
        while self.active_sessions.get(session_id, {}).get('status') != 'ended':
            try:
                message = await websocket.receive_text()
                data = json.loads(message)
                
                event = data.get('event')
                
                if event == 'media':
                    # Handle audio data
                    media = data.get('media', {})
                    audio_payload = media.get('payload')
                    
                    if audio_payload:
                        # Get the realtime session ID
                        realtime_session_id = self.active_sessions.get(session_id, {}).get('realtime_session_id')
                        if realtime_session_id:
                            # Send to OpenAI Realtime API (already base64 encoded)
                            audio_message = {
                                "type": "input_audio_buffer.append",
                                "audio": audio_payload
                            }
                            await self.realtime_service.send_message(audio_message, realtime_session_id)
                        else:
                            self.logger.warning(f"⚠️ No realtime session for audio in {session_id}")
                        
                elif event == 'stop':
                    # Stream stopped
                    self.logger.info(f"🛑 Stream stopped for session {session_id}")
                    self.active_sessions[session_id]['status'] = 'ended'
                    break
                    
                elif event == 'mark':
                    # Mark event (optional handling)
                    mark_name = data.get('mark', {}).get('name')
                    self.logger.debug(f"📍 Mark received for session {session_id}: {mark_name}")
                    
                else:
                    # Log other events for debugging
                    self.logger.debug(f"📨 Received Twilio event: {event}")
                        
            except WebSocketDisconnect:
                self.logger.info(f"📞 Twilio WebSocket disconnected for session {session_id}")
                break
            except Exception as e:
                self.logger.error(f"❌ Error handling Twilio messages for {session_id}: {e}")
                break

    async def _handle_outbound_audio(self, session_id: str, websocket: WebSocket):
        """Handle audio from OpenAI and send to Twilio."""
        self.logger.info(f"🔊 Starting outbound audio handler for session {session_id}")
        
        # Get the realtime session ID from the active session
        realtime_session_id = self.active_sessions.get(session_id, {}).get('realtime_session_id')
        
        if not realtime_session_id:
            self.logger.error(f"❌ No realtime session ID found for {session_id}")
            return
        
        consecutive_errors = 0
        max_consecutive_errors = 5
        
        while self.active_sessions.get(session_id, {}).get('status') != 'ended':
            try:
                # Check if realtime session is still connected with better error handling
                try:
                    session_info = await self.realtime_service.get_session_info(realtime_session_id)
                    if not session_info or session_info.get('state') != 'connected':
                        consecutive_errors += 1
                        if consecutive_errors >= max_consecutive_errors:
                            self.logger.warning(f"⚠️ Max consecutive errors reached for {session_id}, ending session")
                            break
                        await asyncio.sleep(2)  # Wait longer before retrying
                        continue
                    else:
                        consecutive_errors = 0  # Reset error counter on success
                except Exception as session_check_error:
                    self.logger.debug(f"🔍 Session check failed (normal): {session_check_error}")
                    consecutive_errors += 1
                    if consecutive_errors >= max_consecutive_errors:
                        self.logger.warning(f"⚠️ Session check failures exceeded limit for {session_id}")
                        break
                    await asyncio.sleep(1)
                    continue
                
                # Receive from OpenAI Realtime API with shorter timeout to prevent hanging
                try:
                    message = await asyncio.wait_for(
                        self.realtime_service.receive_message(realtime_session_id), 
                        timeout=1.0
                    )
                    if not message:
                        await asyncio.sleep(0.1)  # Small delay before next attempt
                        continue
                except asyncio.TimeoutError:
                    # Timeout is normal, continue loop
                    continue
                except Exception as receive_error:
                    self.logger.debug(f"🔍 Receive error (may be normal): {receive_error}")
                    consecutive_errors += 1
                    if consecutive_errors >= max_consecutive_errors:
                        self.logger.warning(f"⚠️ Too many receive errors for {session_id}")
                        break
                    await asyncio.sleep(0.5)
                    continue
                
                # Reset error counter on successful message receive
                consecutive_errors = 0
                
                # Handle different message types
                message_type = message.get('type', '')
                
                if message_type == 'response.audio.delta':
                    # Audio response from OpenAI
                    audio_delta = message.get('delta')
                    if audio_delta:
                        # Send to Twilio
                        media_message = {
                            "event": "media",
                            "streamSid": self.active_sessions[session_id]['stream_sid'],
                            "media": {
                                "payload": audio_delta
                            }
                        }
                        await websocket.send_text(json.dumps(media_message))
                
                elif message_type == 'response.function_call_arguments.done':
                    # Function call from OpenAI - handle API data fetching
                    await self._handle_function_call(session_id, message)
                
                elif message_type == 'response.audio_transcript.done':
                    # Log the AI response transcript
                    transcript = message.get('transcript', '')
                    self.logger.info(f"🤖 AI said: {transcript}")
                
                elif message_type == 'input_audio_buffer.speech_started':
                    # User started speaking
                    self.logger.debug(f"🎤 User started speaking in session {session_id}")
                
                elif message_type == 'input_audio_buffer.speech_stopped':
                    # User stopped speaking
                    self.logger.debug(f"🎤 User stopped speaking in session {session_id}")
                
                elif message_type == 'conversation.item.input_audio_transcription.completed':
                    # Log user speech transcript
                    transcript = message.get('transcript', '')
                    self.logger.info(f"👤 User said: {transcript}")
                
                elif message_type == 'error':
                    # Handle OpenAI errors
                    error = message.get('error', {})
                    self.logger.error(f"❌ OpenAI error in {session_id}: {error}")
                    consecutive_errors += 1
                    if consecutive_errors >= max_consecutive_errors:
                        break
                
            except WebSocketDisconnect:
                self.logger.info(f"📞 WebSocket disconnected for session {session_id}")
                break
            except Exception as e:
                self.logger.error(f"❌ Error handling outbound audio for {session_id}: {e}")
                consecutive_errors += 1
                if consecutive_errors >= max_consecutive_errors:
                    self.logger.error(f"❌ Too many consecutive errors for {session_id}, ending session")
                    break
                await asyncio.sleep(1)  # Wait before retrying to avoid tight error loop

    async def _handle_function_call(self, session_id: str, message: Dict[str, Any]):
        """Handle function calls from OpenAI Realtime API and fetch real data."""
        try:
            # Get function call details - these are the correct field names
            call_id = message.get('call_id')
            function_name = message.get('name')
            arguments_str = message.get('arguments', '{}')
            
            self.logger.info(f"🔧 Function call received: {function_name}")
            self.logger.info(f"🔧 Call ID: {call_id}")
            self.logger.info(f"🔧 Arguments: {arguments_str}")
            
            # Parse function arguments
            try:
                arguments = json.loads(arguments_str) if arguments_str else {}
            except json.JSONDecodeError:
                self.logger.error(f"❌ Failed to parse function arguments: {arguments_str}")
                arguments = {}
            
            query = arguments.get('query', '')
            self.logger.info(f"🔧 Extracted query: '{query}'")
            
            # Get the realtime session ID
            realtime_session_id = self.active_sessions.get(session_id, {}).get('realtime_session_id')
            if not realtime_session_id:
                self.logger.error(f"❌ No realtime session ID for function call in {session_id}")
                return
            
            # Check if the session is still connected, attempt reconnection if needed
            session_info = await self.realtime_service.get_session_info(realtime_session_id)
            if not session_info or session_info.get('state') != 'connected':
                self.logger.warning(f"⚠️ OpenAI session {realtime_session_id} disconnected, attempting reconnection...")
                
                # Attempt to reconnect
                reconnect_success = await self._attempt_session_reconnection(session_id, realtime_session_id)
                if not reconnect_success:
                    self.logger.error(f"❌ Failed to reconnect OpenAI session for {session_id}")
                    return
                
                # Update the realtime session ID if it changed during reconnection
                realtime_session_id = self.active_sessions.get(session_id, {}).get('realtime_session_id')
            
            # Fetch real data based on function name with validation
            result = None
            self.logger.info(f"🔧 Processing function: {function_name}")
            
            if function_name == 'get_menu_information':
                self.logger.info(f"📋 Calling menu API for query: '{query}'")
                result = await self._fetch_menu_data(query)
                result = self._validate_and_format_response(result, "menu", query)
                self.logger.info(f"📋 Menu API result: {result[:100]}..." if result else "No result")
                
            elif function_name == 'get_business_information':
                self.logger.info(f"🏪 Calling business API for query: '{query}'")
                result = await self._fetch_business_data(query)
                result = self._validate_and_format_response(result, "business", query)
                self.logger.info(f"🏪 Business API result: {result[:100]}..." if result else "No result")
                
            elif function_name == 'get_promotion_information':
                self.logger.info(f"🎁 Calling promotion API for query: '{query}'")
                result = await self._fetch_promotion_data(query)
                result = self._validate_and_format_response(result, "promotion", query)
                self.logger.info(f"🎁 Promotion API result: {result[:100]}..." if result else "No result")
                
            else:
                result = f"I can help you with menu items, store hours, and current promotions. What specific information would you like to know?"
                self.logger.warning(f"⚠️ Unknown function called: {function_name}")
            
            # Ensure we have a valid result
            if not result or len(result.strip()) < 10:
                result = f"I'm having trouble accessing that information right now. Let me get someone who can help you with your question about {query}."
                self.logger.warning(f"⚠️ Empty or insufficient result from {function_name}")
            
            # Send function call result back to OpenAI using the correct format
            function_result = {
                "type": "conversation.item.create",
                "item": {
                    "id": f"fn_{int(time.time()) % 100000000}",  # Max 10 chars: fn_12345678
                    "type": "function_call_output", 
                    "call_id": call_id,
                    "output": result
                }
            }
            
            self.logger.info(f"📤 Sending function result back to OpenAI...")
            
            # Send the function result with retry logic
            success = await self._send_realtime_message_with_retry(function_result, realtime_session_id, session_id)
            if success:
                self.logger.info(f"✅ Function result sent successfully for {function_name}")
                
                # CRITICAL: Trigger response generation - this is required!
                response_trigger = {
                    "type": "response.create"
                }
                await self._send_realtime_message_with_retry(response_trigger, realtime_session_id, session_id)
                self.logger.info(f"🚀 Response generation triggered after {function_name}")
            else:
                self.logger.error(f"❌ Failed to send function result for {function_name}")
            
        except Exception as e:
            self.logger.error(f"❌ Error handling function call in {session_id}: {e}")
            import traceback
            self.logger.error(f"❌ Function call traceback: {traceback.format_exc()}")
            
            # Send error response
            try:
                realtime_session_id = self.active_sessions.get(session_id, {}).get('realtime_session_id')
                if realtime_session_id:
                    error_result = {
                        "type": "conversation.item.create",
                        "item": {
                            "id": f"err_{int(time.time()) % 100000000}",  # Max 11 chars: err_12345678
                            "type": "function_call_output",
                            "call_id": message.get('call_id', 'unknown'),
                            "output": "I'm experiencing technical difficulties. Let me get someone who can help you right away."
                        }
                    }
                    await self._send_realtime_message_with_retry(error_result, str(realtime_session_id), session_id)
                    # Trigger response
                    await self._send_realtime_message_with_retry({"type": "response.create"}, str(realtime_session_id), session_id)
            except Exception as inner_e:
                self.logger.error(f"❌ Error sending error response: {inner_e}")

    async def _attempt_session_reconnection(self, session_id: str, old_realtime_session_id: str) -> bool:
        """Attempt to reconnect a disconnected OpenAI session."""
        try:
            self.logger.info(f"🔄 Attempting to reconnect OpenAI session for {session_id}")
            
            # Disconnect the old session
            await self.realtime_service.disconnect(old_realtime_session_id)
            
            # Create a new session
            import time
            new_realtime_session_id = f"realtime_reconnect_{int(time.time())}"
            
            # Connect to OpenAI Realtime API
            success = await self.realtime_service.connect(new_realtime_session_id)
            if not success:
                self.logger.error(f"❌ Failed to reconnect to OpenAI for session {session_id}")
                return False
            
            # Update session info
            self.active_sessions[session_id]['realtime_session_id'] = new_realtime_session_id
            self.active_sessions[session_id]['realtime_connected'] = True
            
            # Wait for connection to stabilize
            await asyncio.sleep(0.5)
            
            # Send configuration again
            session_config = {
                "type": "session.update",
                "session": {
                    "modalities": ["text", "audio"],
                    "instructions": self._get_system_instructions(),
                    "voice": settings.realtime_voice,
                    "input_audio_format": settings.realtime_input_audio_format,
                    "output_audio_format": settings.realtime_output_audio_format,
                    "input_audio_transcription": {"model": "whisper-1"},
                    "turn_detection": {
                        "type": settings.realtime_turn_detection,
                        "threshold": 0.6,
                        "prefix_padding_ms": 200,
                        "silence_duration_ms": 800
                    },
                    "temperature": 0.7,
                    "max_response_output_tokens": 150,
                    "tools": self._get_function_definitions()
                }
            }
            
            await self.realtime_service.send_message(session_config, new_realtime_session_id)
            
            self.logger.info(f"✅ Successfully reconnected OpenAI session for {session_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to reconnect session {session_id}: {e}")
            return False

    async def _send_realtime_message_with_retry(self, message: Dict[str, Any], realtime_session_id: str, session_id: str, max_retries: int = 2) -> bool:
        """Send a message to the OpenAI Realtime API with retry logic and reconnection."""
        current_session_id = realtime_session_id
        
        for attempt in range(max_retries + 1):
            try:
                await self.realtime_service.send_message(message, current_session_id)
                return True
            except Exception as e:
                self.logger.warning(f"⚠️ Send attempt {attempt + 1} failed: {e}")
                
                if attempt < max_retries:
                    # Check if session is disconnected and try to reconnect
                    session_info = await self.realtime_service.get_session_info(current_session_id)
                    if not session_info or session_info.get('state') != 'connected':
                        self.logger.info(f"🔄 Attempting reconnection for retry {attempt + 1}")
                        reconnect_success = await self._attempt_session_reconnection(session_id, current_session_id)
                        if reconnect_success:
                            # Update realtime_session_id for next attempt
                            new_session_id = self.active_sessions.get(session_id, {}).get('realtime_session_id')
                            if new_session_id:
                                current_session_id = str(new_session_id)
                            else:
                                self.logger.error(f"❌ No session ID after reconnection")
                                return False
                        else:
                            self.logger.error(f"❌ Reconnection failed on retry {attempt + 1}")
                            return False
                    
                    await asyncio.sleep(1)  # Wait before retry
                else:
                    self.logger.error(f"❌ All send attempts failed for message type: {message.get('type', 'unknown')}")
                    return False
        
        return False

    def _validate_and_format_response(self, result: str, data_type: str, query: str) -> str:
        """Validate and format API response to ensure data integrity and optimize for voice."""
        try:
            if not result or len(result.strip()) < 3:
                return f"I'm having trouble accessing our {data_type} information right now. Let me connect you with someone who can help."
            
            # Voice optimization: Keep responses shorter and more conversational
            optimized_result = self._optimize_for_voice(result, data_type)
            
            # Add context markers to help AI understand this is authoritative data
            if data_type == "menu":
                formatted_result = f"OFFICIAL MENU DATA: {optimized_result}\n\nIMPORTANT: This is real menu data from our current menu. Use this exact information to answer the customer's question about: '{query}'. Be confident and specific about what we have available and the prices."
            elif data_type == "business":
                formatted_result = f"OFFICIAL BUSINESS DATA: {optimized_result}\n\nIMPORTANT: This is real business information. Use this exact information to answer the customer's question about: '{query}'. Be confident about our hours, delivery service, and contact details."
            elif data_type == "promotion":
                formatted_result = f"OFFICIAL PROMOTION DATA: {optimized_result}\n\nIMPORTANT: This is real promotion information. Use this exact information to answer the customer's question about: '{query}'. Be confident about the deals we have available."
            else:
                formatted_result = optimized_result
            
            # Add voice-specific instruction
            formatted_result += f"\n\nVOICE INSTRUCTION: Respond confidently using ONLY the official data above. Do NOT say 'I don't know' - you have the real information right here. Keep your response to 1-2 sentences and be helpful."
            
            self.logger.info(f"✅ Optimized {data_type} response: {len(formatted_result)} characters")
            return formatted_result
            
        except Exception as e:
            self.logger.error(f"❌ Error validating {data_type} response: {e}")
            return f"I'm experiencing technical difficulties accessing our {data_type} information. Let me connect you with a team member who can help."

    def _optimize_for_voice(self, result: str, data_type: str) -> str:
        """Optimize response content specifically for voice conversations."""
        try:
            # Remove excessive details and keep only essential information
            if data_type == "menu":
                return self._optimize_menu_for_voice(result)
            elif data_type == "business":
                return self._optimize_business_for_voice(result)
            elif data_type == "promotion":
                return self._optimize_promotion_for_voice(result)
            else:
                return result[:200]  # Limit to 200 characters for voice
                
        except Exception as e:
            self.logger.error(f"❌ Error optimizing response for voice: {e}")
            return result
    
    def _optimize_menu_for_voice(self, menu_result: str) -> str:
        """Optimize menu responses for voice conversations."""
        # Handle different menu response patterns
        if "for $" in menu_result:
            # Extract items with prices (limit to first 3 items)
            items = []
            sentences = menu_result.split('. ')
            for sentence in sentences:
                if "for $" in sentence and len(items) < 3:
                    # Clean up category IDs and make more voice-friendly
                    clean_sentence = sentence.strip()
                    # Remove category IDs like "CAT_a3vvc2d7ya84"
                    import re
                    clean_sentence = re.sub(r'CAT_[a-zA-Z0-9]+,?\s*', '', clean_sentence)
                    # Remove excessive categories listing
                    if "categories:" in clean_sentence and len(clean_sentence) > 100:
                        # Skip this sentence and look for actual items
                        continue
                    items.append(clean_sentence)
            
            if items:
                return ". ".join(items) + "."
        
        # Handle responses with category listings - make voice friendly
        if "categories:" in menu_result.lower():
            # Extract just the essential info after categories
            sentences = menu_result.split('. ')
            voice_friendly_parts = []
            
            for sentence in sentences:
                sentence = sentence.strip()
                # Skip category ID listings
                if "CAT_" in sentence and len(sentence) > 50:
                    continue
                # Include sentences with actual food items or useful info
                if any(keyword in sentence.lower() for keyword in ['items', 'popular', 'for $', 'available']):
                    # Clean up category IDs
                    import re
                    clean_sentence = re.sub(r'CAT_[a-zA-Z0-9]+,?\s*', '', sentence)
                    if len(clean_sentence.strip()) > 10:  # Only include meaningful sentences
                        voice_friendly_parts.append(clean_sentence)
                        if len(voice_friendly_parts) >= 2:  # Limit for voice
                            break
            
            if voice_friendly_parts:
                return ". ".join(voice_friendly_parts) + "."
        
        # Fallback: limit length and clean up for voice
        if len(menu_result) > 150:
            # Try to extract just the first meaningful sentence
            sentences = menu_result.split('. ')
            for sentence in sentences:
                if len(sentence.strip()) > 20 and "for $" in sentence:
                    return sentence.strip() + "."
            
            # If no good sentence found, truncate and clean
            truncated = menu_result[:150].strip()
            # Remove any incomplete words at the end
            last_space = truncated.rfind(' ')
            if last_space > 100:  # Only if we have enough content
                truncated = truncated[:last_space]
            return truncated + "..."
        
        return menu_result
    
    def _optimize_business_for_voice(self, business_result: str) -> str:
        """Optimize business responses for voice conversations."""
        # Keep business responses short and direct
        if len(business_result) > 100:
            # Extract key information
            sentences = business_result.split('. ')
            key_info = []
            
            for sentence in sentences:
                if any(keyword in sentence.lower() for keyword in ['open', 'deliver', 'hours', 'phone', 'located']):
                    key_info.append(sentence.strip())
                    if len(key_info) >= 2:  # Limit to 2 key pieces of info
                        break
            
            if key_info:
                return ". ".join(key_info) + "."
        
        return business_result
    
    def _optimize_promotion_for_voice(self, promo_result: str) -> str:
        """Optimize promotion responses for voice conversations."""
        # Keep promotion responses short and clear
        if len(promo_result) > 80:
            # Extract essential promo info
            if "with code" in promo_result and "offering" in promo_result:
                # Find the first complete promotion mention
                sentences = promo_result.split('. ')
                for sentence in sentences:
                    if "with code" in sentence and "offering" in sentence:
                        return sentence.strip() + "."
        
        return promo_result

    async def _send_realtime_message(self, message: Dict[str, Any], realtime_session_id: str) -> bool:
        """Send a message to the OpenAI Realtime API with proper error handling."""
        try:
            await self.realtime_service.send_message(message, realtime_session_id)
            return True
        except Exception as e:
            self.logger.error(f"❌ Error sending realtime message: {e}")
            return False

    async def _fetch_menu_data(self, query: str) -> str:
        """Fetch menu data using the API menu service with enhanced error handling."""
        try:
            from src.services.api_menu_service import api_menu_service
            
            self.logger.info(f"📋 Fetching menu data for query: '{query}'")
            
            # Validate that the service is available
            if not hasattr(api_menu_service, 'process_menu_query'):
                raise AttributeError("Menu service not properly configured")
            
            if api_menu_service.is_menu_related_query(query):
                result = await api_menu_service.process_menu_query(query)
                
                # Validate the response
                if result and len(result.strip()) > 10:  # Ensure we got meaningful data
                    self.logger.info(f"📋 Successfully fetched menu data: {len(result)} characters")
                    return f"Let me check our current menu for you... {result}"
                else:
                    self.logger.warning(f"📋 Menu API returned empty or minimal data")
                    return "I'm checking our menu system, but I'm having trouble accessing the details right now. Would you like me to connect you with someone who can help you with our menu?"
            else:
                # Fallback to full menu
                result = await api_menu_service.get_full_menu_text()
                if result and len(result.strip()) > 10:
                    return f"Here's what I can tell you about our menu... {result}"
                else:
                    return "I'm having trouble accessing our menu information right now. Let me connect you with someone who can help you with specific menu questions."
                
        except ImportError:
            self.logger.error(f"❌ Menu service not available - import failed")
            return "I'm having trouble accessing our menu system right now. Would you like me to connect you with a team member who can help with menu questions?"
        except Exception as e:
            self.logger.error(f"❌ Error fetching menu data: {e}")
            return "I'm experiencing some technical difficulties accessing our menu information. Let me connect you with someone who can help you right away."

    async def _fetch_business_data(self, query: str) -> str:
        """Fetch business data using the API business service with enhanced error handling."""
        try:
            from src.services.api_business_service import api_business_service
            
            self.logger.info(f"🏪 Fetching business data for query: '{query}'")
            
            # Validate that the service is available
            if not hasattr(api_business_service, 'process_business_query'):
                raise AttributeError("Business service not properly configured")
            
            if api_business_service.is_business_related_query(query):
                result = await api_business_service.process_business_query(query)
                
                # Validate the response
                if result and len(result.strip()) > 5:  # Ensure we got meaningful data
                    self.logger.info(f"🏪 Successfully fetched business data: {len(result)} characters")
                    return f"Let me check that information for you... {result}"
                else:
                    self.logger.warning(f"🏪 Business API returned empty or minimal data")
                    return "I'm checking our business information, but I'm having trouble accessing those details right now. Would you like me to connect you with someone who can help?"
            else:
                return "I can help you with store hours, delivery information, and contact details. What specific information would you like to know?"
                
        except ImportError:
            self.logger.error(f"❌ Business service not available - import failed")
            return "I'm having trouble accessing our business information system right now. Let me connect you with a team member who can help with hours and location details."
        except Exception as e:
            self.logger.error(f"❌ Error fetching business data: {e}")
            return "I'm experiencing some technical difficulties accessing our business information. Let me connect you with someone who can help you right away."

    async def _fetch_promotion_data(self, query: str) -> str:
        """Fetch promotion data using the API promo service with enhanced error handling."""
        try:
            from src.services.api_promo_service import api_promo_service
            
            self.logger.info(f"🎁 Fetching promotion data for query: '{query}'")
            
            # Validate that the service is available
            if not hasattr(api_promo_service, 'process_promo_query'):
                raise AttributeError("Promotion service not properly configured")
            
            if api_promo_service.is_promo_related_query(query):
                result = await api_promo_service.process_promo_query(query)
                
                # Validate the response
                if result and len(result.strip()) > 5:  # Ensure we got meaningful data
                    self.logger.info(f"🎁 Successfully fetched promotion data: {len(result)} characters")
                    return f"Let me check our current promotions for you... {result}"
                else:
                    self.logger.warning(f"🎁 Promotion API returned empty or minimal data")
                    return "I'm checking our current promotions, but I don't see any active offers right now. Let me connect you with someone who can tell you about any upcoming deals."
            else:
                return "I can help you with current promotions and special offers. What type of deals are you interested in?"
                
        except ImportError:
            self.logger.error(f"❌ Promotion service not available - import failed")
            return "I'm having trouble accessing our promotions system right now. Let me connect you with a team member who can tell you about current deals and offers."
        except Exception as e:
            self.logger.error(f"❌ Error fetching promotion data: {e}")
            return "I'm experiencing some technical difficulties accessing our promotion information. Let me connect you with someone who can help you with current offers."

    async def _cleanup_session(self, session_id: str):
        """Cleanup session resources."""
        self.logger.info(f"🧹 Cleaning up session {session_id}")
        
        try:
            # Disconnect from OpenAI Realtime API using the specific session ID
            realtime_session_id = self.active_sessions.get(session_id, {}).get('realtime_session_id')
            if realtime_session_id and self.active_sessions.get(session_id, {}).get('realtime_connected'):
                await self.realtime_service.disconnect(realtime_session_id)
            
            # Update call session status
            call_sid = self.active_sessions.get(session_id, {}).get('call_sid')
            if call_sid and call_sid in self.call_sessions:
                self.call_sessions[call_sid]['status'] = 'ended'
                self.call_sessions[call_sid]['end_time'] = time.time()
            
            # Remove session
            self.active_sessions.pop(session_id, None)
            
        except Exception as e:
            self.logger.error(f"❌ Error during session cleanup for {session_id}: {e}")

    def get_health_status(self) -> Dict[str, Any]:
        """Get health status of the realtime server."""
        active_sessions = len(self.active_sessions)
        active_calls = len([s for s in self.active_sessions.values() if s.get('status') == 'started'])
        realtime_connections = len([s for s in self.active_sessions.values() if s.get('realtime_connected')])
        
        return {
            'status': 'healthy',
            'service': 'VoicePlate Realtime Server',
            'version': '2.0.0',
            'realtime_enabled': settings.use_realtime_api,
            'active_sessions': active_sessions,
            'active_calls': active_calls,
            'realtime_connections': realtime_connections,
            'configuration': {
                'model': settings.openai_realtime_model,
                'voice': settings.realtime_voice,
                'audio_format': settings.realtime_input_audio_format,
                'turn_detection': settings.realtime_turn_detection
            }
        }

# Global server instance
realtime_server = RealtimeServer()

# Create FastAPI app with lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage the application lifespan."""
    logger.info("🚀 Starting VoicePlate Realtime Server")
    yield
    logger.info("🛑 Shutting down VoicePlate Realtime Server")

# Create FastAPI application
app = FastAPI(
    title="VoicePlate Realtime Server",
    description="AI Call Answering Agent with OpenAI Realtime API integration",
    version="2.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return realtime_server.get_health_status()

# Twilio voice webhook endpoint
@app.post("/voice")
async def voice_webhook(request: Request):
    """Handle incoming Twilio voice webhook."""
    try:
        # Parse form data from Twilio
        form_data = await request.form()
        call_data = {key: str(value) for key, value in form_data.items()}
        
        # Handle the voice webhook
        return await realtime_server.handle_voice_webhook(request, call_data)
        
    except Exception as e:
        logger.error(f"❌ Error in voice webhook: {e}")
        # Return a basic error response
        from twilio.twiml.voice_response import VoiceResponse
        response = VoiceResponse()
        response.say("Sorry, we're experiencing technical difficulties. Please try calling back later.", voice='alice')
        response.hangup()
        return Response(content=str(response), media_type='text/xml')

# Process speech endpoint for traditional mode
@app.post("/process-speech")
async def process_speech_endpoint(request: Request):
    """Process speech input from Twilio."""
    try:
        return await realtime_server.process_speech(request)
    except Exception as e:
        logger.error(f"❌ Error processing speech: {e}")
        return realtime_server._create_error_response(str(e))

# Stream status callback endpoint
@app.post("/stream/status")
async def stream_status_callback(request: Request):
    """Handle Twilio Media Stream status callbacks."""
    try:
        form_data = await request.form()
        status_data = {key: str(value) for key, value in form_data.items()}
        return await realtime_server.handle_stream_status(request, status_data)
    except Exception as e:
        logger.error(f"❌ Error in stream status callback: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)

# WebSocket endpoint for Media Streams
@app.websocket("/ws/media")
async def websocket_media(websocket: WebSocket):
    """Handle WebSocket connections from Twilio Media Streams."""
    try:
        await realtime_server.handle_websocket_connection(websocket)
    except Exception as e:
        logger.error(f"❌ Error in WebSocket connection: {e}")

# Main execution
if __name__ == "__main__":
    import uvicorn
    
    logger.info("🎯 Starting VoicePlate Realtime Server...")
    logger.info(f"🌐 Server will run on {settings.host}:{settings.port}")
    logger.info(f"📞 Webhook URL: http://{settings.host}:{settings.port}/voice")
    logger.info(f"🎧 WebSocket URL: ws://{settings.host}:{settings.port}/ws/media")
    logger.info(f"🔧 Health Check: http://{settings.host}:{settings.port}/health")
    
    # Run the server
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        reload=False,
        access_log=True
    ) 