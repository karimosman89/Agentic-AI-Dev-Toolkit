#!/usr/bin/env python3
"""
Advanced Agent Manager for Agentic AI Development Toolkit
=========================================================

Enterprise-grade agent lifecycle management with advanced orchestration,
monitoring, load balancing, and intelligent task distribution.

Author: Karim Osman
License: MIT
"""

import os
import json
import uuid
import time
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Callable, Tuple
from dataclasses import asdict
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# AI providers
import openai
try:
    import anthropic
except ImportError:
    anthropic = None

from .models import Agent, Message, Tool, AgentStatus, MessageType, TaskCreate
from .tool_registry import ToolRegistry
from .communication_bus import CommunicationBus
from .config import get_settings


class AgentManager:
    """
    Advanced Agent Manager with enterprise-grade features.
    
    Features:
    - Intelligent agent creation and lifecycle management
    - Advanced task orchestration and load balancing
    - Multi-provider AI support (OpenAI, Anthropic)
    - Real-time monitoring and metrics collection
    - Fault tolerance and error recovery
    - Scalable architecture with async support
    """
    
    def __init__(self, settings=None):
        """Initialize the advanced agent manager."""
        self.settings = settings or get_settings()
        self.agents: Dict[str, Agent] = {}
        self.tool_registry = ToolRegistry()
        self.communication_bus = CommunicationBus()
        self.running_tasks: Dict[str, asyncio.Task] = {}
        self.task_queue = asyncio.Queue(maxsize=self.settings.message_queue_size)
        self.executor = ThreadPoolExecutor(max_workers=self.settings.max_concurrent_tasks)
        
        # AI Clients
        self._setup_ai_clients()
        
        # Monitoring
        self.metrics = {
            "agents_created": 0,
            "tasks_executed": 0,
            "tasks_failed": 0,
            "total_execution_time": 0.0,
            "active_agents": 0,
            "messages_sent": 0,
            "tools_executed": 0,
            "start_time": datetime.now().isoformat()
        }
        
        # Setup logging
        self.logger = logging.getLogger(__name__)
        self._setup_logging()
        
        self.logger.info("🚀 Advanced Agent Manager initialized")
    
    def _setup_ai_clients(self):
        """Setup AI provider clients."""
        self.ai_clients = {}
        
        # OpenAI setup
        openai_config = self.settings.get_openai_config()
        if openai_config:
            self.ai_clients['openai'] = openai.OpenAI(api_key=openai_config['api_key'])
            self.logger.info("✅ OpenAI client configured")
        
        # Anthropic setup  
        anthropic_config = self.settings.get_anthropic_config()
        if anthropic_config and anthropic:
            self.ai_clients['anthropic'] = anthropic.Anthropic(api_key=anthropic_config['api_key'])
            self.logger.info("✅ Anthropic client configured")
        
        if not self.ai_clients:
            self.logger.warning("⚠️  No AI providers configured")
    
    def _setup_logging(self):
        """Setup structured logging."""
        logging.basicConfig(
            level=getattr(logging, self.settings.log_level),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(f"{self.settings.logs_directory}/agent_manager.log"),
                logging.StreamHandler()
            ]
        )
    
    async def create_agent(
        self, 
        name: str, 
        description: str, 
        agent_type: str = "general",
        tools: List[str] = None, 
        capabilities: List[str] = None,
        configuration: Dict[str, Any] = None,
        **kwargs
    ) -> str:
        """
        Create a new intelligent agent with advanced configuration.
        
        Args:
            name: Agent name (must be unique)
            description: Agent description and purpose
            agent_type: Type of agent (general, specialist, coordinator)
            tools: List of tool names the agent can use
            capabilities: List of agent capabilities
            configuration: Agent-specific configuration
            **kwargs: Additional agent parameters
            
        Returns:
            Agent ID if successful
            
        Raises:
            ValueError: If agent creation fails validation
            RuntimeError: If maximum agents exceeded
        """
        if len(self.agents) >= self.settings.max_agents:
            raise RuntimeError(f"Maximum agents limit ({self.settings.max_agents}) reached")
        
        # Validate tools
        available_tools = self.tool_registry.list_tools()
        agent_tools = tools or []
        
        for tool in agent_tools:
            if tool not in available_tools:
                raise ValueError(f"Tool '{tool}' not available. Available tools: {available_tools}")
        
        # Generate unique agent ID
        agent_id = str(uuid.uuid4())
        
        # Create agent with enhanced attributes
        agent = Agent(
            id=agent_id,
            name=name,
            description=description,
            agent_type=agent_type,
            status=AgentStatus.IDLE,
            tools=agent_tools,
            capabilities=capabilities or [],
            configuration=configuration or {},
            created_at=datetime.now().isoformat(),
            last_activity=datetime.now().isoformat(),
            **kwargs
        )
        
        # Register agent
        self.agents[agent_id] = agent
        self.metrics["agents_created"] += 1
        self.metrics["active_agents"] = len([a for a in self.agents.values() 
                                           if a.status != AgentStatus.OFFLINE])
        
        # Subscribe to communication bus
        await self.communication_bus.subscribe(agent_id, self._handle_agent_message)
        
        self.logger.info(f"🤖 Agent '{name}' created successfully (ID: {agent_id[:8]}...)")
        
        # Send welcome message
        welcome_msg = Message(
            sender="system",
            recipient=agent_id,
            content=f"Welcome {name}! You have been successfully created.",
            message_type=MessageType.STATUS_UPDATE.value
        )
        await self.communication_bus.send_message(welcome_msg)
        
        return agent_id
    
    def get_agent(self, agent_id: str) -> Optional[Agent]:
        """Get agent by ID with validation."""
        return self.agents.get(agent_id)
    
    def get_agent_by_name(self, name: str) -> Optional[Agent]:
        """Get agent by name."""
        for agent in self.agents.values():
            if agent.name == name:
                return agent
        return None
    
    def list_agents(self, status_filter: AgentStatus = None, agent_type: str = None) -> List[Agent]:
        """
        List agents with optional filtering.
        
        Args:
            status_filter: Filter by agent status
            agent_type: Filter by agent type
            
        Returns:
            Filtered list of agents
        """
        agents = list(self.agents.values())
        
        if status_filter:
            agents = [a for a in agents if a.status == status_filter]
        
        if agent_type:
            agents = [a for a in agents if a.agent_type == agent_type]
        
        return agents
    
    def get_available_agents(self, tool_name: str = None, capability: str = None) -> List[Agent]:
        """
        Get available agents that can handle specific requirements.
        
        Args:
            tool_name: Required tool capability
            capability: Required agent capability
            
        Returns:
            List of available agents matching criteria
        """
        available = [a for a in self.agents.values() if a.is_available()]
        
        if tool_name:
            available = [a for a in available if a.can_handle_tool(tool_name)]
        
        if capability:
            available = [a for a in available if a.has_capability(capability)]
        
        return available
    
    async def update_agent_status(self, agent_id: str, status: AgentStatus, metadata: Dict = None):
        """Update agent status with optional metadata."""
        if agent_id not in self.agents:
            raise ValueError(f"Agent {agent_id} not found")
        
        agent = self.agents[agent_id]
        old_status = agent.status
        agent.update_status(status)
        
        if metadata:
            agent.metadata.update(metadata)
        
        self.logger.info(f"🔄 Agent {agent.name} status: {old_status.value} → {status.value}")
        
        # Broadcast status update
        status_msg = Message(
            sender="system",
            recipient="broadcast",
            content={
                "agent_id": agent_id,
                "old_status": old_status.value,
                "new_status": status.value,
                "metadata": metadata
            },
            message_type=MessageType.STATUS_UPDATE.value
        )
        await self.communication_bus.send_message(status_msg)
    
    async def _handle_agent_message(self, message: Message):
        """Handle incoming messages for agents."""
        agent = self.get_agent(message.recipient)
        if not agent:
            self.logger.warning(f"⚠️  Message for unknown agent: {message.recipient}")
            return
        
        try:
            # Route message based on type
            if message.message_type == MessageType.TASK.value:
                await self._execute_agent_task(message.recipient, message.content, message.metadata)
            elif message.message_type == MessageType.TOOL_REQUEST.value:
                await self._handle_tool_request(message)
            elif message.message_type == MessageType.HEARTBEAT.value:
                await self._handle_heartbeat(message)
            else:
                self.logger.debug(f"📨 Unhandled message type: {message.message_type}")
                
        except Exception as e:
            self.logger.error(f"❌ Error handling message: {str(e)}")
            await self._send_error_response(message.sender, str(e))
    
    async def _execute_agent_task(self, agent_id: str, task_content: Any, metadata: Dict = None):
        """
        Execute a task for an agent with advanced error handling and monitoring.
        
        Args:
            agent_id: Target agent ID
            task_content: Task to execute
            metadata: Additional task metadata
        """
        agent = self.get_agent(agent_id)
        if not agent:
            return
        
        task_id = str(uuid.uuid4())
        start_time = time.time()
        
        try:
            # Check if agent can handle the task
            if not agent.add_task(task_id):
                await self._send_error_response(
                    agent_id, 
                    f"Agent {agent.name} is at maximum task capacity"
                )
                return
            
            await self.update_agent_status(agent_id, AgentStatus.RUNNING)
            self.metrics["tasks_executed"] += 1
            
            # Process task with AI
            response = await self._process_task_with_ai(agent, task_content, metadata)
            
            # Send response
            response_message = Message(
                sender=agent_id,
                recipient=metadata.get("reply_to", "system"),
                content={
                    "task_id": task_id,
                    "response": response,
                    "execution_time": time.time() - start_time,
                    "agent_name": agent.name
                },
                message_type=MessageType.RESPONSE.value,
                metadata={"original_task": task_content}
            )
            
            await self.communication_bus.send_message(response_message)
            
            # Update metrics
            execution_time = time.time() - start_time
            agent.update_performance(True, execution_time)
            self.metrics["total_execution_time"] += execution_time
            
            self.logger.info(f"✅ Task completed by {agent.name} in {execution_time:.2f}s")
            
        except Exception as e:
            execution_time = time.time() - start_time
            agent.update_performance(False, execution_time)
            self.metrics["tasks_failed"] += 1
            
            await self.update_agent_status(agent_id, AgentStatus.ERROR)
            await self._send_error_response(agent_id, str(e))
            
            self.logger.error(f"❌ Task failed for {agent.name}: {str(e)}")
            
        finally:
            # Clean up
            agent.remove_task(task_id)
            if agent_id in self.running_tasks:
                del self.running_tasks[agent_id]
    
    async def _process_task_with_ai(self, agent: Agent, task: str, metadata: Dict = None) -> str:
        """
        Process a task using AI with provider selection and fallback.
        
        Args:
            agent: Agent processing the task
            task: Task description
            metadata: Additional context
            
        Returns:
            AI-generated response
        """
        # Build context
        context = self._build_agent_context(agent, metadata)
        
        # Try primary AI provider (OpenAI)
        if 'openai' in self.ai_clients:
            try:
                return await self._process_with_openai(agent, task, context)
            except Exception as e:
                self.logger.warning(f"OpenAI failed, trying fallback: {str(e)}")
        
        # Fallback to Anthropic
        if 'anthropic' in self.ai_clients:
            try:
                return await self._process_with_anthropic(agent, task, context)
            except Exception as e:
                self.logger.error(f"Anthropic failed: {str(e)}")
        
        # Final fallback - simple rule-based response
        return f"Agent {agent.name} received task: {task}. No AI providers available for processing."
    
    def _build_agent_context(self, agent: Agent, metadata: Dict = None) -> str:
        """Build context information for AI processing."""
        context_parts = [
            f"Agent Name: {agent.name}",
            f"Agent Type: {agent.agent_type}",
            f"Description: {agent.description}",
        ]
        
        if agent.capabilities:
            context_parts.append(f"Capabilities: {', '.join(agent.capabilities)}")
        
        if agent.tools:
            tools_info = []
            for tool_name in agent.tools:
                tool = self.tool_registry.get_tool(tool_name)
                if tool:
                    tools_info.append(f"- {tool.name}: {tool.description}")
            if tools_info:
                context_parts.append("Available Tools:")
                context_parts.extend(tools_info)
        
        if metadata:
            context_parts.append(f"Context: {json.dumps(metadata, indent=2)}")
        
        return "\n".join(context_parts)
    
    async def _process_with_openai(self, agent: Agent, task: str, context: str) -> str:
        """Process task using OpenAI."""
        config = self.settings.get_openai_config()
        
        messages = [
            {"role": "system", "content": f"You are {agent.name}, an AI agent. {context}"},
            {"role": "user", "content": task}
        ]
        
        response = self.ai_clients['openai'].chat.completions.create(
            model=config['model'],
            messages=messages,
            temperature=config['temperature'],
            max_tokens=config['max_tokens']
        )
        
        return response.choices[0].message.content
    
    async def _process_with_anthropic(self, agent: Agent, task: str, context: str) -> str:
        """Process task using Anthropic Claude."""
        config = self.settings.get_anthropic_config()
        
        message = f"{context}\n\nTask: {task}"
        
        response = self.ai_clients['anthropic'].messages.create(
            model=config['model'],
            max_tokens=2000,
            messages=[{"role": "user", "content": message}]
        )
        
        return response.content[0].text
    
    async def _handle_tool_request(self, message: Message):
        """Handle tool execution requests with validation and monitoring."""
        try:
            tool_name = message.content.get("tool")
            parameters = message.content.get("parameters", {})
            
            if not tool_name:
                raise ValueError("No tool specified in request")
            
            # Execute tool
            result = self.tool_registry.execute_tool(tool_name, **parameters)
            self.metrics["tools_executed"] += 1
            
            # Send result back
            response_message = Message(
                sender="system",
                recipient=message.sender,
                content={
                    "tool": tool_name,
                    "result": result,
                    "execution_time": datetime.now().isoformat()
                },
                message_type=MessageType.TOOL_RESPONSE.value
            )
            
            await self.communication_bus.send_message(response_message)
            
        except Exception as e:
            await self._send_error_response(message.sender, f"Tool execution failed: {str(e)}")
    
    async def _handle_heartbeat(self, message: Message):
        """Handle agent heartbeat messages."""
        agent = self.get_agent(message.sender)
        if agent:
            agent.update_activity()
            self.logger.debug(f"💓 Heartbeat from {agent.name}")
    
    async def _send_error_response(self, recipient: str, error_message: str):
        """Send error response to recipient."""
        error_msg = Message(
            sender="system",
            recipient=recipient,
            content={"error": error_message},
            message_type=MessageType.ERROR.value
        )
        await self.communication_bus.send_message(error_msg)
    
    async def send_task_to_agent(
        self, 
        agent_id: str, 
        task: str, 
        priority: int = 1,
        metadata: Dict = None
    ):
        """
        Send a task to a specific agent with priority and metadata.
        
        Args:
            agent_id: Target agent ID
            task: Task description
            priority: Task priority (1-4)
            metadata: Additional task metadata
        """
        if agent_id not in self.agents:
            raise ValueError(f"Agent {agent_id} not found")
        
        message = Message(
            sender="system",
            recipient=agent_id,
            content=task,
            message_type=MessageType.TASK.value,
            priority=priority,
            metadata=metadata or {}
        )
        
        await self.communication_bus.send_message(message)
        self.metrics["messages_sent"] += 1
    
    async def broadcast_message(self, content: Any, message_type: str = MessageType.BROADCAST.value):
        """Broadcast message to all agents."""
        message = Message(
            sender="system",
            recipient="broadcast",
            content=content,
            message_type=message_type
        )
        
        await self.communication_bus.send_message(message)
        self.metrics["messages_sent"] += 1
    
    def get_agent_statistics(self) -> Dict[str, Any]:
        """Get comprehensive agent statistics."""
        uptime = (datetime.now() - datetime.fromisoformat(self.metrics["start_time"])).total_seconds()
        
        status_distribution = {}
        for agent in self.agents.values():
            status = agent.status.value
            status_distribution[status] = status_distribution.get(status, 0) + 1
        
        return {
            "total_agents": len(self.agents),
            "active_agents": self.metrics["active_agents"],
            "status_distribution": status_distribution,
            "tasks_executed": self.metrics["tasks_executed"],
            "tasks_failed": self.metrics["tasks_failed"],
            "success_rate": (
                self.metrics["tasks_executed"] / 
                max(1, self.metrics["tasks_executed"] + self.metrics["tasks_failed"])
            ) * 100,
            "total_messages": len(self.communication_bus.message_history),
            "available_tools": len(self.tool_registry.tools),
            "tools_executed": self.metrics["tools_executed"],
            "uptime_seconds": uptime,
            "avg_execution_time": (
                self.metrics["total_execution_time"] / 
                max(1, self.metrics["tasks_executed"])
            ),
            "ai_providers": list(self.ai_clients.keys())
        }
    
    def get_agent_performance(self, agent_id: str) -> Dict[str, Any]:
        """Get detailed performance metrics for a specific agent."""
        agent = self.get_agent(agent_id)
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")
        
        return {
            "agent_id": agent.id,
            "agent_name": agent.name,
            "status": agent.status.value,
            "current_tasks": len(agent.current_tasks),
            "max_concurrent_tasks": agent.max_concurrent_tasks,
            "performance_metrics": agent.performance_metrics,
            "uptime": (
                datetime.now() - 
                datetime.fromisoformat(agent.created_at)
            ).total_seconds(),
            "last_activity": agent.last_activity,
            "tools": agent.tools,
            "capabilities": agent.capabilities
        }
    
    async def shutdown_agent(self, agent_id: str, graceful: bool = True):
        """Shutdown an agent gracefully or forcefully."""
        if agent_id not in self.agents:
            raise ValueError(f"Agent {agent_id} not found")
        
        agent = self.agents[agent_id]
        
        if graceful and agent.current_tasks:
            # Wait for current tasks to complete
            self.logger.info(f"🔄 Gracefully shutting down {agent.name}...")
            await self.update_agent_status(agent_id, AgentStatus.STOPPED)
            
            # Wait up to 30 seconds for tasks to complete
            for _ in range(30):
                if not agent.current_tasks:
                    break
                await asyncio.sleep(1)
        
        # Remove from active agents
        await self.update_agent_status(agent_id, AgentStatus.OFFLINE)
        await self.communication_bus.unsubscribe(agent_id)
        
        # Cancel any running tasks
        if agent_id in self.running_tasks:
            self.running_tasks[agent_id].cancel()
            del self.running_tasks[agent_id]
        
        self.logger.info(f"🔴 Agent {agent.name} shutdown complete")
    
    async def export_agent_data(self, filename: str = None, agent_ids: List[str] = None):
        """
        Export agent data with optional filtering.
        
        Args:
            filename: Output filename (default: timestamp-based)
            agent_ids: List of specific agent IDs to export (default: all)
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{self.settings.data_directory}/agents_export_{timestamp}.json"
        
        # Select agents to export
        if agent_ids:
            agents_to_export = [self.agents[aid] for aid in agent_ids if aid in self.agents]
        else:
            agents_to_export = list(self.agents.values())
        
        export_data = {
            "metadata": {
                "export_timestamp": datetime.now().isoformat(),
                "total_agents": len(agents_to_export),
                "exporter": "Agentic AI Dev Toolkit v2.0",
                "statistics": self.get_agent_statistics()
            },
            "agents": [agent.to_dict() for agent in agents_to_export],
            "message_history": [
                msg.to_dict() for msg in self.communication_bus.message_history[-1000:]
            ],
            "tools": [tool.to_dict() for tool in self.tool_registry.tools.values()]
        }
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, default=str)
        
        self.logger.info(f"📄 Agent data exported to {filename}")
        return filename
    
    async def cleanup(self):
        """Cleanup resources and shutdown gracefully."""
        self.logger.info("🧹 Starting cleanup...")
        
        # Shutdown all agents gracefully
        for agent_id in list(self.agents.keys()):
            await self.shutdown_agent(agent_id, graceful=True)
        
        # Stop communication bus
        self.communication_bus.stop()
        
        # Shutdown executor
        self.executor.shutdown(wait=True)
        
        self.logger.info("✅ Cleanup completed")