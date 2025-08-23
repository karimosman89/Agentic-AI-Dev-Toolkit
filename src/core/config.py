#!/usr/bin/env python3
"""
Configuration Management for Agentic AI Development Toolkit
===========================================================

Professional configuration management with environment-based settings,
validation, and secure credential handling.

Author: Karim Osman
License: MIT
"""

import os
from typing import Optional, Dict, Any, List
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Application settings with environment variable support.
    
    All settings can be overridden via environment variables with AGENTIC_ prefix.
    """
    
    # Application Settings
    app_name: str = Field(default="Agentic AI Development Toolkit", env="AGENTIC_APP_NAME")
    app_version: str = Field(default="2.0.0", env="AGENTIC_APP_VERSION")
    debug: bool = Field(default=False, env="AGENTIC_DEBUG")
    environment: str = Field(default="development", env="AGENTIC_ENVIRONMENT")
    
    # API Settings
    api_host: str = Field(default="0.0.0.0", env="AGENTIC_API_HOST")
    api_port: int = Field(default=8080, env="AGENTIC_API_PORT")
    api_workers: int = Field(default=1, env="AGENTIC_API_WORKERS")
    api_reload: bool = Field(default=True, env="AGENTIC_API_RELOAD")
    
    # AI Provider Settings
    openai_api_key: Optional[str] = Field(default=None, env="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4", env="AGENTIC_OPENAI_MODEL")
    openai_temperature: float = Field(default=0.7, env="AGENTIC_OPENAI_TEMPERATURE")
    openai_max_tokens: int = Field(default=2000, env="AGENTIC_OPENAI_MAX_TOKENS")
    
    anthropic_api_key: Optional[str] = Field(default=None, env="ANTHROPIC_API_KEY")
    anthropic_model: str = Field(default="claude-3-sonnet-20240229", env="AGENTIC_ANTHROPIC_MODEL")
    
    # Database Settings
    database_url: str = Field(default="sqlite:///./agents.db", env="AGENTIC_DATABASE_URL")
    redis_url: str = Field(default="redis://localhost:6379", env="AGENTIC_REDIS_URL")
    
    # Security Settings
    secret_key: str = Field(default="your-secret-key-change-in-production", env="AGENTIC_SECRET_KEY")
    access_token_expire_minutes: int = Field(default=30, env="AGENTIC_ACCESS_TOKEN_EXPIRE")
    
    # Agent Settings
    max_agents: int = Field(default=100, env="AGENTIC_MAX_AGENTS")
    agent_timeout: int = Field(default=300, env="AGENTIC_AGENT_TIMEOUT")
    max_concurrent_tasks: int = Field(default=10, env="AGENTIC_MAX_CONCURRENT_TASKS")
    
    # Monitoring Settings
    enable_prometheus: bool = Field(default=True, env="AGENTIC_ENABLE_PROMETHEUS")
    prometheus_port: int = Field(default=9090, env="AGENTIC_PROMETHEUS_PORT")
    log_level: str = Field(default="INFO", env="AGENTIC_LOG_LEVEL")
    
    # File Storage Settings
    data_directory: str = Field(default="./data", env="AGENTIC_DATA_DIRECTORY")
    logs_directory: str = Field(default="./logs", env="AGENTIC_LOGS_DIRECTORY")
    models_directory: str = Field(default="./models", env="AGENTIC_MODELS_DIRECTORY")
    
    # Communication Settings
    message_queue_size: int = Field(default=1000, env="AGENTIC_MESSAGE_QUEUE_SIZE")
    websocket_port: int = Field(default=8081, env="AGENTIC_WEBSOCKET_PORT")
    
    # Tool Settings
    enable_web_search: bool = Field(default=True, env="AGENTIC_ENABLE_WEB_SEARCH")
    enable_file_operations: bool = Field(default=True, env="AGENTIC_ENABLE_FILE_OPS")
    enable_code_execution: bool = Field(default=False, env="AGENTIC_ENABLE_CODE_EXEC")
    
    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v):
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"Log level must be one of: {valid_levels}")
        return v.upper()
    
    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v):
        valid_envs = ["development", "testing", "staging", "production"]
        if v.lower() not in valid_envs:
            raise ValueError(f"Environment must be one of: {valid_envs}")
        return v.lower()
    
    @field_validator("api_port", "prometheus_port", "websocket_port")
    @classmethod
    def validate_port(cls, v):
        if not (1024 <= v <= 65535):
            raise ValueError("Port must be between 1024 and 65535")
        return v
    
    def get_database_config(self) -> Dict[str, Any]:
        """Get database configuration."""
        return {
            "url": self.database_url,
            "echo": self.debug,
            "future": True
        }
    
    def get_redis_config(self) -> Dict[str, str]:
        """Get Redis configuration."""
        return {
            "url": self.redis_url,
            "encoding": "utf-8",
            "decode_responses": True
        }
    
    def get_openai_config(self) -> Dict[str, Any]:
        """Get OpenAI configuration."""
        if not self.openai_api_key:
            return {}
        
        return {
            "api_key": self.openai_api_key,
            "model": self.openai_model,
            "temperature": self.openai_temperature,
            "max_tokens": self.openai_max_tokens
        }
    
    def get_anthropic_config(self) -> Dict[str, str]:
        """Get Anthropic configuration."""
        if not self.anthropic_api_key:
            return {}
        
        return {
            "api_key": self.anthropic_api_key,
            "model": self.anthropic_model
        }
    
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment == "production"
    
    def is_development(self) -> bool:
        """Check if running in development environment.""" 
        return self.environment == "development"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get application settings."""
    return settings


def reload_settings() -> Settings:
    """Reload settings from environment."""
    global settings
    settings = Settings()
    return settings