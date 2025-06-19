# VoicePlate Call Answering Agent

A Python-based call answering agent that uses OpenAI for intelligent Q&A responses and Twilio for handling phone calls.

## Features

- 📞 **Twilio Integration**: Handle incoming phone calls with webhooks
- 🤖 **OpenAI Integration**: Intelligent Q&A using GPT models
- 🎙️ **Real-time Audio Processing**: Speech-to-text and text-to-speech
- 🔧 **Configurable**: Environment-based configuration management
- 📝 **Logging**: Comprehensive logging for monitoring and debugging
- 🧪 **Testing**: Unit and integration tests included

## Project Structure

```
VoicePlate/
├── src/                    # Source code
│   ├── __init__.py
│   └── utils/             # Utility modules
├── config/                # Configuration files
│   ├── __init__.py
│   └── settings.py        # Pydantic settings
├── tests/                 # Test files
├── logs/                  # Log files (created automatically)
├── requirements.txt       # Python dependencies
├── .env.example          # Example environment variables
└── README.md             # This file
```

## Setup Instructions

### 1. Clone and Setup Environment

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Environment Configuration

```bash
# Copy example environment file
cp .env.example .env

# Edit .env file with your actual API keys and configuration
nano .env
```

### 3. Required API Keys

- **OpenAI API Key**: Get from [OpenAI Platform](https://platform.openai.com/api-keys)
- **Twilio Credentials**: Get from [Twilio Console](https://console.twilio.com/)
  - Account SID
  - Auth Token
  - Phone Number

### 4. Local Development with ngrok

For local development, you'll need ngrok to expose your local server to Twilio:

```bash
# Install ngrok
npm install -g ngrok

# Start your application (in one terminal)
python src/app.py

# Expose local server (in another terminal)
ngrok http 5000

# Update BASE_WEBHOOK_URL in .env with your ngrok URL
```

## Next Steps

This completes the basic project setup. The next steps will involve:

1. Core Application Structure (Flask app with routing)
2. Twilio Integration (webhook endpoints)
3. OpenAI Integration (Q&A processing)
4. Audio Processing Pipeline
5. Call Flow Management
6. Testing and Deployment

## Development

```bash
# Run tests
pytest

# Format code
black src/

# Lint code
flake8 src/
```

## Contributing

1. Follow the existing code structure
2. Add tests for new features
3. Use black for code formatting
4. Update documentation as needed 