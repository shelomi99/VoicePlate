#!/usr/bin/env python3
"""
VoicePlate Unified Realtime FastAPI Application
Single server that handles both Twilio webhooks and WebSocket functionality.
"""

import os
import sys
import logging
from typing import Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException, Form, Depends
from fastapi.responses import Response, JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import settings
from src.realtime_server import realtime_server

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    logger.info("🚀 Starting VoicePlate Unified Realtime Server")
    logger.info("=" * 60)
    logger.info(f"📞 Webhook endpoint: http://{settings.host}:{settings.port}/voice")
    logger.info(f"🎧 WebSocket endpoint: ws://{settings.host}:{settings.port}/ws/media")
    logger.info(f"🔧 Health check: http://{settings.host}:{settings.port}/health")
    logger.info(f"📚 API docs: http://{settings.host}:{settings.port}/docs")
    logger.info("=" * 60)
    yield
    logger.info("🛑 Shutting down VoicePlate Unified Realtime Server")

# Create FastAPI application
app = FastAPI(
    title="VoicePlate Realtime Server",
    description="Unified server for Twilio webhooks and OpenAI Realtime API integration",
    version="2.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dependency to get call data from form
async def get_call_data(
    CallSid: str = Form(...),
    From: str = Form(...),
    To: str = Form(...),
    CallStatus: str = Form(...),
    AccountSid: str = Form(None),
    Direction: str = Form(None),
    CallerName: str = Form(None)
) -> Dict[str, str]:
    """Extract call data from Twilio webhook form."""
    return {
        'CallSid': CallSid,
        'From': From,
        'To': To,
        'CallStatus': CallStatus,
        'AccountSid': AccountSid,
        'Direction': Direction,
        'CallerName': CallerName
    }

# Dependency to get speech data from form
async def get_speech_data(
    CallSid: str = Form(...),
    From: str = Form(...),
    To: str = Form(...),
    SpeechResult: str = Form(None),
    Confidence: str = Form(None),
    CallStatus: str = Form(None)
) -> Dict[str, str]:
    """Extract speech data from Twilio webhook form."""
    return {
        'CallSid': CallSid,
        'From': From,
        'To': To,
        'SpeechResult': SpeechResult,
        'Confidence': Confidence,
        'CallStatus': CallStatus
    }

# Dependency to get stream status data
async def get_status_data(
    CallSid: str = Form(...),
    StreamSid: str = Form(None),
    Status: str = Form(...),
    AccountSid: str = Form(None)
) -> Dict[str, str]:
    """Extract stream status data from Twilio webhook form."""
    return {
        'CallSid': CallSid,
        'StreamSid': StreamSid,
        'Status': Status,
        'AccountSid': AccountSid
    }

@app.post('/voice')
async def voice_webhook(
    request: Request,
    call_data: Dict[str, str] = Depends(get_call_data)
) -> Response:
    """
    Handle incoming Twilio voice webhook for realtime processing.
    This endpoint immediately connects calls to Media Streams.
    """
    return await realtime_server.handle_voice_webhook(request, call_data)

@app.post('/process-speech')
async def process_speech(
    request: Request,
    speech_data: Dict[str, str] = Depends(get_speech_data)
) -> Response:
    """
    Handle speech processing for traditional voice interactions.
    This endpoint processes user speech and generates AI responses.
    """
    return await realtime_server.process_speech(request)

@app.post('/stream/status')
async def stream_status(
    request: Request,
    status_data: Dict[str, str] = Depends(get_status_data)
) -> JSONResponse:
    """Handle Media Stream status callbacks from Twilio."""
    return await realtime_server.handle_stream_status(request, status_data)

@app.websocket('/ws/media')
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for Twilio Media Streams.
    Handles bidirectional audio streaming with OpenAI Realtime API.
    """
    await realtime_server.handle_websocket_connection(websocket)

@app.get('/health')
async def health_check() -> JSONResponse:
    """Health check endpoint for the unified realtime server."""
    health_status = realtime_server.get_health_status()
    return JSONResponse(content=health_status)

@app.get('/status')
async def server_status() -> JSONResponse:
    """Get detailed server status including active sessions."""
    health = realtime_server.get_health_status()
    
    # Add additional status information
    status = {
        **health,
        'endpoints': {
            'voice_webhook': '/voice',
            'stream_status': '/stream/status',
            'websocket': '/ws/media',
            'health': '/health',
            'status': '/status',
            'docs': '/docs'
        },
        'active_sessions': realtime_server.active_sessions,
        'call_sessions': realtime_server.call_sessions
    }
    
    return JSONResponse(content=status)

@app.post('/fallback')
async def fallback_webhook(
    request: Request,
    call_data: Dict[str, str] = Depends(get_call_data)
) -> Response:
    """Fallback webhook if realtime processing fails."""
    
    call_sid = call_data.get('CallSid')
    logger.warning(f"⚠️ Using fallback for call {call_sid} - realtime connection failed")
    
    # Create simple TwiML response
    from twilio.twiml.voice_response import VoiceResponse
    response = VoiceResponse()
    response.say(
        "I'm sorry, our advanced AI assistant is temporarily unavailable. Please try calling back in a moment.",
        voice='alice'
    )
    response.hangup()
    
    return Response(content=str(response), media_type='text/xml')

@app.get('/')
async def root() -> JSONResponse:
    """Root endpoint with service information."""
    return JSONResponse(content={
        'service': 'VoicePlate Unified Realtime Server',
        'version': '2.0.0',
        'description': 'Single FastAPI server handling both Twilio webhooks and WebSocket connections for OpenAI Realtime API',
        'architecture': 'Unified (no Flask dependency)',
        'endpoints': {
            'voice_webhook': '/voice',
            'websocket': '/ws/media',
            'stream_status': '/stream/status',
            'fallback': '/fallback',
            'health': '/health',
            'status': '/status',
            'docs': '/docs'
        },
        'configuration': {
            'realtime_enabled': settings.use_realtime_api,
            'model': settings.openai_realtime_model,
            'voice': settings.realtime_voice,
            'audio_format': settings.realtime_input_audio_format,
            'host': settings.host,
            'port': settings.port
        },
        'benefits': [
            '80% latency reduction vs traditional API',
            'Real-time conversation with interruption handling',
            'Single server architecture',
            'No Flask dependency',
            'Simplified deployment'
        ]
    })

@app.get('/docs-info')
async def docs_info() -> HTMLResponse:
    """Information page about the API documentation."""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>VoicePlate Realtime API</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; }
            .header { color: #2c3e50; }
            .endpoint { background: #f8f9fa; padding: 10px; margin: 10px 0; border-radius: 5px; }
            .method { font-weight: bold; color: #e74c3c; }
            .url { font-family: monospace; background: #ecf0f1; padding: 2px 5px; }
        </style>
    </head>
    <body>
        <h1 class="header">🎉 VoicePlate Unified Realtime Server</h1>
        <p>Welcome to the VoicePlate Realtime API server! This unified FastAPI application handles both Twilio webhooks and WebSocket connections for seamless integration with OpenAI's Realtime API.</p>
        
        <h2>📋 Key Endpoints</h2>
        
        <div class="endpoint">
            <span class="method">POST</span> <span class="url">/voice</span><br>
            <strong>Twilio Voice Webhook</strong> - Handles incoming calls and connects to Media Streams
        </div>
        
        <div class="endpoint">
            <span class="method">POST</span> <span class="url">/process-speech</span><br>
            <strong>Speech Processing</strong> - Handles traditional voice interactions
        </div>
        
        <div class="endpoint">
            <span class="method">WS</span> <span class="url">/ws/media</span><br>
            <strong>WebSocket Endpoint</strong> - Handles real-time audio streaming with OpenAI
        </div>
        
        <div class="endpoint">
            <span class="method">GET</span> <span class="url">/health</span><br>
            <strong>Health Check</strong> - Server health and status information
        </div>
        
        <div class="endpoint">
            <span class="method">GET</span> <span class="url">/docs</span><br>
            <strong>API Documentation</strong> - Interactive OpenAPI documentation
        </div>
        
        <h2>🚀 Architecture Benefits</h2>
        <ul>
            <li><strong>Unified Server</strong>: Single FastAPI application (no Flask dependency)</li>
            <li><strong>Real-time Processing</strong>: 80% latency reduction vs traditional API</li>
            <li><strong>Natural Conversations</strong>: Interruption handling and real-time responses</li>
            <li><strong>Simplified Deployment</strong>: One server, one port, easy setup</li>
        </ul>
        
        <h2>📞 Setup Instructions</h2>
        <ol>
            <li>Start the server: <code>python run_unified_server.py</code></li>
            <li>Expose with ngrok: <code>ngrok http """ + str(settings.port) + """</code></li>
            <li>Configure Twilio webhook URL: <code>https://your-ngrok-url.ngrok.io/voice</code></li>
            <li>Make a test call and experience real-time AI conversation!</li>
        </ol>
        
        <p><a href="/docs">→ View Interactive API Documentation</a></p>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler for better error reporting."""
    logger.error(f"❌ Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": "An unexpected error occurred",
            "type": type(exc).__name__
        }
    )

if __name__ == "__main__":
    import uvicorn
    
    logger.info("🚀 Starting VoicePlate Unified Realtime Server")
    
    uvicorn.run(
        "src.realtime_app_unified:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        reload=False,
        access_log=True
    ) 