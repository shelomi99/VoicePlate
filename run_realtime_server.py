#!/usr/bin/env python3
"""
Realtime Server Runner
Runs the VoicePlate servers optimized for OpenAI Realtime API.
"""

import os
import sys
import asyncio
import logging
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
import signal
import time

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config.settings import settings

def setup_logging():
    """Setup logging configuration."""
    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

def run_realtime_webhook():
    """Run the Realtime Twilio webhook server."""
    try:
        setup_logging()
        logger = logging.getLogger("realtime_webhook")
        logger.info(f"🚀 Starting Realtime Webhook server on {settings.host}:{settings.port}")
        
        # Import and run realtime webhook
        from src.twilio_webhook_realtime import app
        app.run(
            host=settings.host,
            port=settings.port,
            debug=False,
            use_reloader=False
        )
        
    except Exception as e:
        logger.error(f"❌ Realtime webhook server error: {e}")
        raise

def run_fastapi_websocket():
    """Run the FastAPI WebSocket server."""
    try:
        setup_logging()
        logger = logging.getLogger("fastapi_websocket")
        
        # Use a different port for WebSocket server
        websocket_port = settings.port + 1000
        logger.info(f"🚀 Starting FastAPI WebSocket server on {settings.host}:{websocket_port}")
        
        # Import and run FastAPI app with uvicorn
        import uvicorn
        uvicorn.run(
            "src.realtime_app:app",
            host=settings.host,
            port=websocket_port,
            log_level=settings.log_level.lower(),
            reload=False,
            access_log=True
        )
        
    except Exception as e:
        logger.error(f"❌ FastAPI WebSocket server error: {e}")
        raise

class RealtimeServerManager:
    """Manages the realtime server setup."""
    
    def __init__(self):
        self.setup_logging()
        self.logger = logging.getLogger(__name__)
        self.running = False
        
    def setup_logging(self):
        """Setup logging configuration."""
        logging.basicConfig(
            level=getattr(logging, settings.log_level),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        self.logger.info(f"🛑 Received signal {signum}, shutting down servers...")
        self.stop_servers()
        sys.exit(0)
    
    def start_servers(self):
        """Start both webhook and WebSocket servers."""
        self.logger.info("🚀 Starting VoicePlate Realtime Server Setup")
        self.logger.info("=" * 70)
        self.logger.info(f"📞 Realtime Webhook: http://{settings.host}:{settings.port}/voice")
        self.logger.info(f"🎧 WebSocket Server: ws://{settings.host}:{settings.port + 1000}/ws/media")
        self.logger.info(f"🔧 Webhook Health: http://{settings.host}:{settings.port}/health")
        self.logger.info(f"🔧 WebSocket Health: http://{settings.host}:{settings.port + 1000}/health")
        self.logger.info("=" * 70)
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        self.running = True
        
        try:
            with ProcessPoolExecutor(max_workers=2) as executor:
                # Start Realtime Webhook server
                webhook_future = executor.submit(run_realtime_webhook)
                self.logger.info("✅ Realtime webhook server process started")
                
                # Start FastAPI WebSocket server
                websocket_future = executor.submit(run_fastapi_websocket)
                self.logger.info("✅ FastAPI WebSocket server process started")
                
                # Monitor both servers
                self.logger.info("👀 Monitoring realtime servers...")
                self.logger.info("💡 Press Ctrl+C to stop both servers")
                
                # Wait for completion or error
                try:
                    while self.running:
                        if webhook_future.done():
                            if webhook_future.exception():
                                self.logger.error(f"❌ Webhook server failed: {webhook_future.exception()}")
                                break
                        
                        if websocket_future.done():
                            if websocket_future.exception():
                                self.logger.error(f"❌ WebSocket server failed: {websocket_future.exception()}")
                                break
                        
                        time.sleep(1)
                        
                except KeyboardInterrupt:
                    self.logger.info("🛑 Keyboard interrupt received")
                
                finally:
                    # Cleanup
                    self.logger.info("🧹 Cleaning up processes...")
                    if not webhook_future.done():
                        webhook_future.cancel()
                    if not websocket_future.done():
                        websocket_future.cancel()
                        
        except Exception as e:
            self.logger.error(f"❌ Error managing servers: {e}")
        finally:
            self.running = False
            self.logger.info("✅ Realtime server shutdown complete")
    
    def stop_servers(self):
        """Stop both servers."""
        self.running = False
        self.logger.info("🛑 Stopping realtime servers...")

def print_realtime_setup_info():
    """Print realtime setup information and instructions."""
    print("\n" + "=" * 80)
    print("🎉 VoicePlate Realtime Server Setup")
    print("=" * 80)
    print("\n📋 Server Information:")
    print(f"   📞 Realtime Webhook: http://{settings.host}:{settings.port}/voice")
    print(f"      └── Connects calls to Media Streams automatically")
    print(f"      └── Health Check: http://{settings.host}:{settings.port}/health")
    print(f"   🎧 WebSocket Server: ws://{settings.host}:{settings.port + 1000}/ws/media")
    print(f"      └── Handles real-time audio streaming")
    print(f"      └── Health Check: http://{settings.host}:{settings.port + 1000}/health")
    print(f"      └── API Docs: http://{settings.host}:{settings.port + 1000}/docs")
    
    print("\n🔧 Configuration:")
    print(f"   • Realtime API Enabled: {settings.use_realtime_api}")
    print(f"   • Fallback Enabled: {settings.enable_realtime_fallback}")
    print(f"   • OpenAI Model: {settings.openai_realtime_model}")
    print(f"   • Voice: {settings.realtime_voice}")
    print(f"   • Audio Format: {settings.realtime_input_audio_format}")
    
    print("\n🌐 Twilio Configuration Required:")
    print("   1. Update Twilio webhook URL:")
    print(f"      • Webhook URL: http://your-ngrok-url.ngrok.io/voice")
    print("   2. The webhook will automatically connect to Media Streams")
    print("   3. No additional Twilio configuration needed!")
    
    print("\n🚀 Next Steps:")
    print("   1. Expose webhook with: ngrok http 5001")
    print("   2. Update Twilio webhook URL to use ngrok URL")
    print("   3. Make a test call to your Twilio number")
    print("   4. Monitor logs for real-time processing")
    
    print("\n💡 How It Works:")
    print("   • Incoming call → Realtime webhook (port 5001)")
    print("   • Webhook connects call to Media Streams")
    print("   • Media Streams → WebSocket server (port 6001)")
    print("   • WebSocket → OpenAI Realtime API")
    print("   • Real-time conversation with ~500ms latency!")
    
    print("\n🛑 To stop: Press Ctrl+C")
    print("=" * 80 + "\n")

def main():
    """Main entry point."""
    print_realtime_setup_info()
    
    # Validate configuration
    if not settings.openai_api_key:
        print("❌ Error: OPENAI_API_KEY not configured")
        sys.exit(1)
    
    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        print("❌ Error: Twilio credentials not configured")
        sys.exit(1)
    
    if not settings.base_webhook_url:
        print("⚠️  Warning: BASE_WEBHOOK_URL not configured")
        print("💡 You'll need to set this when using ngrok")
    
    # Start realtime server setup
    manager = RealtimeServerManager()
    try:
        manager.start_servers()
    except KeyboardInterrupt:
        print("\n🛑 Received interrupt signal")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        sys.exit(1)
    finally:
        print("👋 Goodbye!")

if __name__ == "__main__":
    main() 