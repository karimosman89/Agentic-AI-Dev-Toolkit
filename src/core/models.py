#!/usr/bin/env python3
"""
Core Data Models for Agentic AI Development Toolkit
===================================================

Professional data models with validation, serialization, and database support.

Author: Karim Osman  
License: MIT
"""

import uuid
from datetime import datetime
from typing import Dict, List, Any, Optional, Callable, Union
from dataclasses import dataclass, field, asdict
from enum import Enum
from pydantic import BaseModel, Field, validator
import json


class AgentStatus(Enum):
    """Agent execution status."""
    IDLE = "idle"
    RUNNING = "running"
    WAITING = "waiting"
    ERROR = "error"
    STOPPED = "stopped"
    BUSY = "busy"
    OFFLINE = "offline"


class MessageType(Enum):
    """Message types for agent communication."""
    TASK = "task"
    RESPONSE = "response"
    TOOL_REQUEST = "tool_request"
    TOOL_RESPONSE = "tool_response"
    ERROR = "error"
    BROADCAST = "broadcast"
    HEARTBEAT = "heartbeat"
    STATUS_UPDATE = "status_update"


class ToolCategory(Enum):
    """Tool categories for organization."""
    GENERAL = "general"
    INFORMATION = "information"
    FILE_OPERATIONS = "file_operations"
    WEB_SCRAPING = "web_scraping"
    DATA_PROCESSING = "data_processing"
    COMMUNICATION = "communication"
    AI_MODELS = "ai_models"
    UTILITIES = "utilities"
    CUSTOM = "custom"


@dataclass
class Message:
    """
    Inter-agent communication message.
    
    Supports various message types and metadata for comprehensive
    agent-to-agent communication with full traceability.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    sender: str = ""
    recipient: str = ""
    content: Any = None
    message_type: str = MessageType.TASK.value
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)
    priority: int = 1  # 1=low, 2=normal, 3=high, 4=critical
    ttl: Optional[int] = None  # Time to live in seconds
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert message to dictionary."""
        return asdict(self)
    
    def to_json(self) -> str:
        """Convert message to JSON string."""
        return json.dumps(self.to_dict(), default=str)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Message':
        """Create message from dictionary.""" 
        return cls(**data)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'Message':
        """Create message from JSON string."""
        return cls.from_dict(json.loads(json_str))
    
    def is_expired(self) -> bool:
        """Check if message has expired based on TTL."""
        if not self.ttl:
            return False
        
        created_time = datetime.fromisoformat(self.timestamp.replace('Z', '+00:00'))
        return (datetime.now() - created_time).total_seconds() > self.ttl


