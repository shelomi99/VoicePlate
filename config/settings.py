import os
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # OpenAI Configuration
    openai_api_key: str = Field(alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-3.5-turbo", alias="OPENAI_MODEL")
    openai_tts_model: str = Field(default="tts-1", alias="OPENAI_TTS_MODEL")
    openai_tts_voice: str = Field(default="alloy", alias="OPENAI_TTS_VOICE")
    
    # OpenAI Realtime API Configuration - NEW
    openai_realtime_model: str = Field(default="gpt-4o-realtime-preview-2024-10-01", alias="OPENAI_REALTIME_MODEL")
    realtime_voice: str = Field(default="alloy", alias="REALTIME_VOICE")
    realtime_temperature: float = Field(default=0.8, alias="REALTIME_TEMPERATURE")
    realtime_max_tokens: Optional[int] = Field(default=None, alias="REALTIME_MAX_TOKENS")
    realtime_turn_detection: str = Field(default="server_vad", alias="REALTIME_TURN_DETECTION")
    realtime_input_audio_format: str = Field(default="g711_ulaw", alias="REALTIME_INPUT_AUDIO_FORMAT")
    realtime_output_audio_format: str = Field(default="g711_ulaw", alias="REALTIME_OUTPUT_AUDIO_FORMAT")
    
    # Feature Flags - NEW
    use_realtime_api: bool = Field(default=True, alias="USE_REALTIME_API")
    enable_realtime_fallback: bool = Field(default=True, alias="ENABLE_REALTIME_FALLBACK")
    
    # Twilio Configuration
    twilio_account_sid: str = Field(alias="TWILIO_ACCOUNT_SID")
    twilio_auth_token: str = Field(alias="TWILIO_AUTH_TOKEN")
    twilio_phone_number: str = Field(alias="TWILIO_PHONE_NUMBER")
    
    # Application Configuration
    flask_env: str = Field(default="development", alias="FLASK_ENV")
    flask_debug: bool = Field(default=True, alias="FLASK_DEBUG")
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=5001, alias="PORT")
    
    # Webhook Configuration
    base_webhook_url: str = Field(alias="BASE_WEBHOOK_URL")
    realtime_websocket_url: Optional[str] = Field(default=None, alias="REALTIME_WEBSOCKET_URL")
    
    # Logging Configuration
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_file: str = Field(default="logs/app.log", alias="LOG_FILE")
    
    # Audio Configuration
    audio_format: str = Field(default="wav", alias="AUDIO_FORMAT")
    audio_sample_rate: int = Field(default=16000, alias="AUDIO_SAMPLE_RATE")
    max_recording_duration: int = Field(default=30, alias="MAX_RECORDING_DURATION")
    
    # Voice Assistant Configuration
    greeting_message: str = Field(
        default="Hello! Welcome to VoicePlate, your AI-powered assistant. I'm here to help answer your questions. Please tell me how I can assist you today.",
        alias="GREETING_MESSAGE"
    )
    voice_type: str = Field(default="alice", alias="VOICE_TYPE")
    language: str = Field(default="en-US", alias="LANGUAGE")
    
    # WebSocket Configuration - NEW
    websocket_timeout: int = Field(default=30, alias="WEBSOCKET_TIMEOUT")
    max_reconnect_attempts: int = Field(default=3, alias="MAX_RECONNECT_ATTEMPTS")
    reconnect_delay: float = Field(default=2.0, alias="RECONNECT_DELAY")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Global settings instance
settings = Settings() 