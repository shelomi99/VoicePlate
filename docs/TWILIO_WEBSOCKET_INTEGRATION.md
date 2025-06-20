# Twilio Media Streams WebSocket Integration Guide

## Overview

This guide covers integrating Twilio Media Streams with the VoicePlate WebSocket handler for real-time audio streaming with OpenAI's Realtime API.

## Architecture

```
Twilio Phone Call → Media Streams → WebSocket → OpenAI Realtime API
                                      ↓
Twilio Audio Response ← WebSocket ← OpenAI Response Stream
```

## Prerequisites

1. **Twilio Account** with Media Streams enabled
2. **ngrok** or public URL for WebSocket endpoint
3. **OpenAI Realtime API** access
4. **VoicePlate FastAPI server** running

## Setup Steps

### 1. Configure Twilio Media Streams

#### Update Twilio Webhook URL

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>Welcome to VoicePlate! Connecting you to our AI assistant...</Say>
    <Connect>
        <Stream url="wss://your-domain.com/ws/media">
            <Parameter name="track">both_tracks</Parameter>
            <Parameter name="statusCallback">https://your-domain.com/stream/status</Parameter>
        </Stream>
    </Connect>
</Response>
```

#### Configure in Twilio Console

1. Go to **Phone Numbers** → **Manage** → **Active numbers**
2. Select your VoicePlate phone number
3. Update webhook URL to use the new TwiML above
4. Save configuration

### 2. Environment Configuration

Add these settings to your `.env` file:

```bash
# Enable Realtime API
USE_REALTIME_API=true
ENABLE_REALTIME_FALLBACK=true

# WebSocket Configuration
WEBSOCKET_TIMEOUT=30
MAX_RECONNECT_ATTEMPTS=3
RECONNECT_DELAY=2.0

# Twilio Media Streams
TWILIO_MEDIA_STREAM_URL=wss://your-domain.com/ws/media
```

### 3. Run Dual Server Setup

```bash
# Start both Flask and FastAPI servers
python run_dual_server.py
```

This will start:
- **Flask Server**: `http://localhost:5001` (traditional API)
- **FastAPI Server**: `http://localhost:6001` (realtime WebSocket)
- **WebSocket Endpoint**: `ws://localhost:6001/ws/media`

### 4. Expose WebSocket with ngrok

```bash
# Expose FastAPI server
ngrok http 6001

# Note the WebSocket URL: wss://abc123.ngrok.io/ws/media
```

## Message Flow

### 1. Call Initiation
```json
{
  "event": "start",
  "streamSid": "MZ123...",
  "start": {
    "callSid": "CA123...",
    "tracks": ["inbound"],
    "mediaFormat": {
      "encoding": "audio/x-mulaw",
      "sampleRate": 8000,
      "channels": 1
    }
  }
}
```

### 2. Audio Streaming (Inbound)
```json
{
  "event": "media",
  "streamSid": "MZ123...",
  "media": {
    "track": "inbound",
    "chunk": "2",
    "timestamp": "1234567890",
    "payload": "base64-encoded-audio-data"
  }
}
```

### 3. Audio Response (Outbound)
```json
{
  "event": "media",
  "streamSid": "MZ123...",
  "media": {
    "track": "outbound",
    "payload": "base64-encoded-response-audio"
  }
}
```

### 4. Call Termination
```json
{
  "event": "stop",
  "streamSid": "MZ123..."
}
```

## WebSocket Handler Features

### Real-time Audio Processing
- **Automatic VAD**: Server-side voice activity detection
- **Interruption Handling**: Natural conversation flow
- **Audio Format**: G.711 μ-law (Twilio compatible)
- **Streaming**: Real-time bidirectional audio

### Session Management
- **Session Tracking**: Per-call session management
- **State Persistence**: Conversation context maintained
- **Cleanup**: Automatic resource cleanup on call end
- **Monitoring**: Health checks and metrics

### OpenAI Integration
- **Realtime API**: Direct WebSocket to OpenAI
- **Function Calling**: Menu service integration
- **Fallback**: Traditional API backup
- **Error Recovery**: Automatic retry and fallback

## Testing the Integration

### 1. Health Check
```bash
# Check FastAPI server
curl http://localhost:6001/health

# Check active streams
curl http://localhost:6001/streams

# Check realtime sessions
curl http://localhost:6001/realtime/sessions
```