@dataclass
class Tool:
    """
    Agent tool definition with comprehensive metadata.
    
    Represents executable tools that agents can use to perform tasks,
    with support for parameters, validation, and categorization.
    """
    name: str
    description: str
    function: Callable
    parameters: Dict[str, Any] = field(default_factory=dict)
    category: str = ToolCategory.GENERAL.value
    version: str = "1.0.0"
    author: str = "System"
    requires_auth: bool = False
    async_execution: bool = False
    timeout: int = 30  # seconds
    cost_estimate: float = 0.0  # Estimated execution cost
    usage_count: int = 0
    last_used: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert tool to dictionary (excluding function)."""
        data = asdict(self)
        data.pop('function', None)  # Remove function for serialization
        return data
    
    def execute(self, **kwargs) -> Any:
        """Execute the tool with given parameters."""
        self.usage_count += 1
        self.last_used = datetime.now().isoformat()
        return self.function(**kwargs)
    
    def validate_parameters(self, params: Dict[str, Any]) -> bool:
        """Validate parameters against tool requirements."""
        required_params = {k: v for k, v in self.parameters.items() 
                         if v.get('required', False)}
        
        for param_name, param_info in required_params.items():
            if param_name not in params:
                raise ValueError(f"Missing required parameter: {param_name}")
        
        return True


@dataclass
class Agent:
    """
    Agentic AI agent with comprehensive state management.
    
    Represents an autonomous AI agent with tools, capabilities, and 
    full lifecycle management including monitoring and persistence.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Unnamed Agent"
    description: str = "AI Agent"
    status: AgentStatus = AgentStatus.IDLE
    tools: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_activity: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Enhanced attributes
    agent_type: str = "general"  # general, specialist, coordinator
    capabilities: List[str] = field(default_factory=list)
    max_concurrent_tasks: int = 3
    current_tasks: List[str] = field(default_factory=list)
    performance_metrics: Dict[str, Any] = field(default_factory=dict)
    configuration: Dict[str, Any] = field(default_factory=dict)
    version: str = "1.0.0"
    owner: str = "system"
    tags: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """Initialize performance metrics if not provided."""
        if not self.performance_metrics:
            self.performance_metrics = {
                "tasks_completed": 0,
                "tasks_failed": 0,
                "avg_response_time": 0.0,
                "total_execution_time": 0.0,
                "success_rate": 1.0
            }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert agent to dictionary."""
        data = asdict(self)
        data['status'] = self.status.value if isinstance(self.status, AgentStatus) else self.status
        return data
    
    def to_json(self) -> str:
        """Convert agent to JSON string."""
        return json.dumps(self.to_dict(), default=str)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Agent':
        """Create agent from dictionary."""
        if 'status' in data and isinstance(data['status'], str):
            data['status'] = AgentStatus(data['status'])
        return cls(**data)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'Agent':
        """Create agent from JSON string."""
        return cls.from_dict(json.loads(json_str))
    
    def update_activity(self):
        """Update last activity timestamp."""
        self.last_activity = datetime.now().isoformat()
    
    def update_status(self, status: AgentStatus):
        """Update agent status and activity timestamp."""
        self.status = status
        self.update_activity()
    
    def add_task(self, task_id: str) -> bool:
        """Add a task to current tasks if under limit."""
        if len(self.current_tasks) >= self.max_concurrent_tasks:
            return False
        
        self.current_tasks.append(task_id)
        self.update_status(AgentStatus.BUSY if self.current_tasks else AgentStatus.IDLE)
        return True
    
    def remove_task(self, task_id: str):
        """Remove a task from current tasks."""
        if task_id in self.current_tasks:
            self.current_tasks.remove(task_id)
            self.update_status(AgentStatus.BUSY if self.current_tasks else AgentStatus.IDLE)
    
    def update_performance(self, task_success: bool, execution_time: float):
        """Update performance metrics."""
        metrics = self.performance_metrics
        
        if task_success:
            metrics["tasks_completed"] += 1
        else:
            metrics["tasks_failed"] += 1
        
        # Update average response time
        total_tasks = metrics["tasks_completed"] + metrics["tasks_failed"]
        if total_tasks > 0:
            current_avg = metrics["avg_response_time"]
            metrics["avg_response_time"] = (current_avg * (total_tasks - 1) + execution_time) / total_tasks
            metrics["total_execution_time"] += execution_time
            metrics["success_rate"] = metrics["tasks_completed"] / total_tasks
    
    def can_handle_tool(self, tool_name: str) -> bool:
        """Check if agent can handle a specific tool."""
        return tool_name in self.tools
    
    def has_capability(self, capability: str) -> bool:
        """Check if agent has a specific capability."""
        return capability in self.capabilities
    
    def is_available(self) -> bool:
        """Check if agent is available for new tasks."""
        return (self.status in [AgentStatus.IDLE, AgentStatus.BUSY] and 
                len(self.current_tasks) < self.max_concurrent_tasks)


# Pydantic models for API validation
class AgentCreate(BaseModel):
    """Pydantic model for agent creation."""
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., min_length=1, max_length=500)
    agent_type: str = Field(default="general")
    tools: List[str] = Field(default_factory=list)
    capabilities: List[str] = Field(default_factory=list) 
    max_concurrent_tasks: int = Field(default=3, ge=1, le=10)
    configuration: Dict[str, Any] = Field(default_factory=dict)
    tags: List[str] = Field(default_factory=list)


class AgentUpdate(BaseModel):
    """Pydantic model for agent updates."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, min_length=1, max_length=500)
    status: Optional[str] = None
    tools: Optional[List[str]] = None
    capabilities: Optional[List[str]] = None
    max_concurrent_tasks: Optional[int] = Field(None, ge=1, le=10)
    configuration: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None


class MessageCreate(BaseModel):
    """Pydantic model for message creation."""
    sender: str = Field(..., min_length=1)
    recipient: str = Field(..., min_length=1) 
    content: Any = Field(...)
    message_type: str = Field(default=MessageType.TASK.value)
    priority: int = Field(default=1, ge=1, le=4)
    ttl: Optional[int] = Field(None, ge=1)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ToolCreate(BaseModel):
    """Pydantic model for tool creation."""
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., min_length=1, max_length=500)
    category: str = Field(default=ToolCategory.CUSTOM.value)
    parameters: Dict[str, Any] = Field(default_factory=dict)
    requires_auth: bool = Field(default=False)
    async_execution: bool = Field(default=False)
    timeout: int = Field(default=30, ge=1, le=3600)


class TaskCreate(BaseModel):
    """Pydantic model for task creation."""
    agent_id: str = Field(..., min_length=1)
    task_content: str = Field(..., min_length=1)
    priority: int = Field(default=1, ge=1, le=4)
    timeout: Optional[int] = Field(None, ge=1)
    metadata: Dict[str, Any] = Field(default_factory=dict)