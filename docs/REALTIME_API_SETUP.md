# OpenAI Realtime API Setup Guide

## Overview

This guide covers setting up VoicePlate with OpenAI's Realtime API for ultra-low latency voice conversations.

## Prerequisites

1. **OpenAI API Access**: Requires OpenAI Realtime API access (currently in beta)
2. **Updated Dependencies**: Run `pip install -r requirements.txt` after pulling latest changes
3. **Python 3.9+**: Required for async WebSocket support

## Environment Configuration

Add these new environment variables to your `.env` file:

```bash
# ================================
# OPENAI REALTIME API CONFIGURATION
# ================================
OPENAI_REALTIME_MODEL=gpt-4o-realtime-preview-2024-10-01
REALTIME_VOICE=alloy
REALTIME_TEMPERATURE=0.8
REALTIME_MAX_TOKENS=
REALTIME_TURN_DETECTION=server_vad
REALTIME_INPUT_AUDIO_FORMAT=g711_ulaw
REALTIME_OUTPUT_AUDIO_FORMAT=g711_ulaw

# ================================
# FEATURE FLAGS
# ================================
# Set to true to use Realtime API instead of traditional STT->GPT->TTS
USE_REALTIME_API=false
# Set to true to fallback to traditional API if Realtime API fails
ENABLE_REALTIME_FALLBACK=true

# ================================
# WEBSOCKET CONFIGURATION
# ================================
WEBSOCKET_TIMEOUT=30
MAX_RECONNECT_ATTEMPTS=3
RECONNECT_DELAY=2.0
```

## Configuration Options

### Voice Options
- `alloy` - Neutral, balanced voice (recommended)
- `echo` - Alternative voice option  
- `fable` - Another voice variation
- `onyx` - Deeper voice
- `nova` - Bright voice
- `shimmer` - Soft voice

### Audio Formats
- `g711_ulaw` - 8kHz μ-law (Twilio compatible, recommended)
- `g711_alaw` - 8kHz A-law
- `pcm16` - 24kHz PCM (higher quality, may need conversion)

### Turn Detection
- `server_vad` - Server-side voice activity detection (recommended)
- `none` - Manual control (push-to-talk style)

## Testing the Realtime Service

### 1. Basic Health Check

```python
from src.services.realtime_service import realtime_service

# Check service health
health = await realtime_service.health_check()
print(health)
```

### 2. Create and Test Session

```python
# Create a new session
session = await realtime_service.create_session("test_session_001")

# Connect to OpenAI
success = await realtime_service.connect_to_openai("test_session_001")
if success:
    print("✅ Connected to OpenAI Realtime API")
else:
    print("❌ Failed to connect")

# Get session info
info = await realtime_service.get_session_info("test_session_001")
print(f"Session info: {info}")

# Cleanup
await realtime_service.close_session("test_session_001")
```

## Migration Strategy

The system is designed for gradual migration:

### Phase 1: Parallel Testing (Current)
- Traditional system remains primary
- Realtime API runs in parallel for testing
- `USE_REALTIME_API=false` (default)

### Phase 2: Gradual Rollout
- Enable Realtime API for specific phone numbers
- Monitor performance and reliability
- `USE_REALTIME_API=true` with `ENABLE_REALTIME_FALLBACK=true`

### Phase 3: Full Migration
- Realtime API becomes primary
- Traditional system as backup only
- `USE_REALTIME_API=true` with `ENABLE_REALTIME_FALLBACK=false`

## Performance Expectations

| Metric | Traditional API | Realtime API | Improvement |
|--------|----------------|--------------|-------------|
| **Latency** | ~3 seconds | ~500ms | 83% reduction |
| **User Experience** | Sequential | Natural | Interruption handling |
| **Resource Usage** | High (file I/O) | Low (streaming) | Reduced CPU |
| **Error Recovery** | Manual | Built-in | Simplified |

## Troubleshooting

### Common Issues

1. **WebSocket Connection Fails**
   ```bash
   # Check API key
   echo $OPENAI_API_KEY
   
   # Verify model access
   curl -H "Authorization: Bearer $OPENAI_API_KEY" \
        -H "OpenAI-Beta: realtime=v1" \
        "https://api.openai.com/v1/models/gpt-4o-realtime-preview-2024-10-01"
   ```

2. **Audio Format Issues**
   - Ensure `REALTIME_INPUT_AUDIO_FORMAT=g711_ulaw` for Twilio
   - Check audio encoding in logs

3. **Session Management**
   ```python
   # List active sessions
   sessions = realtime_service.get_all_sessions()
   print(f"Active sessions: {sessions}")
   
   # Check session state
   info = await realtime_service.get_session_info(session_id)
   print(f"State: {info['state']}")
   ```

### Logging

Set appropriate log levels for debugging:

```bash
# Detailed WebSocket logging
LOG_LEVEL=DEBUG

# Production logging
LOG_LEVEL=INFO
```

## Integration with Menu Service

The Realtime service automatically integrates with the existing menu service:

```python
# Menu context is automatically added for menu-related queries
# No additional configuration needed
```

## Next Steps

1. **Test Basic Functionality**: Create sessions and test connections
2. **Implement WebSocket Handler**: Connect Twilio Media Streams
3. **Add Audio Processing**: Handle real-time audio streaming
4. **Enable Function Calling**: Integrate menu service via tools
5. **Performance Testing**: Compare with traditional system

## Support

- Check logs in `logs/app.log` for detailed debugging
- Monitor WebSocket connections in real-time
- Use health check endpoint for system status 