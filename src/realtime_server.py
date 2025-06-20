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
            # Check if this might be a trial account - use traditional approach for better compatibility
            # Trial accounts often have issues with Media Streams/WebSocket functionality
            use_traditional_approach = True  # Default to traditional for trial account compatibility
            
            if use_traditional_approach:
                self.logger.info(f"🔄 Using traditional voice response for trial account compatibility")
                return await self._handle_traditional_voice_response(call_sid, from_number, to_number)
            else:
                # Original realtime approach (for paid accounts)
                return await self._handle_realtime_voice_response(call_sid, from_number, to_number)
            
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
            "Hi there! Thanks for calling Food Fusion. How can I assist you today? I can help you with the menu and answer any questions you have about our restaurant.",
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
            "Hi there! Thanks for calling Food Fusion. How can I assist you today? I can help you with the menu and answer any questions you have about our restaurant.",
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
                return False
            
            # Store the realtime session ID for this WebSocket session
            self.active_sessions[session_id]['realtime_session_id'] = realtime_session_id
            self.active_sessions[session_id]['realtime_connected'] = True
            
            # Configure the session with restaurant-specific instructions
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
                        "threshold": 0.5,
                        "prefix_padding_ms": 300,
                        "silence_duration_ms": 500
                    },
                    "temperature": settings.realtime_temperature,
                    "max_response_output_tokens": settings.realtime_max_tokens
                }
            }
            
            # Send session configuration
            await self.realtime_service.send_message(session_config, realtime_session_id)
            
            self.logger.info(f"✅ OpenAI Realtime connection established for session {session_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to initialize realtime connection for {session_id}: {e}")
            return False

    def _get_system_instructions(self) -> str:
        """Get the system instructions for the OpenAI Realtime session."""
        base_instructions = """You are VoicePlate, a helpful and professional AI call answering assistant for Applova - a smart restaurant and retail tech company.

Guidelines for real-time conversation:
- Respond naturally and conversationally
- Keep responses concise and clear (2-3 sentences max)
- Be helpful and professional
- If you don't know something, be honest
- Handle interruptions gracefully
- Maintain context throughout the conversation

You can help with:
- Menu information and pricing
- General information and questions  
- Basic customer service inquiries
- Routing calls to appropriate departments
- Taking messages and contact information

Remember: You're having a real-time conversation, so respond naturally as you would in person."""

        # Try to add menu context if available
        try:
            from src.services.menu_service import menu_service
            # Temporarily commented out due to type issues
            # if hasattr(menu_service, 'get_menu_context'):
            #     menu_info = menu_service.get_menu_context()
            #     if menu_info:
            #         base_instructions += f"\n\nCurrent menu information: {menu_info}\n\nUse this information to answer menu-related questions naturally."
        except Exception as e:
            self.logger.warning(f"⚠️ Could not load menu context: {e}")
        
        return base_instructions

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
        
        while self.active_sessions.get(session_id, {}).get('status') != 'ended':
            try:
                # Check if realtime session is still connected
                session_info = await self.realtime_service.get_session_info(realtime_session_id)
                if not session_info or session_info.get('state') != 'connected':
                    self.logger.warning(f"⚠️ Realtime session disconnected for {session_id}")
                    await asyncio.sleep(1)  # Wait before retrying
                    continue
                
                # Receive from OpenAI Realtime API with timeout
                try:
                    message = await asyncio.wait_for(
                        self.realtime_service.receive_message(realtime_session_id), 
                        timeout=2.0
                    )
                    if not message:
                        await asyncio.sleep(0.1)  # Small delay before next attempt
                        continue
                except asyncio.TimeoutError:
                    # Timeout is normal, continue loop
                    continue
                
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
                
                elif message_type == 'response.audio_transcript.done':
                    # Log the AI response transcript
                    transcript = message.get('transcript', '')
                    self.logger.info(f"🤖 AI said: {transcript}")
                
                elif message_type == 'input_audio_buffer.speech_started':
                    # User started speaking
                    self.logger.info(f"🎤 User started speaking in session {session_id}")
                
                elif message_type == 'input_audio_buffer.speech_stopped':
                    # User stopped speaking
                    self.logger.info(f"🎤 User stopped speaking in session {session_id}")
                
                elif message_type == 'conversation.item.input_audio_transcription.completed':
                    # Log user speech transcript
                    transcript = message.get('transcript', '')
                    self.logger.info(f"👤 User said: {transcript}")
                
                elif message_type == 'error':
                    # Handle OpenAI errors
                    error = message.get('error', {})
                    self.logger.error(f"❌ OpenAI error in {session_id}: {error}")
                    
            except WebSocketDisconnect:
                self.logger.info(f"📞 WebSocket disconnected for session {session_id}")
                break
            except Exception as e:
                self.logger.error(f"❌ Error handling outbound audio for {session_id}: {e}")
                await asyncio.sleep(1)  # Wait before retrying to avoid tight error loop
                break

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