### 2. WebSocket Connection Test
```javascript
// Test WebSocket connection
const ws = new WebSocket('ws://localhost:6001/ws/media');

ws.onopen = () => {
    console.log('✅ WebSocket connected');
    
    // Send test start event
    ws.send(JSON.stringify({
        event: 'start',
        streamSid: 'test-stream-123',
        start: {
            callSid: 'test-call-456',
            tracks: ['inbound']
        }
    }));
};

ws.onmessage = (event) => {
    console.log('📨 Received:', JSON.parse(event.data));
};
```

### 3. End-to-End Test
1. Call your Twilio number
2. Speak into the phone
3. Monitor logs for:
   - WebSocket connection
   - Audio streaming
   - OpenAI responses
   - Audio playback

## Monitoring and Debugging

### Log Levels
```bash
# Detailed WebSocket logging
LOG_LEVEL=DEBUG

# Production logging
LOG_LEVEL=INFO
```

### Key Log Messages
- `🔗 WebSocket connection accepted` - Twilio connected
- `📞 Starting media stream` - Audio stream started
- `✅ OpenAI Realtime session created` - AI session ready
- `🎙️ Speech started` - User speaking detected
- `🎵 Forwarded audio to Twilio` - AI response sent

### Health Monitoring
```bash
# Monitor all services
curl http://localhost:6001/status

# Check specific streams
curl http://localhost:6001/streams

# Monitor call sessions
curl http://localhost:6001/calls
```

## Performance Optimization

### Latency Reduction
- **Audio Format**: Use G.711 μ-law (no conversion needed)
- **Buffering**: Minimal audio buffering
- **Connection**: Persistent WebSocket connections
- **Processing**: Real-time stream processing

### Resource Management
- **Memory**: Automatic cleanup of ended sessions
- **Connections**: Connection pooling for efficiency
- **CPU**: Efficient audio processing
- **Network**: Optimized message batching

## Error Handling

### Connection Failures
- **Automatic Retry**: Up to 3 reconnection attempts
- **Fallback**: Traditional API if realtime fails
- **Graceful Degradation**: Partial functionality maintained
- **User Experience**: Seamless fallback to user

### Audio Issues
- **Format Validation**: Audio format checking
- **Buffer Management**: Overflow protection
- **Quality Monitoring**: Audio quality checks
- **Error Recovery**: Automatic error recovery

## Production Deployment

### Infrastructure Requirements
- **WebSocket Support**: Load balancer with WebSocket support
- **SSL/TLS**: Secure WebSocket connections (wss://)
- **Scaling**: Horizontal scaling support
- **Monitoring**: Real-time monitoring and alerts

### Security Considerations
- **Authentication**: Twilio signature validation
- **Encryption**: End-to-end encryption
- **Rate Limiting**: Connection rate limiting
- **Access Control**: IP whitelisting if needed

### Configuration
```bash
# Production settings
USE_REALTIME_API=true
ENABLE_REALTIME_FALLBACK=true
WEBSOCKET_TIMEOUT=30
LOG_LEVEL=INFO

# Security
TWILIO_WEBHOOK_VALIDATION=true
SSL_CERT_PATH=/path/to/cert.pem
SSL_KEY_PATH=/path/to/key.pem
```

## Troubleshooting

### Common Issues

1. **WebSocket Connection Fails**
   - Check ngrok tunnel is active
   - Verify URL in Twilio configuration
   - Check firewall settings

2. **No Audio Received**
   - Verify Twilio Media Streams configuration
   - Check audio format compatibility
   - Monitor WebSocket messages

3. **OpenAI Connection Issues**
   - Verify API key and model access
   - Check realtime API beta access
   - Monitor connection logs

4. **High Latency**
   - Check network connectivity
   - Optimize audio buffer sizes
   - Monitor processing times

### Debug Commands
```bash
# Test WebSocket connectivity
wscat -c ws://localhost:6001/ws/media

# Monitor real-time logs
tail -f logs/app.log | grep -E "(WebSocket|Realtime|Audio)"

# Check system resources
htop
```

## Next Steps

1. **Performance Testing**: Load test with multiple concurrent calls
2. **Integration Testing**: End-to-end testing with real phone calls
3. **Monitoring Setup**: Production monitoring and alerting
4. **Documentation**: User-facing documentation and guides

## Support

- Check logs for detailed error messages
- Use health check endpoints for system status
- Monitor WebSocket connections in real-time
- Review Twilio webhook logs for integration issues 