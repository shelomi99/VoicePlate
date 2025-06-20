#!/usr/bin/env python3
"""
VoicePlate Call Answering Agent - Main Flask Application
Handles incoming Twilio webhooks and processes voice calls with OpenAI.
"""

import os
import sys
import logging
from datetime import datetime
from flask import Flask, request, jsonify, url_for
from flask_cors import CORS
from dotenv import load_dotenv
from twilio.twiml.voice_response import VoiceResponse, Record, Gather
from twilio.request_validator import RequestValidator

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables
load_dotenv()

# Import our configuration and services
try:
    from config.settings import settings
    from src.services.openai_service import openai_service
except ImportError as e:
    print(f"Import error: {e}")
    # Create minimal settings for testing
    class MinimalSettings:
        flask_debug = True
        log_level = "INFO"
        host = "0.0.0.0"
        port = int(os.getenv("PORT", 5001))
        twilio_account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
        twilio_auth_token = os.getenv("TWILIO_AUTH_TOKEN", "")
        twilio_phone_number = os.getenv("TWILIO_PHONE_NUMBER", "")
        openai_model = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
        greeting_message = os.getenv("GREETING_MESSAGE", "Hi there! Thanks for calling Food Fusion. How can I assist you today? I can help you with the menu and answer any questions you have about our restaurant.")
        voice_type = os.getenv("VOICE_TYPE", "alice")
        language = os.getenv("LANGUAGE", "en-US")
    
    settings = MinimalSettings()
    openai_service = None

def create_app():
    """Create and configure Flask application."""
    
    app = Flask(__name__)
    
    # Configure Flask
    app.config['SECRET_KEY'] = os.urandom(24)
    app.config['DEBUG'] = settings.flask_debug
    
    # Enable CORS for development
    CORS(app)
    
    # Set up basic logging
    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    logger = logging.getLogger(__name__)
    logger.info("🚀 VoicePlate Call Answering Agent starting up...")
    
    return app

# Create Flask app
app = create_app()

# Initialize Twilio Request Validator for security
validator = RequestValidator(settings.twilio_auth_token) if settings.twilio_auth_token else None

# In-memory session storage (without Redis)
call_sessions = {}

def validate_twilio_request():
    """Validate that the request is actually from Twilio."""
    if app.config['DEBUG'] or not validator:
        # Skip validation in development mode
        return True
    
    url = request.url
    signature = request.headers.get('X-Twilio-Signature', '')
    
    return validator.validate(url, request.form, signature)

def get_or_create_session(call_sid: str) -> dict:
    """Get or create a session for the call."""
    if call_sid not in call_sessions:
        call_sessions[call_sid] = {
            'conversation_history': [],
            'start_time': datetime.utcnow().isoformat(),
            'turn_count': 0
        }
    return call_sessions[call_sid]

def cleanup_session(call_sid: str):
    """Clean up session data when call ends."""
    if call_sid in call_sessions:
        del call_sessions[call_sid]
        logging.getLogger(__name__).info(f"🧹 Cleaned up session for call {call_sid}")

@app.route('/')
def home():
    """Health check and welcome endpoint."""
    return jsonify({
        'status': 'healthy',
        'service': 'VoicePlate Call Answering Agent',
        'version': '1.0.0',
        'capabilities': ['voice_calls', 'ai_conversations', 'speech_to_text', 'text_to_speech'],
        'endpoints': {
            'voice_webhook': '/voice',
            'recording_handler': '/handle_recording',
            'health': '/health',
            'status': '/status',
            'test': '/test'
        }
    })

@app.route('/test')
def test_endpoint():
    """Simple test endpoint to verify the app is working."""
    return jsonify({
        'message': '✅ VoicePlate is working perfectly!',
        'timestamp': datetime.utcnow().isoformat(),
        'test_status': 'success',
        'server_info': {
            'host': settings.host,
            'port': settings.port,
            'debug': app.config['DEBUG']
        }
    })

@app.route('/ping')
def ping():
    """Simple ping endpoint that returns plain text."""
    return "VoicePlate is alive and working! 🚀✅", 200, {'Content-Type': 'text/plain'}

@app.route('/hello')
def hello():
    """Simple hello endpoint for easy testing."""
    return f"Hello from VoicePlate! Server running on port {settings.port} at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC", 200, {'Content-Type': 'text/plain'}

@app.route('/health')
def health_check():
    """Health check endpoint for monitoring."""
    return jsonify({
        'status': 'healthy',
        'timestamp': str(datetime.utcnow()),
        'services': {
            'flask': 'running',
            'twilio': 'configured' if settings.twilio_auth_token else 'not_configured',
            'openai': 'configured' if openai_service else 'not_configured'
        },
        'active_sessions': len(call_sessions)
    }), 200

