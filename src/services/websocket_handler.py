"""
WebSocket Handler for Twilio Media Streams Integration
Handles bidirectional audio streaming between Twilio and OpenAI Realtime API.
"""

import json
import base64
import asyncio
import logging
import time
from typing import Dict, Optional, Any, Callable, List
from dataclasses import dataclass
import websockets
from websockets.exceptions import WebSocketException, ConnectionClosed
from fastapi import WebSocket, WebSocketDisconnect

from src.services.realtime_service import RealtimeService
from config.settings import settings
from src.services.realtime_service import realtime_service, RealtimeConfig, AudioFormat

@dataclass
class TwilioMediaStream:
    """Represents a Twilio Media Stream session"""
    call_sid: str
    stream_sid: str
    track: str  # "inbound" or "outbound"
    websocket: websockets.WebSocketServerProtocol
    realtime_session_id: Optional[str] = None
    is_active: bool = True
    metadata: Dict[str, Any] = None

class WebSocketHandler:
    """Handles WebSocket connections for Twilio Media Streams and OpenAI Realtime API integration."""
    
    def __init__(self):
        """Initialize the WebSocket handler."""
        self.logger = logging.getLogger(__name__)
        self.active_streams: Dict[str, TwilioMediaStream] = {}
        self.call_sessions: Dict[str, Dict[str, Any]] = {}
        
        # Audio format configuration for Twilio compatibility
        self.twilio_audio_config = RealtimeConfig(
            model=settings.openai_realtime_model,
            voice=settings.realtime_voice,
            input_audio_format=AudioFormat.G711_ULAW,  # Twilio compatible
            output_audio_format=AudioFormat.G711_ULAW,
            temperature=settings.realtime_temperature,
            max_tokens=settings.realtime_max_tokens,
            turn_detection={"type": settings.realtime_turn_detection}
        )
        
        self.logger.info("🎧 WebSocket handler initialized for Twilio Media Streams")

    async def handle_twilio_websocket(self, websocket, path: str):
        """
        Main handler for incoming Twilio Media Stream WebSocket connections.
        
        Args:
            websocket: The WebSocket connection from Twilio
            path: WebSocket path (contains call information)
        """
        stream_sid = None
        call_sid = None
        
        try:
            self.logger.info(f"🔗 New WebSocket connection from Twilio: {path}")
            
            async for message in websocket:
                try:
                    # Parse Twilio Media Stream message
                    data = json.loads(message)
                    event_type = data.get("event")
                    
                    if event_type == "connected":
                        self.logger.info("✅ Twilio WebSocket connected")
                        
                    elif event_type == "start":
                        # Media stream start event
                        await self._handle_stream_start(websocket, data)
                        stream_sid = data.get("streamSid")
                        call_sid = data.get("start", {}).get("callSid")
                        
                    elif event_type == "media":
                        # Audio data from Twilio
                        await self._handle_media_data(data)
                        
                    elif event_type == "stop":
                        # Media stream stop event
                        await self._handle_stream_stop(data)
                        break
                        
                except json.JSONDecodeError as e:
                    self.logger.error(f"❌ Failed to parse Twilio message: {e}")
                except Exception as e:
                    self.logger.error(f"❌ Error processing Twilio message: {e}")
                    
        except ConnectionClosed:
            self.logger.info(f"🔌 Twilio WebSocket connection closed for stream {stream_sid}")
        except Exception as e:
            self.logger.error(f"❌ WebSocket handler error: {e}")
        finally:
            # Cleanup
            if stream_sid:
                await self._cleanup_stream(stream_sid)

    async def _handle_stream_start(self, websocket, data: Dict[str, Any]):
        """Handle Twilio Media Stream start event."""
        start_data = data.get("start", {})
        stream_sid = data.get("streamSid")
        call_sid = start_data.get("callSid")
        track = start_data.get("tracks", ["inbound"])[0]  # Usually "inbound"
        
        self.logger.info(f"📞 Starting media stream: {stream_sid} for call {call_sid}")
        
        # Create Twilio media stream record
        media_stream = TwilioMediaStream(
            call_sid=call_sid,
            stream_sid=stream_sid,
            track=track,
            websocket=websocket,
            metadata=start_data
        )
        
        self.active_streams[stream_sid] = media_stream
        
        # Create or get call session
        if call_sid not in self.call_sessions:
            self.call_sessions[call_sid] = {
                "start_time": asyncio.get_event_loop().time(),
                "streams": [],
                "conversation_state": "active"
            }
        
        self.call_sessions[call_sid]["streams"].append(stream_sid)
        
        # Initialize OpenAI Realtime session if enabled
        if settings.use_realtime_api:
            await self._initialize_realtime_session(media_stream)
        
        # Send initial message to Twilio
        await self._send_to_twilio(websocket, {
            "event": "connected",
            "protocol": "Call"
        })

    async def _initialize_realtime_session(self, media_stream: TwilioMediaStream):
        """Initialize OpenAI Realtime API session for the media stream."""
        try:
            # Create realtime session with Twilio-compatible config
            session_id = f"twilio_{media_stream.call_sid}_{media_stream.stream_sid}"
            
            # Create session with menu integration
            config = self.twilio_audio_config
            
            # Add menu context to system message if available
            try:
                from src.services.menu_service import menu_service
                if hasattr(menu_service, 'get_menu_context'):
                    menu_info = menu_service.get_menu_context()
                    if menu_info:
                        config.system_message += f"\n\nCurrent menu information: {menu_info}"
            except Exception as e:
                self.logger.warning(f"⚠️ Could not load menu context: {e}")
            
            # Create and connect session
            session = await realtime_service.create_session(session_id, config)
            connected = await realtime_service.connect_to_openai(session_id)
            
            if connected:
                media_stream.realtime_session_id = session_id
                self.logger.info(f"✅ OpenAI Realtime session created: {session_id}")
                
                # Start listening for OpenAI events
                asyncio.create_task(self._handle_openai_events(session_id, media_stream))
            else:
                self.logger.error(f"❌ Failed to connect to OpenAI for session {session_id}")
                
                # Fallback to traditional API if realtime fails
                if settings.enable_realtime_fallback:
                    self.logger.info("🔄 Falling back to traditional API")
                    # Could implement fallback logic here
                    
        except Exception as e:
            self.logger.error(f"❌ Error initializing realtime session: {e}")

    async def _handle_media_data(self, data: Dict[str, Any]):
        """Handle audio data from Twilio Media Stream."""
        stream_sid = data.get("streamSid")
        media_data = data.get("media", {})
        payload = media_data.get("payload", "")
        
        if stream_sid not in self.active_streams:
            self.logger.warning(f"⚠️ Received media for unknown stream: {stream_sid}")
            return
        
        media_stream = self.active_streams[stream_sid]
        
        # Send audio to OpenAI Realtime API if session is active
        if media_stream.realtime_session_id and settings.use_realtime_api:
            try:
                # Twilio sends μ-law encoded audio as base64
                # OpenAI Realtime API expects the same format
                success = await realtime_service.stream_audio_to_openai(
                    media_stream.realtime_session_id,
                    payload
                )
                
                if not success:
                    self.logger.warning(f"⚠️ Failed to stream audio to OpenAI for {stream_sid}")
                    
            except Exception as e:
                self.logger.error(f"❌ Error streaming audio to OpenAI: {e}")
        else:
            # Traditional API fallback would go here
            self.logger.debug(f"📊 Received {len(payload)} bytes of audio for {stream_sid}")

    async def _handle_openai_events(self, session_id: str, media_stream: TwilioMediaStream):
        """Handle events from OpenAI Realtime API and forward audio to Twilio."""
        try:
            async def event_handler(event: Dict[str, Any]):
                event_type = event.get("type", "")
                
                if event_type == "response.audio.delta":
                    # Forward audio response to Twilio
                    await self._forward_audio_to_twilio(media_stream, event)
                    
                elif event_type == "input_audio_buffer.speech_started":
                    self.logger.info(f"🎙️ User started speaking in {session_id}")
                    
                elif event_type == "input_audio_buffer.speech_stopped":
                    self.logger.info(f"🔇 User stopped speaking in {session_id}")
                    # Commit audio buffer to trigger response
                    await realtime_service.commit_audio_buffer(session_id)
                    
                elif event_type == "response.done":
                    self.logger.info(f"✅ OpenAI response completed for {session_id}")
                    
                elif event_type == "error":
                    error = event.get("error", {})
                    self.logger.error(f"❌ OpenAI error in {session_id}: {error}")
            
            # Start listening for OpenAI events
            await realtime_service.listen_for_events(session_id, event_handler)
            
        except Exception as e:
            self.logger.error(f"❌ Error handling OpenAI events: {e}")

    async def _forward_audio_to_twilio(self, media_stream: TwilioMediaStream, event: Dict[str, Any]):
        """Forward audio response from OpenAI back to Twilio."""
        try:
            audio_delta = event.get("delta", "")
            if not audio_delta:
                return
            
            # Create Twilio media message
            twilio_message = {
                "event": "media",
                "streamSid": media_stream.stream_sid,
                "media": {
                    "payload": audio_delta,
                    "track": "outbound"
                }
            }
            
            # Send to Twilio WebSocket
            await self._send_to_twilio(media_stream.websocket, twilio_message)
            
            self.logger.debug(f"🎵 Forwarded {len(audio_delta)} bytes to Twilio {media_stream.stream_sid}")
            
        except Exception as e:
            self.logger.error(f"❌ Error forwarding audio to Twilio: {e}")

    async def _send_to_twilio(self, websocket, message: Dict[str, Any]):
        """Send a message to Twilio WebSocket."""
        try:
            await websocket.send(json.dumps(message))
        except Exception as e:
            self.logger.error(f"❌ Error sending to Twilio WebSocket: {e}")

    async def _handle_stream_stop(self, data: Dict[str, Any]):
        """Handle Twilio Media Stream stop event."""
        stream_sid = data.get("streamSid")
        
        if stream_sid in self.active_streams:
            media_stream = self.active_streams[stream_sid]
            call_sid = media_stream.call_sid
            
            self.logger.info(f"🛑 Stopping media stream: {stream_sid} for call {call_sid}")
            
            # Close OpenAI Realtime session
            if media_stream.realtime_session_id:
                await realtime_service.close_session(media_stream.realtime_session_id)
            
            # Update call session
            if call_sid in self.call_sessions:
                self.call_sessions[call_sid]["conversation_state"] = "ended"
                # Remove stream from call session
                if stream_sid in self.call_sessions[call_sid]["streams"]:
                    self.call_sessions[call_sid]["streams"].remove(stream_sid)
            
            # Mark stream as inactive
            media_stream.is_active = False

    async def _cleanup_stream(self, stream_sid: str):
        """Clean up resources for a media stream."""
        if stream_sid in self.active_streams:
            media_stream = self.active_streams[stream_sid]
            
            # Close OpenAI session if still active
            if media_stream.realtime_session_id:
                await realtime_service.close_session(media_stream.realtime_session_id)
            
            # Remove from active streams
            del self.active_streams[stream_sid]
            
            self.logger.info(f"🗑️ Cleaned up stream {stream_sid}")

    async def handle_interruption(self, stream_sid: str, audio_end_ms: Optional[int] = None):
        """Handle user interruption during AI response."""
        if stream_sid not in self.active_streams:
            return False
        
        media_stream = self.active_streams[stream_sid]
        
        if media_stream.realtime_session_id:
            success = await realtime_service.handle_interruption(
                media_stream.realtime_session_id,
                audio_end_ms=audio_end_ms
            )
            
            if success:
                self.logger.info(f"🛑 Handled interruption for stream {stream_sid}")
            
            return success
        
        return False

    def get_active_streams(self) -> Dict[str, Dict[str, Any]]:
        """Get information about all active streams."""
        return {
            stream_sid: {
                "call_sid": stream.call_sid,
                "track": stream.track,
                "realtime_session": stream.realtime_session_id,
                "is_active": stream.is_active
            }
            for stream_sid, stream in self.active_streams.items()
        }

    def get_call_sessions(self) -> Dict[str, Dict[str, Any]]:
        """Get information about all call sessions."""
        return self.call_sessions.copy()

    async def health_check(self) -> Dict[str, Any]:
        """Health check for the WebSocket handler."""
        active_streams = len(self.active_streams)
        active_calls = len(self.call_sessions)
        realtime_sessions = len([s for s in self.active_streams.values() if s.realtime_session_id])
        
        return {
            "service": "websocket_handler",
            "status": "healthy",
            "active_streams": active_streams,
            "active_calls": active_calls,
            "realtime_sessions": realtime_sessions,
            "realtime_api_enabled": settings.use_realtime_api,
            "fallback_enabled": settings.enable_realtime_fallback
        }

