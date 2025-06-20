#!/usr/bin/env python3
"""
Twilio Webhook for Realtime API Integration
Redirects incoming calls to use Media Streams with OpenAI Realtime API.
"""

import os
import sys
import logging
from flask import Flask, request, Response
from twilio.twiml.voice_response import VoiceResponse, Connect, Stream
from twilio.request_validator import RequestValidator

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import settings

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Create Flask app for webhook
app = Flask(__name__)

# Initialize Twilio Request Validator for security
validator = RequestValidator(settings.twilio_auth_token) if settings.twilio_auth_token else None

def validate_twilio_request():
    """Validate that the request is actually from Twilio."""
    if app.config.get('DEBUG') or not validator:
        # Skip validation in development mode
        return True
    
    url = request.url
    signature = request.headers.get('X-Twilio-Signature', '')
    
    return validator.validate(url, request.form, signature)

@app.route('/voice', methods=['POST'])
def handle_realtime_voice_call():
    """
    Handle incoming voice calls using Realtime API approach.
    This webhook immediately connects to Media Streams for real-time processing.
    """
    
    # Validate request is from Twilio
    if not validate_twilio_request():
        logger.warning("Invalid Twilio request received")
        return "Forbidden", 403
    
    # Get call information from Twilio
    call_sid = request.form.get('CallSid')
    from_number = request.form.get('From')
    to_number = request.form.get('To')
    call_status = request.form.get('CallStatus')
    
    logger.info(f"📞 Incoming realtime call: {call_sid} from {from_number} to {to_number} (Status: {call_status})")
    
    # Create TwiML response for realtime processing
    response = VoiceResponse()
    
    # Welcome message
    response.say(
        "Hi there! Thanks for calling Food Fusion. How can I assist you today? I can help you with the menu and answer any questions you have about our restaurant.",
        voice=getattr(settings, 'voice_type', 'alice'),
        language=getattr(settings, 'language', 'en-US')
    )
    
    # Connect to Media Streams for real-time processing
    connect = Connect()
    
    # Determine WebSocket URL
    if hasattr(settings, 'realtime_websocket_url') and settings.realtime_websocket_url:
        websocket_url = settings.realtime_websocket_url
    else:
        # Construct WebSocket URL from base webhook URL
        base_url = getattr(settings, 'base_webhook_url', 'wss://localhost:6001')
        # Convert HTTP to WebSocket protocol
        if base_url.startswith('https://'):
            websocket_url = base_url.replace('https://', 'wss://') + '/ws/media'
        elif base_url.startswith('http://'):
            websocket_url = base_url.replace('http://', 'ws://') + '/ws/media'
        else:
            websocket_url = f"wss://{base_url}/ws/media"
    
    # Create Media Stream
    stream = Stream(url=websocket_url)
    
    # Configure stream parameters
    stream.parameter(name='track', value='both_tracks')  # Both inbound and outbound audio
    stream.parameter(name='statusCallback', value=f"{getattr(settings, 'base_webhook_url', '')}/stream/status")
    
    connect.append(stream)
    response.append(connect)
    
    logger.info(f"✅ Connecting call {call_sid} to realtime WebSocket: {websocket_url}")
    
    return str(response), 200, {'Content-Type': 'text/xml'}

@app.route('/stream/status', methods=['POST'])
def handle_stream_status():
    """Handle Media Stream status callbacks from Twilio."""
    
    # Validate request is from Twilio
    if not validate_twilio_request():
        logger.warning("Invalid Twilio request received in stream status")
        return "Forbidden", 403
    
    # Get stream status information
    call_sid = request.form.get('CallSid')
    stream_sid = request.form.get('StreamSid')
    status = request.form.get('Status')
    
    logger.info(f"📊 Stream status for call {call_sid}, stream {stream_sid}: {status}")
    
    return "OK", 200

@app.route('/fallback', methods=['POST'])
def handle_fallback():
    """Fallback webhook for traditional API if realtime fails."""
    
    # Validate request is from Twilio
    if not validate_twilio_request():
        logger.warning("Invalid Twilio request received in fallback")
        return "Forbidden", 403
    
    call_sid = request.form.get('CallSid')
    logger.warning(f"⚠️ Using fallback for call {call_sid} - realtime connection failed")
    
    # Create traditional TwiML response
    response = VoiceResponse()
    response.say(
        "I'm sorry, our advanced AI assistant is temporarily unavailable. Please try calling back in a moment.",
        voice='alice'
    )
    response.hangup()
    
    return str(response), 200, {'Content-Type': 'text/xml'}

@app.route('/health')
def health_check():
    """Health check endpoint for the Twilio webhook service."""
    return {
        'status': 'healthy',
        'service': 'VoicePlate Realtime Webhook',
        'realtime_enabled': settings.use_realtime_api,
        'fallback_enabled': settings.enable_realtime_fallback,
        'websocket_url': getattr(settings, 'realtime_websocket_url', 'not_configured')
    }, 200

@app.route('/')
def root():
    """Root endpoint with service information."""
    return {
        'service': 'VoicePlate Realtime Webhook',
        'version': '1.0.0',
        'description': 'Twilio webhook that connects calls to OpenAI Realtime API via Media Streams',
        'endpoints': {
            'voice': '/voice',
            'stream_status': '/stream/status',
            'fallback': '/fallback',
            'health': '/health'
        },
        'configuration': {
            'realtime_enabled': settings.use_realtime_api,
            'fallback_enabled': settings.enable_realtime_fallback,
            'websocket_url': getattr(settings, 'realtime_websocket_url', 'not_configured')
        }
    }, 200

if __name__ == '__main__':
    logger.info("🚀 Starting VoicePlate Realtime Webhook Service")
    logger.info(f"📞 Webhook endpoint: http://{settings.host}:{settings.port}/voice")
    logger.info(f"🎧 WebSocket target: {getattr(settings, 'realtime_websocket_url', 'not_configured')}")
    logger.info(f"🔧 Health check: http://{settings.host}:{settings.port}/health")
    
    app.run(
        host=settings.host,
        port=settings.port,
        debug=settings.flask_debug
    ) 