@app.route('/voice', methods=['POST'])
def handle_voice_call():
    """
    Handle incoming voice calls from Twilio.
    This is the main webhook endpoint that Twilio calls when someone dials our number.
    """
    
    logger = logging.getLogger(__name__)
    
    # Validate request is from Twilio
    if not validate_twilio_request():
        logger.warning("Invalid Twilio request received")
        return "Forbidden", 403
    
    # Get call information from Twilio
    call_sid = request.form.get('CallSid')
    from_number = request.form.get('From')
    to_number = request.form.get('To')
    call_status = request.form.get('CallStatus')
    
    logger.info(f"📞 Incoming call: {call_sid} from {from_number} to {to_number} (Status: {call_status})")
    
    # Get or create session
    session = get_or_create_session(call_sid)
    
    # Create TwiML response
    response = VoiceResponse()
    
    # Welcome message for new calls
    if session['turn_count'] == 0:
        response.say(
            settings.greeting_message,
            voice=getattr(settings, 'voice_type', 'alice'),
            language=getattr(settings, 'language', 'en-US')
        )
        session['turn_count'] += 1
    
    # Record the caller's response
    response.record(
        max_length=30,  # Maximum 30 seconds
        play_beep=True,
        action=url_for('handle_recording', _external=True),
        method='POST',
        timeout=10,  # Stop recording after 10 seconds of silence
        transcribe=False  # We'll use OpenAI Whisper instead
    )
    
    # Fallback if recording fails
    response.say(
        "I didn't catch that. Please call back and try again.",
        voice='alice',
        language='en-US'
    )
    
    logger.info(f"✅ Call {call_sid} initial response sent")
    
    # Return TwiML response
    return str(response), 200, {'Content-Type': 'text/xml'}

@app.route('/handle_recording', methods=['GET', 'POST'])
def handle_recording():
    """
    Handle recorded audio from Twilio and process with OpenAI.
    """
    
    logger = logging.getLogger(__name__)
    
    # Validate request is from Twilio
    if not validate_twilio_request():
        logger.warning("Invalid Twilio request received in recording handler")
        return "Forbidden", 403
    
    # Get call and recording information - handle both GET and POST
    if request.method == 'POST':
        call_sid = request.form.get('CallSid')
        recording_url = request.form.get('RecordingUrl')
        recording_duration = request.form.get('RecordingDuration', '0')
    else:  # GET method
        call_sid = request.args.get('CallSid')
        recording_url = request.args.get('RecordingUrl')
        recording_duration = request.args.get('RecordingDuration', '0')
    
    logger.info(f"🎙️ Processing recording for call {call_sid}: {recording_url} (Duration: {recording_duration}s)")
    
    # Get session
    session = get_or_create_session(call_sid)
    
    # Create TwiML response
    response = VoiceResponse()
    
    # Check if we have a recording and OpenAI service
    if recording_url and int(recording_duration) > 0 and openai_service:
        try:
            # Download and process the recording
            import requests
            import tempfile
            from requests.auth import HTTPBasicAuth
            
            # Download recording with Twilio authentication
            auth = HTTPBasicAuth(settings.twilio_account_sid, settings.twilio_auth_token)
            
            # Try different audio formats with retry logic
            audio_response = None
            temp_audio_path = None
            max_retries = 3
            retry_delay = 2  # seconds
            
            for attempt in range(max_retries):
                logger.info(f"🔄 Download attempt {attempt + 1}/{max_retries}")
                
                # First try the original URL (might already have format)
                logger.info(f"🎵 Trying original recording URL: {recording_url}")
                audio_response = requests.get(recording_url, auth=auth, timeout=10)
                
                if audio_response.status_code != 200:
                    # Try with .mp3 format
                    logger.info(f"🎵 Trying MP3 format: {recording_url}.mp3")
                    audio_response = requests.get(recording_url + '.mp3', auth=auth, timeout=10)
                
                if audio_response.status_code != 200:
                    # Try with .wav format
                    logger.info(f"🎵 Trying WAV format: {recording_url}.wav")
                    audio_response = requests.get(recording_url + '.wav', auth=auth, timeout=10)
                
                logger.info(f"📥 Recording download status: {audio_response.status_code}")
                
                if audio_response.status_code == 200:
                    break  # Success!
                elif attempt < max_retries - 1:
                    logger.info(f"⏳ Recording not ready, waiting {retry_delay} seconds...")
                    import time
                    time.sleep(retry_delay)
            
            if audio_response.status_code == 200:
                # Determine file extension based on content type or URL
                content_type = audio_response.headers.get('content-type', '')
                if 'mp3' in content_type or recording_url.endswith('.mp3'):
                    file_extension = '.mp3'
                elif 'wav' in content_type or recording_url.endswith('.wav'):
                    file_extension = '.wav'
                else:
                    file_extension = '.mp3'  # Default to MP3
                
                logger.info(f"🎵 Audio format detected: {file_extension}")
                
                # Save to temporary file
                with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as temp_file:
                    temp_file.write(audio_response.content)
                    temp_audio_path = temp_file.name
                
                logger.info(f"💾 Audio saved to: {temp_audio_path}")
                
                # Convert speech to text
                user_text = openai_service.speech_to_text(temp_audio_path)
                
                # Clean up temp file
                os.unlink(temp_audio_path)
                
                if user_text:
                    logger.info(f"🎯 User said: {user_text}")
                    
                    # Process with OpenAI
                    ai_response, updated_history = openai_service.process_conversation_turn(
                        user_text, 
                        session['conversation_history']
                    )
                    
                    # Update session
                    session['conversation_history'] = updated_history
                    session['turn_count'] += 1
                    
                    logger.info(f"🤖 AI response: {ai_response}")
                    
                    # Respond to caller
                    response.say(ai_response, voice='alice', language='en-US')
                    
                    # Ask if they have more questions
                    response.pause(length=1)
                    response.say(
                        "Is there anything else I can help you with?",
                        voice='alice',
                        language='en-US'
                    )
                    
                    # Record next question
                    response.record(
                        max_length=30,
                        play_beep=True,
                        action=url_for('handle_recording', _external=True),
                        method='POST',
                        timeout=10,
                        transcribe=False
                    )
                    
                    # If no response, end call politely
                    response.say(
                        "Thank you for calling VoicePlate! Have a great day!",
                        voice='alice',
                        language='en-US'
                    )
                    response.hangup()
                    
                else:
                    # Speech-to-text failed
                    response.say(
                        "I'm sorry, I couldn't understand what you said. Could you please repeat that?",
                        voice='alice',
                        language='en-US'
                    )
                    
                    # Try recording again
                    response.record(
                        max_length=30,
                        play_beep=True,
                        action=url_for('handle_recording', _external=True),
                        method='POST',
                        timeout=10,
                        transcribe=False
                    )
                    
                    response.say(
                        "Thank you for calling. Goodbye!",
                        voice='alice',
                        language='en-US'
                    )
                    response.hangup()
            
            else:
                logger.error(f"❌ Failed to download recording after trying multiple formats")
                logger.error(f"📍 Recording URL: {recording_url}")
                logger.error(f"📍 Final status code: {audio_response.status_code}")
                logger.error(f"📍 Response headers: {dict(audio_response.headers)}")
                logger.error(f"📍 Response text: {audio_response.text[:200]}...")
                
                response.say(
                    "I'm sorry, there was a technical issue accessing the recording. Please try calling again.",
                    voice='alice',
                    language='en-US'
                )
                response.hangup()
                
        except Exception as e:
            logger.error(f"❌ Error processing recording: {str(e)}")
            response.say(
                "I apologize, but I'm having trouble processing your request. Please try again.",
                voice='alice',
                language='en-US'
            )
            response.hangup()
    
    else:
        # No recording, too short, or no OpenAI service
        response.say(
            "Thank you for calling VoicePlate! Have a great day!",
            voice='alice',
            language='en-US'
        )
        response.hangup()
    
    # Clean up session if call is ending
    if 'hangup' in str(response).lower():
        cleanup_session(call_sid)
    
    logger.info(f"✅ Recording processed for call {call_sid}")
    
    return str(response), 200, {'Content-Type': 'text/xml'}

