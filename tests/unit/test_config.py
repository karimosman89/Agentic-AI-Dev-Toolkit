#!/usr/bin/env python3
"""
Unit Tests for Configuration
============================

Test suite for configuration management and validation.
"""

import pytest
import os
from unittest.mock import patch

from src.core.config import Settings, get_settings


class TestSettings:
    """Test Settings configuration class."""
    
    def test_default_settings(self):
        """Test default configuration values."""
        settings = Settings()
        
        assert settings.app_name == "Agentic AI Development Toolkit"
        assert settings.app_version == "2.0.0"
        assert settings.api_host == "0.0.0.0"
        assert settings.api_port == 8080
        assert settings.debug == False
        assert settings.environment == "development"
    
    @patch.dict(os.environ, {
        "AGENTIC_APP_NAME": "Test App",
        "AGENTIC_API_PORT": "9000",
        "AGENTIC_DEBUG": "true",
        "OPENAI_API_KEY": "test-key"
    })
    def test_environment_override(self):
        """Test environment variable override."""
        settings = Settings()
        
        assert settings.app_name == "Test App"
        assert settings.api_port == 9000
        assert settings.debug == True
        assert settings.openai_api_key == "test-key"
    
    def test_log_level_validation(self):
        """Test log level validation."""
        # Valid log level
        settings = Settings(log_level="DEBUG")
        assert settings.log_level == "DEBUG"
        
        # Invalid log level should raise ValueError
        with pytest.raises(ValueError):
            Settings(log_level="INVALID")
    
    def test_environment_validation(self):
        """Test environment validation."""
        # Valid environments
        for env in ["development", "testing", "staging", "production"]:
            settings = Settings(environment=env)
            assert settings.environment == env
        
        # Invalid environment should raise ValueError
        with pytest.raises(ValueError):
            Settings(environment="invalid")
    
    def test_port_validation(self):
        """Test port number validation."""
        # Valid port
        settings = Settings(api_port=8080)
        assert settings.api_port == 8080
        
        # Invalid ports should raise ValueError
        with pytest.raises(ValueError):
            Settings(api_port=80)  # Too low
        
        with pytest.raises(ValueError):
            Settings(api_port=70000)  # Too high
    
    def test_database_config(self):
        """Test database configuration method."""
        settings = Settings(database_url="postgresql://test:test@localhost/test")
        
        db_config = settings.get_database_config()
        
        assert db_config["url"] == "postgresql://test:test@localhost/test"
        assert "echo" in db_config
        assert "future" in db_config
    
    def test_redis_config(self):
        """Test Redis configuration method."""
        settings = Settings(redis_url="redis://localhost:6380")
        
        redis_config = settings.get_redis_config()
        
        assert redis_config["url"] == "redis://localhost:6380"
        assert redis_config["encoding"] == "utf-8"
        assert redis_config["decode_responses"] == True
    
    def test_openai_config(self):
        """Test OpenAI configuration method."""
        # With API key
        settings = Settings(
            openai_api_key="test-key",
            openai_model="gpt-3.5-turbo",
            openai_temperature=0.5
        )
        
        openai_config = settings.get_openai_config()
        
        assert openai_config["api_key"] == "test-key"
        assert openai_config["model"] == "gpt-3.5-turbo"
        assert openai_config["temperature"] == 0.5
        
        # Without API key
        settings_no_key = Settings(openai_api_key=None)
        assert settings_no_key.get_openai_config() == {}
    
    def test_anthropic_config(self):
        """Test Anthropic configuration method."""
        # With API key
        settings = Settings(
            anthropic_api_key="test-key",
            anthropic_model="claude-3-opus"
        )
        
        anthropic_config = settings.get_anthropic_config()
        
        assert anthropic_config["api_key"] == "test-key"
        assert anthropic_config["model"] == "claude-3-opus"
        
        # Without API key
        settings_no_key = Settings(anthropic_api_key=None)
        assert settings_no_key.get_anthropic_config() == {}
    
    def test_environment_checks(self):
        """Test environment check methods."""
        # Production check
        prod_settings = Settings(environment="production", debug=False)
        assert prod_settings.is_production() == True
        assert prod_settings.is_development() == False
        
        # Development check
        dev_settings = Settings(environment="development", debug=True)
        assert dev_settings.is_production() == False
        assert dev_settings.is_development() == True


class TestGlobalSettings:
    """Test global settings functions."""
    
    def test_get_settings(self):
        """Test get_settings function."""
        settings = get_settings()
        
        assert isinstance(settings, Settings)
        assert settings.app_name == "Agentic AI Development Toolkit"
    
    def test_settings_singleton_behavior(self):
        """Test that get_settings returns the same instance."""
        settings1 = get_settings()
        settings2 = get_settings()
        
        # Should be the same object
        assert settings1 is settings2


if __name__ == "__main__":
    pytest.main([__file__])