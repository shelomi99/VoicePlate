"""
FastAPI Realtime Application
Serves WebSocket endpoints for Twilio Media Streams and OpenAI Realtime API integration.
"""

import logging
import asyncio
from typing import Dict, Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from config.settings import settings
from src.services.websocket_handler import websocket_handler
from src.services.realtime_service import realtime_service

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="VoicePlate Realtime API",
    description="FastAPI application for Twilio Media Streams and OpenAI Realtime API integration",
    version="1.0.0",
    docs_url="/docs" if settings.flask_debug else None,
    redoc_url="/redoc" if settings.flask_debug else None
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.flask_debug else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup."""
    logger.info("🚀 Starting VoicePlate Realtime API server")
    logger.info(f"🎧 WebSocket endpoint: ws://localhost:{settings.port + 1000}/ws/media")
    logger.info(f"🔧 Health check: http://localhost:{settings.port + 1000}/health")
    logger.info(f"📊 Status: http://localhost:{settings.port + 1000}/status")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    logger.info("🛑 Shutting down VoicePlate Realtime API server")
    
    # Close all active streams
    active_streams = websocket_handler.get_active_streams()
    for stream_sid in active_streams:
        await websocket_handler._cleanup_stream(stream_sid)
    
    logger.info("✅ Cleanup completed")

@app.get("/")
async def root():
    """Root endpoint with service information."""
    return {
        "service": "VoicePlate Realtime API",
        "version": "1.0.0",
        "status": "running",
        "features": {
            "realtime_api": settings.use_realtime_api,
            "fallback_enabled": settings.enable_realtime_fallback,
            "websocket_endpoints": ["/ws/media"],
            "http_endpoints": ["/health", "/status", "/streams", "/calls"]
        },
        "integration": {
            "twilio_media_streams": True,
            "openai_realtime_api": settings.use_realtime_api,
            "menu_service": True
        }
    }

@app.websocket("/ws/media")
async def websocket_endpoint(websocket: WebSocket):
    """
    Main WebSocket endpoint for Twilio Media Streams.
    
    This endpoint receives WebSocket connections from Twilio and handles
    bidirectional audio streaming with OpenAI Realtime API.
    """
    await websocket.accept()
    
    logger.info(f"🔗 WebSocket connection accepted from {websocket.client}")
    
    try:
        # Delegate to the WebSocket handler
        await websocket_handler.handle_twilio_websocket(websocket, "/ws/media")
        
    except WebSocketDisconnect:
        logger.info("🔌 WebSocket disconnected")
    except Exception as e:
        logger.error(f"❌ WebSocket error: {e}")
        try:
            await websocket.close(code=1011, reason="Internal server error")
        except:
            pass

@app.get("/health")
async def health_check():
    """Comprehensive health check endpoint."""
    try:
        # Get health from all services
        websocket_health = await websocket_handler.health_check()
        realtime_health = await realtime_service.health_check()
        
        # Combine health information
        health_status = {
            "status": "healthy",
            "timestamp": asyncio.get_event_loop().time(),
            "services": {
                "websocket_handler": websocket_health,
                "realtime_service": realtime_health
            },
            "configuration": {
                "realtime_api_enabled": settings.use_realtime_api,
                "fallback_enabled": settings.enable_realtime_fallback,
                "model": settings.openai_realtime_model,
                "voice": settings.realtime_voice,
                "audio_format": settings.realtime_input_audio_format
            }
        }
        
        return JSONResponse(content=health_status, status_code=200)
        
    except Exception as e:
        logger.error(f"❌ Health check failed: {e}")
        return JSONResponse(
            content={"status": "unhealthy", "error": str(e)}, 
            status_code=503
        )

@app.get("/status")
async def status():
    """Detailed status endpoint with active sessions."""
    try:
        # Get current active streams and calls
        active_streams = websocket_handler.get_active_streams()
        call_sessions = websocket_handler.get_call_sessions()
        realtime_sessions = realtime_service.get_all_sessions()
        
        return {
            "application": {
                "name": "VoicePlate Realtime API",
                "version": "1.0.0",
                "uptime": asyncio.get_event_loop().time()
            },
            "statistics": {
                "active_websocket_streams": len(active_streams),
                "active_call_sessions": len(call_sessions),
                "active_realtime_sessions": len(realtime_sessions)
            },
            "active_streams": active_streams,
            "call_sessions": call_sessions,
            "realtime_sessions": realtime_sessions,
            "configuration": {
                "use_realtime_api": settings.use_realtime_api,
                "enable_fallback": settings.enable_realtime_fallback,
                "websocket_timeout": settings.websocket_timeout,
                "max_reconnect_attempts": settings.max_reconnect_attempts
            }
        }
        
    except Exception as e:
        logger.error(f"❌ Status check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/streams")
async def get_streams():
    """Get information about active WebSocket streams."""
    try:
        streams = websocket_handler.get_active_streams()
        return {
            "active_streams": len(streams),
            "streams": streams
        }
    except Exception as e:
        logger.error(f"❌ Error getting streams: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/calls")
async def get_calls():
    """Get information about active call sessions."""
    try:
        calls = websocket_handler.get_call_sessions()
        return {
            "active_calls": len(calls),
            "calls": calls
        }
    except Exception as e:
        logger.error(f"❌ Error getting calls: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/streams/{stream_sid}/interrupt")
async def interrupt_stream(stream_sid: str, audio_end_ms: int = None):
    """Handle user interruption for a specific stream."""
    try:
        success = await websocket_handler.handle_interruption(stream_sid, audio_end_ms)
        
        if success:
            return {"success": True, "stream_sid": stream_sid, "message": "Interruption handled"}
        else:
            raise HTTPException(status_code=404, detail="Stream not found or inactive")
            
    except Exception as e:
        logger.error(f"❌ Error handling interruption: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/realtime/sessions")
async def get_realtime_sessions():
    """Get information about OpenAI Realtime API sessions."""
    try:
        sessions = realtime_service.get_all_sessions()
        session_info = []
        
        for session_id in sessions:
            info = await realtime_service.get_session_info(session_id)
            if info:
                session_info.append(info)
        
        return {
            "active_sessions": len(sessions),
            "sessions": session_info
        }
        
    except Exception as e:
        logger.error(f"❌ Error getting realtime sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/realtime/sessions/{session_id}")
async def close_realtime_session(session_id: str):
    """Close a specific OpenAI Realtime API session."""
    try:
        await realtime_service.close_session(session_id)
        return {"success": True, "session_id": session_id, "message": "Session closed"}
        
    except Exception as e:
        logger.error(f"❌ Error closing session: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler."""
    logger.error(f"❌ Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)}
    )

# WebSocket exception handler
@app.exception_handler(WebSocketDisconnect)
async def websocket_disconnect_handler(request: Request, exc: WebSocketDisconnect):
    """Handle WebSocket disconnections gracefully."""
    logger.info(f"🔌 WebSocket disconnected with code: {exc.code}")

def create_app() -> FastAPI:
    """Factory function to create and configure the FastAPI app."""
    return app

async def run_server():
    """Run the FastAPI server with uvicorn."""
    # Use a different port from Flask to avoid conflicts
    realtime_port = settings.port + 1000  # e.g., 6001 if Flask is on 5001
    
    config = uvicorn.Config(
        "src.realtime_app:app",
        host=settings.host,
        port=realtime_port,
        log_level=settings.log_level.lower(),
        reload=settings.flask_debug,
        access_log=True
    )
    
    server = uvicorn.Server(config)
    
    logger.info(f"🌐 Starting FastAPI server on {settings.host}:{realtime_port}")
    await server.serve()

if __name__ == "__main__":
    # Run with asyncio
    asyncio.run(run_server()) 