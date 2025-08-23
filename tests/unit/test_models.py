#!/usr/bin/env python3
"""
Unit Tests for Core Models
==========================

Test suite for data models, validation, and serialization.
"""

import pytest
import json
from datetime import datetime, timedelta

from src.core.models import Agent, Message, Tool, AgentStatus, MessageType, ToolCategory


class TestAgent:
    """Test Agent model functionality."""
    
    def test_agent_creation(self):
        """Test basic agent creation."""
        agent = Agent(
            name="TestAgent",
            description="Test agent for unit tests"
        )
        
        assert agent.name == "TestAgent"
        assert agent.description == "Test agent for unit tests"
        assert agent.status == AgentStatus.IDLE
        assert isinstance(agent.id, str)
        assert len(agent.id) > 0
    
    def test_agent_serialization(self):
        """Test agent to dict serialization."""
        agent = Agent(
            name="SerializeAgent",
            description="Test serialization",
            tools=["web_search", "calculate"]
        )
        
        agent_dict = agent.to_dict()
        
        assert agent_dict["name"] == "SerializeAgent"
        assert agent_dict["tools"] == ["web_search", "calculate"]
        assert "created_at" in agent_dict
    
    def test_agent_from_dict(self):
        """Test agent creation from dictionary."""
        agent_data = {
            "id": "test-123",
            "name": "DictAgent",
            "description": "From dict",
            "status": "idle",
            "tools": ["test_tool"]
        }
        
        agent = Agent.from_dict(agent_data)
        
        assert agent.id == "test-123"
        assert agent.name == "DictAgent"
        assert agent.status == AgentStatus.IDLE
    
    def test_agent_task_management(self):
        """Test agent task management."""
        agent = Agent(name="TaskAgent", max_concurrent_tasks=2)
        
        # Add tasks
        assert agent.add_task("task1") == True
        assert agent.add_task("task2") == True
        assert agent.add_task("task3") == False  # Exceeds limit
        
        assert len(agent.current_tasks) == 2
        assert agent.status == AgentStatus.BUSY
        
        # Remove task
        agent.remove_task("task1")
        assert len(agent.current_tasks) == 1
        
        # Remove all tasks
        agent.remove_task("task2")
        assert len(agent.current_tasks) == 0
        assert agent.status == AgentStatus.IDLE
    
    def test_agent_performance_update(self):
        """Test performance metrics update."""
        agent = Agent(name="PerfAgent")
        
        # Update performance
        agent.update_performance(True, 1.5)  # Success, 1.5s execution
        
        metrics = agent.performance_metrics
        assert metrics["tasks_completed"] == 1
        assert metrics["tasks_failed"] == 0
        assert metrics["avg_response_time"] == 1.5
        assert metrics["success_rate"] == 1.0
        
        # Add failure
        agent.update_performance(False, 2.0)
        
        assert metrics["tasks_completed"] == 1
        assert metrics["tasks_failed"] == 1
        assert metrics["success_rate"] == 0.5


class TestMessage:
    """Test Message model functionality."""
    
    def test_message_creation(self):
        """Test basic message creation."""
        message = Message(
            sender="agent1",
            recipient="agent2",
            content="Hello",
            message_type=MessageType.TASK.value
        )
        
        assert message.sender == "agent1"
        assert message.recipient == "agent2"
        assert message.content == "Hello"
        assert message.message_type == MessageType.TASK.value
        assert isinstance(message.id, str)
    
    def test_message_serialization(self):
        """Test message serialization."""
        message = Message(
            sender="test",
            recipient="receiver",
            content={"data": "test"}
        )
        
        # Test to_dict
        msg_dict = message.to_dict()
        assert "id" in msg_dict
        assert msg_dict["sender"] == "test"
        
        # Test to_json
        msg_json = message.to_json()
        parsed = json.loads(msg_json)
        assert parsed["recipient"] == "receiver"
    
    def test_message_from_dict(self):
        """Test message creation from dictionary."""
        msg_data = {
            "id": "msg-123",
            "sender": "sender",
            "recipient": "recipient",
            "content": "test content",
            "message_type": "task"
        }
        
        message = Message.from_dict(msg_data)
        assert message.id == "msg-123"
        assert message.content == "test content"
    
    def test_message_ttl_expiry(self):
        """Test message TTL expiry logic."""
        # Create message with 1 second TTL
        message = Message(
            sender="test",
            recipient="test",
            content="test",
            ttl=1
        )
        
        # Should not be expired immediately
        assert not message.is_expired()
        
        # Test with past timestamp (simulate expiry)
        past_time = (datetime.now() - timedelta(seconds=2)).isoformat()
        message.timestamp = past_time
        
        # Should be expired now
        assert message.is_expired()


class TestTool:
    """Test Tool model functionality."""
    
    def test_tool_creation(self):
        """Test basic tool creation."""
        def sample_function(x: int) -> int:
            return x * 2
        
        tool = Tool(
            name="multiply_by_two",
            description="Multiply number by 2",
            function=sample_function,
            parameters={"x": {"type": "integer", "required": True}}
        )
        
        assert tool.name == "multiply_by_two"
        assert tool.function == sample_function
        assert tool.category == ToolCategory.GENERAL.value
    
    def test_tool_execution(self):
        """Test tool execution."""
        def add_numbers(a: int, b: int) -> int:
            return a + b
        
        tool = Tool(
            name="add",
            description="Add two numbers",
            function=add_numbers,
            parameters={
                "a": {"type": "integer", "required": True},
                "b": {"type": "integer", "required": True}
            }
        )
        
        result = tool.execute(a=5, b=3)
        assert result == 8
        assert tool.usage_count == 1
    
    def test_tool_parameter_validation(self):
        """Test tool parameter validation."""
        def test_func(required_param: str, optional_param: str = "default"):
            return f"{required_param}_{optional_param}"
        
        tool = Tool(
            name="test_validation",
            description="Test validation",
            function=test_func,
            parameters={
                "required_param": {"type": "string", "required": True},
                "optional_param": {"type": "string", "required": False}
            }
        )
        
        # Valid parameters
        assert tool.validate_parameters({"required_param": "test"}) == True
        
        # Missing required parameter
        with pytest.raises(ValueError):
            tool.validate_parameters({"optional_param": "test"})
    
    def test_tool_serialization(self):
        """Test tool serialization (excluding function)."""
        def dummy_func():
            return "dummy"
        
        tool = Tool(
            name="serializable",
            description="Test serialization",
            function=dummy_func,
            category=ToolCategory.UTILITIES.value
        )
        
        tool_dict = tool.to_dict()
        
        # Function should be excluded from serialization
        assert "function" not in tool_dict
        assert tool_dict["name"] == "serializable"
        assert tool_dict["category"] == ToolCategory.UTILITIES.value


class TestEnums:
    """Test enum functionality."""
    
    def test_agent_status_enum(self):
        """Test AgentStatus enum values."""
        assert AgentStatus.IDLE.value == "idle"
        assert AgentStatus.RUNNING.value == "running"
        assert AgentStatus.ERROR.value == "error"
    
    def test_message_type_enum(self):
        """Test MessageType enum values."""
        assert MessageType.TASK.value == "task"
        assert MessageType.RESPONSE.value == "response"
        assert MessageType.ERROR.value == "error"
    
    def test_tool_category_enum(self):
        """Test ToolCategory enum values."""
        assert ToolCategory.GENERAL.value == "general"
        assert ToolCategory.INFORMATION.value == "information"
        assert ToolCategory.UTILITIES.value == "utilities"


if __name__ == "__main__":
    pytest.main([__file__])