@app.route('/status', methods=['GET', 'POST'])
def status():
    """Detailed status endpoint for debugging and Twilio status callbacks."""
    
    # If this is a Twilio status callback (POST), log it and return 200
    if request.method == 'POST':
        logger = logging.getLogger(__name__)
        call_sid = request.form.get('CallSid', 'unknown')
        call_status = request.form.get('CallStatus', 'unknown')
        logger.info(f"📊 Status callback for call {call_sid}: {call_status}")
        return "OK", 200
    
    # Otherwise return detailed status information (GET)
    return jsonify({
        'application': {
            'name': 'VoicePlate Call Answering Agent',
            'version': '1.0.0',
            'environment': getattr(settings, 'flask_env', 'development'),
            'debug': settings.flask_debug
        },
        'configuration': {
            'twilio_number': getattr(settings, 'twilio_phone_number', 'not_configured'),
            'openai_model': getattr(settings, 'openai_model', 'not_configured'),
            'host': settings.host,
            'port': settings.port
        },
        'session_stats': {
            'active_sessions': len(call_sessions),
            'session_ids': list(call_sessions.keys())
        },
        'endpoints': {
            'voice_webhook': f"{request.host_url}voice",
            'recording_handler': f"{request.host_url}handle_recording",
            'health_check': f"{request.host_url}health",
            'status': f"{request.host_url}status",
            'test': f"{request.host_url}test"
        }
    })

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors."""
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    logger = logging.getLogger(__name__)
    logger.error(f"Internal server error: {str(error)}")
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    logger = logging.getLogger(__name__)
    
    logger.info(f"🌐 Starting VoicePlate on {settings.host}:{settings.port}")
    logger.info(f"📞 Twilio webhook URL: http://{settings.host}:{settings.port}/voice")
    logger.info(f"🎙️ Recording handler: http://{settings.host}:{settings.port}/handle_recording")
    logger.info(f"🔧 Health check: http://{settings.host}:{settings.port}/health")
    logger.info(f"🧪 Test endpoint: http://{settings.host}:{settings.port}/test")
    
    # Run the Flask app
    try:
        app.run(
            host=settings.host,
            port=settings.port,
            debug=settings.flask_debug
        )
    except Exception as e:
        logger.error(f"Failed to start Flask app: {e}")
        print(f"Error starting app: {e}") 