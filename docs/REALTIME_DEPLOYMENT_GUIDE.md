# VoicePlate Realtime API Deployment Guide

## 🎯 Overview

This guide walks you through deploying the VoicePlate Realtime API integration using the new webhook approach that connects Twilio calls directly to OpenAI's Realtime API via Media Streams.

## 🏗️ Architecture

```
Phone Call → Twilio → Realtime Webhook → Media Streams → FastAPI WebSocket → OpenAI Realtime API
```

### Key Benefits
- **80% Latency Reduction**: From ~3 seconds to ~500ms
- **Natural Conversations**: Real-time interruption handling
- **Simplified Setup**: Single webhook configuration
- **Better User Experience**: No audio conversion delays

## 📋 Prerequisites

### 1. Environment Setup
```bash
# Clone the repository
git clone <repository-url>
cd VoicePlate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
```

### 2. Required Environment Variables
```bash
# OpenAI Configuration
OPENAI_API_KEY=your_openai_api_key_here

# Twilio Configuration
TWILIO_ACCOUNT_SID=your_twilio_account_sid_here
TWILIO_AUTH_TOKEN=your_twilio_auth_token_here
TWILIO_PHONE_NUMBER=+1234567890

# Realtime API Settings (defaults work well)
USE_REALTIME_API=true
REALTIME_VOICE=alloy
REALTIME_INPUT_AUDIO_FORMAT=g711_ulaw
REALTIME_OUTPUT_AUDIO_FORMAT=g711_ulaw

# Server Configuration
HOST=0.0.0.0
PORT=5001
```

## 🚀 Deployment Steps

### Step 1: Start the Realtime Servers

```bash
# Start both webhook and WebSocket servers
python run_realtime_server.py
```

This starts:
- **Webhook Server**: Port 5001 (handles Twilio webhook calls)
- **WebSocket Server**: Port 6001 (handles Media Streams)

### Step 2: Expose with ngrok

```bash
# In a new terminal
ngrok http 5001
```

Copy the ngrok URL (e.g., `https://abc123.ngrok.io`)

### Step 3: Configure Twilio Webhook

1. Log into [Twilio Console](https://console.twilio.com/)
2. Go to **Phone Numbers** → **Manage** → **Active Numbers**
3. Click on your phone number
4. Set the webhook URL to: `https://your-ngrok-url.ngrok.io/voice`
5. Make sure HTTP method is set to **POST**
6. Save the configuration

### Step 4: Test the Setup

```bash
# Run the test suite (optional but recommended)
python test_realtime_setup.py
```

### Step 5: Make a Test Call

Call your Twilio phone number and experience real-time conversation!

## 🔧 Configuration Options

### Webhook Configuration
```python
# src/twilio_webhook_realtime.py
@app.route('/voice', methods=['POST'])
def handle_realtime_voice_call():
    # Immediate connection to Media Streams
    # No traditional API processing
```

### WebSocket Configuration
```python
# src/realtime_app.py
@app.websocket("/ws/media")
async def websocket_endpoint(websocket: WebSocket):
    # Handles bidirectional audio streaming
```

### Audio Settings
- **Format**: G.711 μ-law (compatible with Twilio)
- **Sample Rate**: 8kHz (Twilio standard)
- **Channels**: Mono
- **Encoding**: Base64 for transport

## 📊 Monitoring and Logging

### Real-time Logs
The system provides comprehensive logging:

```bash
2024-01-15 10:30:45 - realtime_webhook - INFO - 📞 Incoming realtime call: CA123... from +1234567890
2024-01-15 10:30:45 - websocket_handler - INFO - 🎧 Starting bidirectional audio streaming
2024-01-15 10:30:46 - websocket_handler - INFO - 👤 User said: Hello, can you help me with your menu?
2024-01-15 10:30:47 - websocket_handler - INFO - 🤖 AI said: Hello! I'd be happy to help you with our menu...
```

### Health Checks
- **Webhook Health**: `http://localhost:5001/health`
- **WebSocket Health**: `http://localhost:6001/health`
- **API Documentation**: `http://localhost:6001/docs`

## 🔍 Troubleshooting

### Common Issues

#### 1. Connection Failures
```bash
# Check server status
curl http://localhost:5001/health
curl http://localhost:6001/health

# Verify configuration
python test_realtime_setup.py
```

#### 2. Audio Quality Issues
- Ensure G.711 μ-law format is used
- Check network connectivity to OpenAI
- Verify Twilio Media Streams configuration

#### 3. Webhook Not Responding
- Verify ngrok is running and exposing port 5001
- Check Twilio webhook URL configuration
- Ensure Twilio credentials are correct

#### 4. WebSocket Connection Issues
- Verify FastAPI server is running on port 6001
- Check firewall settings
- Ensure WebSocket URL is properly constructed

### Debug Mode
```bash
# Enable debug logging
export LOG_LEVEL=DEBUG
python run_realtime_server.py
```

### Test Individual Components
```bash
# Test webhook only
python src/twilio_webhook_realtime.py

# Test WebSocket only
uvicorn src.realtime_app:app --host 0.0.0.0 --port 6001
```

## 🔒 Security Considerations

### 1. Twilio Request Validation
The webhook validates all incoming requests are from Twilio:
```python
validator = RequestValidator(settings.twilio_auth_token)
valid = validator.validate(url, request.form, signature)
```

### 2. Environment Variables
Never commit sensitive credentials:
```bash
# Use .env file (gitignored)
OPENAI_API_KEY=sk-...
TWILIO_AUTH_TOKEN=...
```

### 3. Production Deployment
- Use HTTPS for all webhook URLs
- Implement rate limiting
- Monitor for unusual usage patterns
- Regular credential rotation

## 📈 Performance Metrics

### Expected Performance
- **Connection Time**: <500ms
- **Response Latency**: 300-800ms
- **Audio Quality**: High (G.711 μ-law)
- **Concurrent Calls**: 50+ (depending on server resources)

### Monitoring
Track these metrics in production:
- WebSocket connection count
- Average response time
- Error rates
- OpenAI API usage

## 🔄 Fallback Strategy

If the realtime system fails, the webhook includes fallback logic:
```python
@app.route('/fallback', methods=['POST'])
def handle_fallback():
    # Graceful degradation message
    response.say("I'm sorry, our advanced AI assistant is temporarily unavailable...")
```

## 📞 Twilio Configuration Details

### Media Streams Parameters
```xml
<Stream url="wss://your-domain.com/ws/media">
    <Parameter name="track" value="both_tracks" />
    <Parameter name="statusCallback" value="https://your-domain.com/stream/status" />
</Stream>
```

### Required Twilio Features
- Media Streams (available on all plans)
- WebRTC compatible endpoints
- WebSocket support

## 🎉 Success Indicators

You've successfully deployed when:
- ✅ Test suite passes all checks
- ✅ Health endpoints return 200 status
- ✅ Test call connects immediately
- ✅ Conversation feels natural and responsive
- ✅ Logs show real-time audio processing

## 🚀 Next Steps

After successful deployment:
1. **Production Hardening**: Implement monitoring and alerting
2. **Scale Testing**: Test with multiple concurrent calls
3. **Custom Instructions**: Tailor AI responses for your business
4. **Analytics**: Implement call analytics and insights
5. **Integration**: Connect to your existing systems (CRM, menu management, etc.)

## 📞 Support

For issues or questions:
- Check the troubleshooting section above
- Review logs for error details
- Test individual components
- Validate configuration settings

---

**🎉 Congratulations!** You now have a lightning-fast, real-time AI phone assistant powered by OpenAI's latest technology! 