#!/usr/bin/env python3
"""
WebSocket Test Script
Tests the WebSocket handler functionality and OpenAI Realtime API integration.
"""

import asyncio
import json
import logging
import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.services.realtime_service import realtime_service
from src.services.websocket_handler import websocket_handler
from config.settings import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

async def test_realtime_service():
    """Test the OpenAI Realtime service."""
    logger.info("🧪 Testing OpenAI Realtime Service...")
    
    try:
        # Test health check
        health = await realtime_service.health_check()
        logger.info(f"✅ Realtime service health: {health}")
        
        # Test session creation
        session_id = "test_session_001"
        session = await realtime_service.create_session(session_id)
        logger.info(f"✅ Created session: {session.session_id}")
        
        # Test connection to OpenAI (if API key is available)
        if settings.openai_api_key:
            connected = await realtime_service.connect_to_openai(session_id)
            if connected:
                logger.info("✅ Connected to OpenAI Realtime API")
                
                # Get session info
                info = await realtime_service.get_session_info(session_id)
                logger.info(f"📊 Session info: {info}")
                
                # Close session
                await realtime_service.close_session(session_id)
                logger.info("✅ Session closed successfully")
            else:
                logger.warning("⚠️ Failed to connect to OpenAI (check API key and access)")
        else:
            logger.warning("⚠️ No OpenAI API key configured, skipping connection test")
            
    except Exception as e:
        logger.error(f"❌ Realtime service test failed: {e}")
        return False
    
    return True

async def test_websocket_handler():
    """Test the WebSocket handler."""
    logger.info("🧪 Testing WebSocket Handler...")
    
    try:
        # Test health check
        health = await websocket_handler.health_check()
        logger.info(f"✅ WebSocket handler health: {health}")
        
        # Test stream information
        streams = websocket_handler.get_active_streams()
        logger.info(f"📊 Active streams: {len(streams)}")
        
        calls = websocket_handler.get_call_sessions()
        logger.info(f"📊 Active calls: {len(calls)}")
        
    except Exception as e:
        logger.error(f"❌ WebSocket handler test failed: {e}")
        return False
    
    return True

async def test_simulated_twilio_event():
    """Test simulated Twilio Media Stream events."""
    logger.info("🧪 Testing Simulated Twilio Events...")
    
    try:
        # Create a mock WebSocket connection
        class MockWebSocket:
            def __init__(self):
                self.closed = False
                self.messages = []
            
            async def send(self, message):
                self.messages.append(message)
                logger.debug(f"📤 Mock WebSocket sent: {json.loads(message)}")
            
            async def close(self, code=None, reason=None):
                self.closed = True
                logger.debug(f"🔌 Mock WebSocket closed: {code} - {reason}")
        
        mock_ws = MockWebSocket()
        
        # Simulate stream start event
        start_event = {
            "event": "start",
            "streamSid": "test_stream_123",
            "start": {
                "callSid": "test_call_456",
                "tracks": ["inbound"],
                "mediaFormat": {
                    "encoding": "audio/x-mulaw",
                    "sampleRate": 8000,
                    "channels": 1
                }
            }
        }
        
        # Process start event
        await websocket_handler._handle_stream_start(mock_ws, start_event)
        logger.info("✅ Processed stream start event")
        
        # Check if stream was created
        streams = websocket_handler.get_active_streams()
        if "test_stream_123" in streams:
            logger.info("✅ Stream created successfully")
            
            # Simulate media data
            media_event = {
                "event": "media",
                "streamSid": "test_stream_123",
                "media": {
                    "track": "inbound",
                    "chunk": "1",
                    "timestamp": "1234567890",
                    "payload": "dGVzdCBhdWRpbyBkYXRh"  # base64 "test audio data"
                }
            }
            
            await websocket_handler._handle_media_data(media_event)
            logger.info("✅ Processed media data event")
            
            # Simulate stop event
            stop_event = {
                "event": "stop",
                "streamSid": "test_stream_123"
            }
            
            await websocket_handler._handle_stream_stop(stop_event)
            logger.info("✅ Processed stream stop event")
            
            # Cleanup
            await websocket_handler._cleanup_stream("test_stream_123")
            logger.info("✅ Cleaned up test stream")
            
        else:
            logger.error("❌ Failed to create stream")
            return False
            
    except Exception as e:
        logger.error(f"❌ Simulated Twilio event test failed: {e}")
        return False
    
    return True

async def test_configuration():
    """Test configuration and environment setup."""
    logger.info("🧪 Testing Configuration...")
    
    # Check required environment variables
    required_vars = [
        "OPENAI_API_KEY",
        "TWILIO_ACCOUNT_SID",
        "TWILIO_AUTH_TOKEN"
    ]
    
    missing_vars = []
    for var in required_vars:
        if not getattr(settings, var.lower(), None):
            missing_vars.append(var)
    
    if missing_vars:
        logger.warning(f"⚠️ Missing environment variables: {missing_vars}")
        logger.info("💡 Some tests may be skipped due to missing configuration")
    else:
        logger.info("✅ All required environment variables configured")
    
    # Check feature flags
    logger.info(f"🚀 Realtime API enabled: {settings.use_realtime_api}")
    logger.info(f"🔄 Fallback enabled: {settings.enable_realtime_fallback}")
    logger.info(f"🎙️ Audio format: {settings.realtime_input_audio_format}")
    logger.info(f"🎭 Voice: {settings.realtime_voice}")
    
    return True

async def run_all_tests():
    """Run all test suites."""
    logger.info("🚀 Starting VoicePlate WebSocket Tests...")
    logger.info("=" * 60)
    
    # Test results
    results = {}
    
    # Configuration test
    results['configuration'] = await test_configuration()
    
    # Realtime service test
    results['realtime_service'] = await test_realtime_service()
    
    # WebSocket handler test
    results['websocket_handler'] = await test_websocket_handler()
    
    # Simulated events test
    results['simulated_events'] = await test_simulated_twilio_event()
    
    # Print results
    logger.info("=" * 60)
    logger.info("📊 Test Results Summary:")
    
    all_passed = True
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        logger.info(f"   {test_name:20}: {status}")
        if not passed:
            all_passed = False
    
    logger.info("=" * 60)
    
    if all_passed:
        logger.info("🎉 All tests passed! WebSocket integration is ready.")
        logger.info("💡 Next steps:")
        logger.info("   1. Run 'python run_dual_server.py' to start servers")
        logger.info("   2. Configure Twilio webhook to use WebSocket endpoint")
        logger.info("   3. Test with real phone calls")
    else:
        logger.error("❌ Some tests failed. Please check configuration and logs.")
        return 1
    
    return 0

def main():
    """Main entry point."""
    try:
        exit_code = asyncio.run(run_all_tests())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("🛑 Tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Test execution failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 