class TwilioWebSocketHandler:
    """Handles Twilio Media Streams WebSocket connections and bridges to OpenAI Realtime API."""
    
    def __init__(self):
        """Initialize the WebSocket handler."""
        self.logger = logging.getLogger(__name__)
        self.realtime_service = RealtimeService()
        self.sessions: Dict[str, Any] = {}
        
        # Audio processing buffers
        self.audio_buffers: Dict[str, List[bytes]] = {}
        self.session_configs: Dict[str, Dict[str, Any]] = {}
        
        # Connection tracking
        self.active_connections: Dict[str, Any] = {}
        
    async def handle_connection(self, websocket: WebSocket):
        """Handle a new WebSocket connection from Twilio Media Streams."""
        await websocket.accept()
        
        # Generate session ID
        session_id = f"session_{int(time.time())}_{hash(websocket)}"
        
        self.logger.info(f"📞 New WebSocket connection established: {session_id}")
        
        # Initialize session
        self.sessions[session_id] = {
            'websocket': websocket,
            'call_sid': None,
            'stream_sid': None,
            'connected_at': time.time(),
            'status': 'connecting'
        }
        
        self.audio_buffers[session_id] = []
        self.active_connections[session_id] = websocket
        
        try:
            # Handle the connection lifecycle
            await self._handle_session_lifecycle(session_id, websocket)
            
        except WebSocketDisconnect:
            self.logger.info(f"📞 Client disconnected: {session_id}")
        except Exception as e:
            self.logger.error(f"❌ Error in WebSocket connection {session_id}: {str(e)}")
        finally:
            # Cleanup session
            await self._cleanup_session(session_id)

    async def _handle_session_lifecycle(self, session_id: str, websocket: WebSocket):
        """Handle the complete lifecycle of a WebSocket session."""
        
        # Wait for initial connection and setup
        await self._wait_for_stream_start(session_id, websocket)
        
        # Initialize OpenAI Realtime connection
        success = await self._initialize_realtime_connection(session_id)
        if not success:
            self.logger.error(f"❌ Failed to initialize realtime connection for {session_id}")
            await websocket.close(code=1011, reason="Failed to connect to OpenAI")
            return
        
        # Start bidirectional audio streaming
        await self._start_audio_streaming(session_id, websocket)

    async def _wait_for_stream_start(self, session_id: str, websocket: WebSocket, timeout: int = 10):
        """Wait for Twilio to send the initial stream start message."""
        self.logger.info(f"⏳ Waiting for stream start from Twilio for session {session_id}")
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                # Wait for message with timeout
                message = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
                data = json.loads(message)
                
                if data.get('event') == 'start':
                    # Stream started - extract call information
                    call_sid = data.get('callSid')
                    stream_sid = data.get('streamSid')
                    
                    self.sessions[session_id].update({
                        'call_sid': call_sid,
                        'stream_sid': stream_sid,
                        'status': 'started'
                    })
                    
                    self.logger.info(f"✅ Stream started for session {session_id}, call {call_sid}, stream {stream_sid}")
                    return True
                    
            except asyncio.TimeoutError:
                # Continue waiting
                continue
            except Exception as e:
                self.logger.error(f"❌ Error waiting for stream start: {e}")
                return False
        
        self.logger.error(f"❌ Timeout waiting for stream start for session {session_id}")
        return False

    async def _initialize_realtime_connection(self, session_id: str) -> bool:
        """Initialize OpenAI Realtime API connection for this session."""
        try:
            self.logger.info(f"🔗 Initializing OpenAI Realtime connection for session {session_id}")
            
            # Connect to OpenAI Realtime API
            success = await self.realtime_service.connect()
            if not success:
                return False
            
            # Configure the session
            session_config = {
                "type": "session.update",
                "session": {
                    "modalities": ["text", "audio"],
                    "instructions": self._get_session_instructions(),
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
            await self.realtime_service.send_message(session_config)
            
            self.session_configs[session_id] = session_config
            self.sessions[session_id]['realtime_connected'] = True
            
            self.logger.info(f"✅ OpenAI Realtime connection established for session {session_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to initialize realtime connection for {session_id}: {e}")
            return False

    def _get_session_instructions(self) -> str:
        """Get the system instructions for the OpenAI Realtime session."""
        return """You are VoicePlate, a helpful and professional AI call answering assistant for Applova - a smart restaurant and retail tech company.

Guidelines for real-time conversation:
- Respond naturally and conversationally
- Keep responses concise and clear
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

    async def _start_audio_streaming(self, session_id: str, websocket: WebSocket):
        """Start bidirectional audio streaming between Twilio and OpenAI."""
        self.logger.info(f"🎧 Starting bidirectional audio streaming for session {session_id}")
        
        # Create tasks for both directions
        tasks = [
            asyncio.create_task(self._handle_inbound_audio(session_id, websocket)),
            asyncio.create_task(self._handle_outbound_audio(session_id, websocket)),
            asyncio.create_task(self._handle_twilio_messages(session_id, websocket))
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

    async def _handle_inbound_audio(self, session_id: str, websocket: WebSocket):
        """Handle audio from Twilio (user speaking) and send to OpenAI."""
        self.logger.info(f"🎤 Starting inbound audio handler for session {session_id}")
        
        while self.sessions.get(session_id, {}).get('status') != 'ended':
            try:
                message = await websocket.receive_text()
                data = json.loads(message)
                
                if data.get('event') == 'media':
                    # Extract audio data
                    audio_payload = data.get('media', {}).get('payload')
                    if audio_payload:
                        # Decode base64 audio
                        audio_data = base64.b64decode(audio_payload)
                        
                        # Send to OpenAI Realtime API
                        audio_message = {
                            "type": "input_audio_buffer.append",
                            "audio": base64.b64encode(audio_data).decode('utf-8')
                        }
                        await self.realtime_service.send_message(audio_message)
                        
            except WebSocketDisconnect:
                break
            except Exception as e:
                self.logger.error(f"❌ Error handling inbound audio for {session_id}: {e}")
                break

    async def _handle_outbound_audio(self, session_id: str, websocket: WebSocket):
        """Handle audio from OpenAI and send to Twilio."""
        self.logger.info(f"🔊 Starting outbound audio handler for session {session_id}")
        
        while self.sessions.get(session_id, {}).get('status') != 'ended':
            try:
                # Receive from OpenAI Realtime API
                message = await self.realtime_service.receive_message()
                if not message:
                    continue
                
                # Handle different message types
                if message.get('type') == 'response.audio.delta':
                    # Audio response from OpenAI
                    audio_data = message.get('delta')
                    if audio_data:
                        # Send to Twilio
                        media_message = {
                            "event": "media",
                            "streamSid": self.sessions[session_id]['stream_sid'],
                            "media": {
                                "payload": audio_data
                            }
                        }
                        await websocket.send_text(json.dumps(media_message))
                
                elif message.get('type') == 'response.audio_transcript.done':
                    # Log the AI response transcript
                    transcript = message.get('transcript', '')
                    self.logger.info(f"🤖 AI said: {transcript}")
                
                elif message.get('type') == 'input_audio_buffer.speech_started':
                    # User started speaking
                    self.logger.info(f"🎤 User started speaking in session {session_id}")
                
                elif message.get('type') == 'input_audio_buffer.speech_stopped':
                    # User stopped speaking
                    self.logger.info(f"🎤 User stopped speaking in session {session_id}")
                
                elif message.get('type') == 'conversation.item.input_audio_transcription.completed':
                    # Log user speech transcript
                    transcript = message.get('transcript', '')
                    self.logger.info(f"👤 User said: {transcript}")
                    
            except Exception as e:
                self.logger.error(f"❌ Error handling outbound audio for {session_id}: {e}")
                break

    async def _handle_twilio_messages(self, session_id: str, websocket: WebSocket):
        """Handle non-audio messages from Twilio Media Streams."""
        self.logger.info(f"📡 Starting Twilio message handler for session {session_id}")
        
        while self.sessions.get(session_id, {}).get('status') != 'ended':
            try:
                message = await websocket.receive_text()
                data = json.loads(message)
                
                event = data.get('event')
                
                if event == 'stop':
                    # Stream stopped
                    self.logger.info(f"🛑 Stream stopped for session {session_id}")
                    self.sessions[session_id]['status'] = 'ended'
                    break
                    
                elif event == 'mark':
                    # Mark event (optional handling)
                    mark_name = data.get('mark', {}).get('name')
                    self.logger.debug(f"📍 Mark received for session {session_id}: {mark_name}")
                    
            except WebSocketDisconnect:
                break
            except Exception as e:
                self.logger.error(f"❌ Error handling Twilio messages for {session_id}: {e}")
                break

    async def _cleanup_session(self, session_id: str):
        """Cleanup session resources."""
        self.logger.info(f"🧹 Cleaning up session {session_id}")
        
        try:
            # Disconnect from OpenAI Realtime API
            if self.sessions.get(session_id, {}).get('realtime_connected'):
                await self.realtime_service.disconnect()
            
            # Remove session data
            self.sessions.pop(session_id, None)
            self.audio_buffers.pop(session_id, None)
            self.session_configs.pop(session_id, None)
            self.active_connections.pop(session_id, None)
            
        except Exception as e:
            self.logger.error(f"❌ Error during session cleanup for {session_id}: {e}")

# Global WebSocket handler instance
websocket_handler = WebSocketHandler() 