#!/usr/bin/env python3
"""
VoicePlate Unified Realtime Server Runner
Runs a single FastAPI server that handles both webhooks and WebSocket connections.
"""

import os
import sys
import logging
import signal
import uvicorn

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config.settings import settings

def setup_logging():
    """Setup logging configuration."""
    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

def print_unified_server_info():
    """Print unified server setup information."""
    print("\n" + "=" * 80)
    print("🎉 VoicePlate Unified Realtime Server")
    print("=" * 80)
    print("\n📋 Server Information:")
    print(f"   🚀 Single FastAPI Server: http://{settings.host}:{settings.port}")
    print(f"      ├── Webhook Endpoint: /voice")
    print(f"      ├── WebSocket Endpoint: /ws/media")
    print(f"      ├── Health Check: /health")
    print(f"      ├── Server Status: /status")
    print(f"      └── API Documentation: /docs")
    
    print("\n🏗️ Architecture:")
    print("   • Unified FastAPI application (no Flask dependency)")
    print("   • Single server handles both webhooks and WebSocket")
    print("   • Simplified deployment and management")
    print("   • Real-time OpenAI Realtime API integration")
    
    print("\n🔧 Configuration:")
    print(f"   • Realtime API Enabled: {settings.use_realtime_api}")
    print(f"   • OpenAI Model: {settings.openai_realtime_model}")
    print(f"   • Voice: {settings.realtime_voice}")
    print(f"   • Audio Format: {settings.realtime_input_audio_format}")
    print(f"   • Turn Detection: {settings.realtime_turn_detection}")
    
    print("\n🌐 Twilio Configuration:")
    print("   1. Update Twilio webhook URL:")
    print(f"      • Webhook URL: http://your-ngrok-url.ngrok.io/voice")
    print("   2. The webhook automatically connects to WebSocket on the same server")
    print("   3. No additional configuration needed!")
    
    print("\n🚀 Deployment Steps:")
    print("   1. Start unified server: python run_unified_server.py")
    print("   2. Expose with ngrok: ngrok http 5001")
    print("   3. Update Twilio webhook URL")
    print("   4. Make a test call!")
    
    print("\n✨ Key Benefits:")
    print("   • 80% latency reduction (3s → 500ms)")
    print("   • Natural conversation with interruptions")
    print("   • Single server (simplified architecture)")
    print("   • No Flask dependency")
    print("   • Easy deployment and management")
    
    print("\n🛑 To stop: Press Ctrl+C")
    print("=" * 80 + "\n")

def validate_configuration():
    """Validate configuration before starting."""
    errors = []
    
    if not settings.openai_api_key:
        errors.append("OPENAI_API_KEY not configured")
    
    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        errors.append("Twilio credentials (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN) not configured")
    
    if not settings.use_realtime_api:
        print("⚠️  Warning: USE_REALTIME_API is disabled")
    
    if not getattr(settings, 'base_webhook_url', None):
        print("⚠️  Warning: BASE_WEBHOOK_URL not configured (you'll need to set this with ngrok)")
    
    if errors:
        print("❌ Configuration Errors:")
        for error in errors:
            print(f"   • {error}")
        return False
    
    return True

def signal_handler(signum, frame):
    """Handle shutdown signals."""
    logger = logging.getLogger(__name__)
    logger.info(f"🛑 Received signal {signum}, shutting down...")
    sys.exit(0)

def main():
    """Main entry point for the unified server."""
    setup_logging()
    logger = logging.getLogger(__name__)
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Print server information
    print_unified_server_info()
    
    # Validate configuration
    if not validate_configuration():
        sys.exit(1)
    
    try:
        logger.info("🚀 Starting VoicePlate Unified Realtime Server")
        
        # Start the unified FastAPI server
        uvicorn.run(
            "src.realtime_app_unified:app",
            host=settings.host,
            port=settings.port,
            log_level=settings.log_level.lower(),
            reload=False,
            access_log=True
        )
        
    except KeyboardInterrupt:
        logger.info("\n🛑 Received keyboard interrupt")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        sys.exit(1)
    finally:
        logger.info("👋 Server shutdown complete")

if __name__ == "__main__":
    main() 