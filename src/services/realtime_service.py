"""
OpenAI Realtime Service Module
Handles real-time WebSocket connections, audio streaming, and conversation management
for OpenAI's Realtime API integration.
"""

import os
import json
import base64
import asyncio
import logging
from typing import Dict, List, Optional, Callable, Any, AsyncIterator
from dataclasses import dataclass, field
from enum import Enum
import websockets
from websockets.exceptions import WebSocketException, ConnectionClosed
from config.settings import settings

class ConnectionState(Enum):
    """WebSocket connection states"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    FAILED = "failed"

class AudioFormat(Enum):
    """Supported audio formats for Realtime API"""
    PCM16 = "pcm16"  # 24kHz PCM
    G711_ULAW = "g711_ulaw"  # 8kHz μ-law (Twilio compatible)
    G711_ALAW = "g711_alaw"  # 8kHz A-law

@dataclass
class RealtimeConfig:
    """Configuration for OpenAI Realtime API session"""
    model: str = "gpt-4o-realtime-preview-2024-10-01"
    voice: str = "alloy"
    input_audio_format: AudioFormat = AudioFormat.G711_ULAW
    output_audio_format: AudioFormat = AudioFormat.G711_ULAW
    turn_detection: Dict[str, Any] = field(default_factory=lambda: {"type": "server_vad"})
    temperature: float = 0.8
    max_tokens: Optional[int] = None
    system_message: str = ""
    modalities: List[str] = field(default_factory=lambda: ["text", "audio"])
    tools: List[Dict[str, Any]] = field(default_factory=list)

@dataclass
class StreamingSession:
    """Manages state for a single streaming session"""
    session_id: str
    connection_id: str
    config: RealtimeConfig
    websocket: Optional[websockets.WebSocketServerProtocol] = None
    openai_ws: Optional[websockets.WebSocketClientProtocol] = None
    state: ConnectionState = ConnectionState.DISCONNECTED
    conversation_items: List[Dict[str, Any]] = field(default_factory=list)
    last_assistant_item_id: Optional[str] = None
    audio_buffer: bytes = b""
    metadata: Dict[str, Any] = field(default_factory=dict)

class RealtimeService:
    """Service class for OpenAI Realtime API WebSocket connections."""
    
    def __init__(self):
        """Initialize the Realtime service."""
        self.logger = logging.getLogger(__name__)
        self.api_key = settings.openai_api_key
        self.base_url = "wss://api.openai.com/v1/realtime"
        self.sessions: Dict[str, StreamingSession] = {}
        self.event_handlers: Dict[str, List[Callable]] = {}
        
        # Connection settings
        self.max_reconnect_attempts = 3
        self.reconnect_delay = 2.0
        self.connection_timeout = 30.0
        
        # Default configuration
        self.default_config = RealtimeConfig(
            system_message="""You are VoicePlate, a helpful and professional AI call answering assistant for Applova - a smart restaurant and retail tech company.

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
        )
        
        self.logger.info("🔄 Realtime service initialized")

    async def create_session(self, session_id: str, config: Optional[RealtimeConfig] = None) -> StreamingSession:
        """
        Create a new streaming session.
        
        Args:
            session_id: Unique identifier for the session
            config: Optional configuration, uses default if not provided
            
        Returns:
            StreamingSession object
        """
        if session_id in self.sessions:
            self.logger.warning(f"⚠️ Session {session_id} already exists, removing old session")
            await self.close_session(session_id)
        
        session_config = config or self.default_config
        connection_id = f"conn_{session_id}_{asyncio.get_event_loop().time()}"
        
        session = StreamingSession(
            session_id=session_id,
            connection_id=connection_id,
            config=session_config
        )
        
        self.sessions[session_id] = session
        self.logger.info(f"✅ Created session {session_id} with connection {connection_id}")
        
        return session

    async def connect_to_openai(self, session_id: str) -> bool:
        """
        Establish WebSocket connection to OpenAI Realtime API.
        
        Args:
            session_id: Session identifier
            
        Returns:
            True if connection successful, False otherwise
        """
        if session_id not in self.sessions:
            self.logger.error(f"❌ Session {session_id} not found")
            return False
        
        session = self.sessions[session_id]
        session.state = ConnectionState.CONNECTING
        
        try:
            # Build WebSocket URL with model parameter
            url = f"{self.base_url}?model={session.config.model}"
            
            # Headers for authentication
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "OpenAI-Beta": "realtime=v1"
            }
            
            self.logger.info(f"🔗 Connecting to OpenAI Realtime API: {url}")
            
            # Establish WebSocket connection
            session.openai_ws = await websockets.connect(
                url,
                extra_headers=headers,
                timeout=self.connection_timeout,
                ping_interval=20,
                ping_timeout=10
            )
            
            session.state = ConnectionState.CONNECTED
            self.logger.info(f"✅ Connected to OpenAI for session {session_id}")
            
            # Send initial session configuration
            await self._send_session_update(session)
            
            return True
            
        except WebSocketException as e:
            self.logger.error(f"❌ WebSocket connection failed for session {session_id}: {e}")
            session.state = ConnectionState.FAILED
            return False
        except Exception as e:
            self.logger.error(f"❌ Unexpected error connecting session {session_id}: {e}")
            session.state = ConnectionState.FAILED
            return False

    async def _send_session_update(self, session: StreamingSession):
        """Send session configuration to OpenAI."""
        if not session.openai_ws:
            return
        
        # Build session update payload
        session_update = {
            "type": "session.update",
            "session": {
                "modalities": session.config.modalities,
                "instructions": session.config.system_message,
                "voice": session.config.voice,
                "input_audio_format": session.config.input_audio_format.value,
                "output_audio_format": session.config.output_audio_format.value,
                "turn_detection": session.config.turn_detection,
                "temperature": session.config.temperature,
                "tools": session.config.tools
            }
        }
        
        if session.config.max_tokens:
            session_update["session"]["max_response_output_tokens"] = session.config.max_tokens
        
        try:
            await session.openai_ws.send(json.dumps(session_update))
            self.logger.info(f"📤 Sent session update for {session.session_id}")
        except Exception as e:
            self.logger.error(f"❌ Failed to send session update: {e}")

    async def stream_audio_to_openai(self, session_id: str, audio_data: str) -> bool:
        """
        Stream audio data to OpenAI Realtime API.
        
        Args:
            session_id: Session identifier
            audio_data: Base64 encoded audio data
            
        Returns:
            True if successful, False otherwise
        """
        if session_id not in self.sessions:
            self.logger.error(f"❌ Session {session_id} not found")
            return False
        
        session = self.sessions[session_id]
        
        if not session.openai_ws or session.state != ConnectionState.CONNECTED:
            self.logger.error(f"❌ OpenAI connection not ready for session {session_id}")
            return False
        
        try:
            # Send audio buffer append event
            audio_append = {
                "type": "input_audio_buffer.append",
                "audio": audio_data
            }
            
            await session.openai_ws.send(json.dumps(audio_append))
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to stream audio for session {session_id}: {e}")
            return False

    async def commit_audio_buffer(self, session_id: str) -> bool:
        """
        Commit the audio buffer to trigger response generation.
        
        Args:
            session_id: Session identifier
            
        Returns:
            True if successful, False otherwise
        """
        if session_id not in self.sessions:
            return False
        
        session = self.sessions[session_id]
        
        if not session.openai_ws or session.state != ConnectionState.CONNECTED:
            return False
        
        try:
            commit_event = {
                "type": "input_audio_buffer.commit"
            }
            
            await session.openai_ws.send(json.dumps(commit_event))
            self.logger.info(f"📤 Committed audio buffer for session {session_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to commit audio buffer: {e}")
            return False

    async def create_response(self, session_id: str, instructions: Optional[str] = None) -> bool:
        """
        Request response generation from OpenAI.
        
        Args:
            session_id: Session identifier
            instructions: Optional response-specific instructions
            
        Returns:
            True if successful, False otherwise
        """
        if session_id not in self.sessions:
            return False
        
        session = self.sessions[session_id]
        
        if not session.openai_ws or session.state != ConnectionState.CONNECTED:
            return False
        
        try:
            response_event = {
                "type": "response.create"
            }
            
            if instructions:
                response_event["response"] = {
                    "instructions": instructions
                }
            
            await session.openai_ws.send(json.dumps(response_event))
            self.logger.info(f"📤 Requested response for session {session_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to create response: {e}")
            return False

    async def handle_interruption(self, session_id: str, truncate_item_id: Optional[str] = None, audio_end_ms: Optional[int] = None) -> bool:
        """
        Handle conversation interruption by truncating current response.
        
        Args:
            session_id: Session identifier
            truncate_item_id: ID of item to truncate
            audio_end_ms: Timestamp where to truncate audio
            
        Returns:
            True if successful, False otherwise
        """
        if session_id not in self.sessions:
            return False
        
        session = self.sessions[session_id]
        
        if not session.openai_ws or session.state != ConnectionState.CONNECTED:
            return False
        
        try:
            # Use last assistant item if not specified
            item_id = truncate_item_id or session.last_assistant_item_id
            
            if item_id:
                truncate_event = {
                    "type": "conversation.item.truncate",
                    "item_id": item_id,
                    "content_index": 0
                }
                
                if audio_end_ms is not None:
                    truncate_event["audio_end_ms"] = audio_end_ms
                
                await session.openai_ws.send(json.dumps(truncate_event))
                self.logger.info(f"🛑 Sent interruption for session {session_id}, item {item_id}")
                
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to handle interruption: {e}")
            return False

    async def listen_for_events(self, session_id: str, event_handler: Callable[[Dict[str, Any]], None]):
        """
        Listen for events from OpenAI WebSocket and handle them.
        
        Args:
            session_id: Session identifier
            event_handler: Function to handle incoming events
        """
        if session_id not in self.sessions:
            return
        
        session = self.sessions[session_id]
        
        if not session.openai_ws:
            return
        
        try:
            async for message in session.openai_ws:
                try:
                    event = json.loads(message)
                    await self._process_openai_event(session, event)
                    
                    # Call external event handler
                    if event_handler:
                        await asyncio.create_task(event_handler(event))
                        
                except json.JSONDecodeError as e:
                    self.logger.error(f"❌ Failed to parse OpenAI event: {e}")
                except Exception as e:
                    self.logger.error(f"❌ Error handling event: {e}")
                    
        except ConnectionClosed:
            self.logger.warning(f"⚠️ OpenAI connection closed for session {session_id}")
            session.state = ConnectionState.DISCONNECTED
        except Exception as e:
            self.logger.error(f"❌ Error in event listener: {e}")
            session.state = ConnectionState.FAILED

    async def _process_openai_event(self, session: StreamingSession, event: Dict[str, Any]):
        """Process incoming events from OpenAI and update session state."""
        event_type = event.get("type", "")
        
        # Update session state based on events
        if event_type == "session.created":
            self.logger.info(f"📱 OpenAI session created for {session.session_id}")
            
        elif event_type == "conversation.item.created":
            # Track conversation items
            item = event.get("item", {})
            session.conversation_items.append(item)
            
            # Track assistant items for interruption handling
            if item.get("role") == "assistant":
                session.last_assistant_item_id = item.get("id")
                
        elif event_type == "response.audio.delta":
            # Log audio streaming
            delta = event.get("delta", "")
            if delta:
                audio_bytes = base64.b64decode(delta)
                self.logger.debug(f"🎵 Received {len(audio_bytes)} bytes of audio for {session.session_id}")
                
        elif event_type == "input_audio_buffer.speech_started":
            self.logger.info(f"🎙️ Speech started in session {session.session_id}")
            
        elif event_type == "input_audio_buffer.speech_stopped":
            self.logger.info(f"🔇 Speech stopped in session {session.session_id}")
            
        elif event_type == "response.done":
            self.logger.info(f"✅ Response completed for session {session.session_id}")
            
        elif event_type == "error":
            error = event.get("error", {})
            self.logger.error(f"❌ OpenAI error in session {session.session_id}: {error}")

    async def get_menu_context(self, query: str) -> Optional[str]:
        """
        Get menu context for a query (integrates with existing menu service).
        
        Args:
            query: User's menu-related query
            
        Returns:
            Menu context string or None
        """
        try:
            # Import here to avoid circular imports
            from src.services.api_menu_service import api_menu_service
            
            if api_menu_service.is_menu_related_query(query):
                return await api_menu_service.process_menu_query(query)
                
        except Exception as e:
            self.logger.warning(f"⚠️ Could not load API menu service: {e}")
            # Fallback to static menu service
            try:
                from src.services.menu_service import menu_service
                if menu_service.is_menu_related_query(query):
                    return menu_service.process_menu_query(query)
            except Exception as fallback_e:
                self.logger.warning(f"⚠️ Could not load fallback menu service: {fallback_e}")
            
        return None

    async def get_business_context(self, query: str) -> Optional[str]:
        """
        Get business context for a query (integrates with business service).
        
        Args:
            query: User's business-related query
            
        Returns:
            Business context string or None
        """
        try:
            # Import here to avoid circular imports
            from src.services.api_business_service import api_business_service
            
            if api_business_service.is_business_related_query(query):
                return await api_business_service.process_business_query(query)
                
        except Exception as e:
            self.logger.warning(f"⚠️ Could not load API business service: {e}")
            
        return None

    async def close_session(self, session_id: str):
        """Close a streaming session and cleanup resources."""
        if session_id not in self.sessions:
            return
        
        session = self.sessions[session_id]
        
        # Close OpenAI WebSocket
        if session.openai_ws:
            try:
                await session.openai_ws.close()
                self.logger.info(f"🔌 Closed OpenAI connection for session {session_id}")
            except Exception as e:
                self.logger.warning(f"⚠️ Error closing OpenAI connection: {e}")
        
        # Update state and cleanup
        session.state = ConnectionState.DISCONNECTED
        session.openai_ws = None
        
        # Remove from sessions
        del self.sessions[session_id]
        self.logger.info(f"🗑️ Cleaned up session {session_id}")

    async def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get information about a session."""
        if session_id not in self.sessions:
            return None
        
        session = self.sessions[session_id]
        
        return {
            "session_id": session.session_id,
            "connection_id": session.connection_id,
            "state": session.state.value,
            "conversation_items": len(session.conversation_items),
            "last_assistant_item": session.last_assistant_item_id,
            "config": {
                "model": session.config.model,
                "voice": session.config.voice,
                "audio_format": session.config.input_audio_format.value
            }
        }

    def get_all_sessions(self) -> List[str]:
        """Get list of all active session IDs."""
        return list(self.sessions.keys())

    async def health_check(self) -> Dict[str, Any]:
        """Check service health and return status."""
        active_sessions = len(self.sessions)
        connected_sessions = sum(1 for s in self.sessions.values() 
                               if s.state == ConnectionState.CONNECTED)
        
        return {
            "service": "realtime",
            "status": "healthy",
            "active_sessions": active_sessions,
            "connected_sessions": connected_sessions,
            "api_key_configured": bool(self.api_key),
            "base_url": self.base_url
        }

    async def connect(self, session_id: Optional[str] = None, config: Optional[RealtimeConfig] = None) -> bool:
        """
        Convenience method to create a session and connect to OpenAI.
        
        Args:
            session_id: Optional session identifier, generates one if not provided
            config: Optional configuration, uses default if not provided
            
        Returns:
            True if connection successful, False otherwise
        """
        if not session_id:
            import time
            session_id = f"realtime_{int(time.time())}"
        
        # Create session
        await self.create_session(session_id, config)
        
        # Connect to OpenAI
        return await self.connect_to_openai(session_id)

    async def disconnect(self, session_id: Optional[str] = None):
        """
        Convenience method to disconnect and close session.
        
        Args:
            session_id: Optional session identifier, closes all if not provided
        """
        if session_id:
            await self.close_session(session_id)
        else:
            # Close all sessions
            for sid in list(self.sessions.keys()):
                await self.close_session(sid)

    async def send_message(self, message: Dict[str, Any], session_id: Optional[str] = None):
        """
        Send a message to OpenAI Realtime API.
        
        Args:
            message: Message dictionary to send
            session_id: Optional session identifier, uses first session if not provided
        """
        session = None
        
        # Get session with better error handling
        if session_id:
            if session_id in self.sessions:
                session = self.sessions[session_id]
            else:
                self.logger.error(f"❌ Session {session_id} not found. Available sessions: {list(self.sessions.keys())}")
                return
        elif self.sessions:
            # Use first available session
            session = next(iter(self.sessions.values()))
            self.logger.debug(f"🔄 Using first available session: {session.session_id}")
        else:
            self.logger.error("❌ No active sessions for sending message")
            return
        
        # Check session state and connection
        if not session.openai_ws:
            self.logger.error(f"❌ No WebSocket connection for session {session.session_id}")
            return
            
        if session.state != ConnectionState.CONNECTED:
            self.logger.error(f"❌ Session {session.session_id} not connected (state: {session.state.value})")
            return
        
        try:
            message_str = json.dumps(message)
            await session.openai_ws.send(message_str)
            self.logger.debug(f"📤 Sent message to OpenAI session {session.session_id}: {message.get('type', 'unknown')}")
        except ConnectionClosed:
            self.logger.error(f"❌ OpenAI connection closed for session {session.session_id}")
            session.state = ConnectionState.DISCONNECTED
        except Exception as e:
            self.logger.error(f"❌ Error sending message to session {session.session_id}: {e}")

    async def receive_message(self, session_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Receive a message from OpenAI Realtime API.
        
        Args:
            session_id: Optional session identifier, uses first session if not provided
            
        Returns:
            Message dictionary or None if no message available
        """
        session = None
        
        # Get session with better error handling
        if session_id:
            if session_id in self.sessions:
                session = self.sessions[session_id]
            else:
                self.logger.error(f"❌ Session {session_id} not found for receiving. Available: {list(self.sessions.keys())}")
                return None
        elif self.sessions:
            # Use first available session
            session = next(iter(self.sessions.values()))
        else:
            return None
        
        # Check session state and connection
        if not session.openai_ws:
            return None
            
        if session.state != ConnectionState.CONNECTED:
            return None
        
        try:
            message_str = await session.openai_ws.recv()
            message = json.loads(message_str)
            self.logger.debug(f"📥 Received message from OpenAI session {session.session_id}: {message.get('type', 'unknown')}")
            return message
        except ConnectionClosed:
            self.logger.warning(f"⚠️ OpenAI connection closed for session {session.session_id}")
            session.state = ConnectionState.DISCONNECTED
            return None
        except Exception as e:
            self.logger.error(f"❌ Error receiving message from session {session.session_id}: {e}")
            return None

# Global realtime service instance
realtime_service = RealtimeService() 