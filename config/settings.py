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
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Global settings instance
settings = Settings() 