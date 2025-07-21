#!/usr/bin/env python3
"""
Agentic AI Development Toolkit
A comprehensive toolkit for developing and managing agentic AI systems.
"""

import os
import json
import uuid
import time
import asyncio
import threading
from datetime import datetime
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, asdict
from enum import Enum
import openai

class AgentStatus(Enum):
    IDLE = "idle"
    RUNNING = "running"
    WAITING = "waiting"
    ERROR = "error"
    STOPPED = "stopped"

@dataclass
class Message:
    id: str
    sender: str
    recipient: str
    content: Any
    message_type: str
    timestamp: str
    metadata: Dict[str, Any] = None

@dataclass
class Tool:
    name: str
    description: str
    function: Callable
    parameters: Dict[str, Any]
    category: str = "general"

@dataclass
class Agent:
    id: str
    name: str
    description: str
    status: AgentStatus
    tools: List[str]
    created_at: str
    last_activity: str
    metadata: Dict[str, Any] = None

class ToolRegistry:
    def __init__(self):
        """Initialize the tool registry."""
        self.tools = {}
        self.register_default_tools()
    
    def register_tool(self, tool: Tool):
        """Register a new tool."""
        self.tools[tool.name] = tool
        print(f"Tool '{tool.name}' registered successfully")
    
    def get_tool(self, name: str) -> Optional[Tool]:
        """Get a tool by name."""
        return self.tools.get(name)
    
    def list_tools(self) -> List[str]:
        """List all available tools."""
        return list(self.tools.keys())
    
    def execute_tool(self, name: str, **kwargs) -> Any:
        """Execute a tool with given parameters."""
        tool = self.get_tool(name)
        if not tool:
            raise ValueError(f"Tool '{name}' not found")
        
        try:
            return tool.function(**kwargs)
        except Exception as e:
            raise RuntimeError(f"Error executing tool '{name}': {str(e)}")
    
    def register_default_tools(self):
        """Register default tools."""
        # Web search tool
        def web_search(query: str) -> Dict[str, Any]:
            return {
                "query": query,
                "results": [
                    {"title": f"Result for {query}", "url": "https://example.com", "snippet": "Sample result"}
                ],
                "timestamp": datetime.now().isoformat()
            }
        
        self.register_tool(Tool(
            name="web_search",
            description="Search the web for information",
            function=web_search,
            parameters={"query": {"type": "string", "description": "Search query"}},
            category="information"
        ))
        
        # File operations tool
        def read_file(filepath: str) -> str:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    return f.read()
            except Exception as e:
                return f"Error reading file: {str(e)}"
        
        self.register_tool(Tool(
            name="read_file",
            description="Read content from a file",
            function=read_file,
            parameters={"filepath": {"type": "string", "description": "Path to the file"}},
            category="file_operations"
        ))
        
        # Calculator tool
        def calculate(expression: str) -> float:
            try:
                # Simple calculator (be careful with eval in production)
                allowed_chars = set('0123456789+-*/.() ')
                if all(c in allowed_chars for c in expression):
                    return eval(expression)
                else:
                    raise ValueError("Invalid characters in expression")
            except Exception as e:
                raise ValueError(f"Calculation error: {str(e)}")
        
        self.register_tool(Tool(
            name="calculate",
            description="Perform mathematical calculations",
            function=calculate,
            parameters={"expression": {"type": "string", "description": "Mathematical expression"}},
            category="utilities"
        ))

class CommunicationBus:
    def __init__(self):
        """Initialize the communication bus."""
        self.message_queue = asyncio.Queue()
        self.subscribers = {}
        self.message_history = []
        self.running = False
    
    def subscribe(self, agent_id: str, callback: Callable):
        """Subscribe an agent to receive messages."""
        self.subscribers[agent_id] = callback
    
    def unsubscribe(self, agent_id: str):
        """Unsubscribe an agent from receiving messages."""
        if agent_id in self.subscribers:
            del self.subscribers[agent_id]
    
    async def send_message(self, message: Message):
        """Send a message through the bus."""
        await self.message_queue.put(message)
        self.message_history.append(message)
    
    async def start(self):
        """Start the communication bus."""
        self.running = True
        while self.running:
            try:
                message = await asyncio.wait_for(self.message_queue.get(), timeout=1.0)
                await self.deliver_message(message)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                print(f"Communication bus error: {str(e)}")
    
    async def deliver_message(self, message: Message):
        """Deliver a message to the recipient."""
        if message.recipient in self.subscribers:
            try:
                await self.subscribers[message.recipient](message)
            except Exception as e:
                print(f"Error delivering message to {message.recipient}: {str(e)}")
        elif message.recipient == "broadcast":
            # Broadcast to all subscribers
            for agent_id, callback in self.subscribers.items():
                if agent_id != message.sender:
                    try:
                        await callback(message)
                    except Exception as e:
                        print(f"Error broadcasting to {agent_id}: {str(e)}")
    
    def stop(self):
        """Stop the communication bus."""
        self.running = False
    
    def get_message_history(self, agent_id: str = None) -> List[Message]:
        """Get message history for an agent or all messages."""
        if agent_id:
            return [msg for msg in self.message_history 
                   if msg.sender == agent_id or msg.recipient == agent_id]
        return self.message_history

class AgentManager:
    def __init__(self):
        """Initialize the agent manager."""
        self.agents = {}
        self.tool_registry = ToolRegistry()
        self.communication_bus = CommunicationBus()
        self.client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.running_tasks = {}
    
    def create_agent(self, name: str, description: str, tools: List[str] = None) -> str:
        """Create a new agent."""
        agent_id = str(uuid.uuid4())
        
        # Validate tools
        available_tools = self.tool_registry.list_tools()
        agent_tools = tools or []
        
        for tool in agent_tools:
            if tool not in available_tools:
                raise ValueError(f"Tool '{tool}' not available")
        
        agent = Agent(
            id=agent_id,
            name=name,
            description=description,
            status=AgentStatus.IDLE,
            tools=agent_tools,
            created_at=datetime.now().isoformat(),
            last_activity=datetime.now().isoformat()
        )
        
        self.agents[agent_id] = agent
        
        # Subscribe agent to communication bus
        self.communication_bus.subscribe(agent_id, self.handle_agent_message)
        
        print(f"Agent '{name}' created with ID: {agent_id}")
        return agent_id
    
    def get_agent(self, agent_id: str) -> Optional[Agent]:
        """Get an agent by ID."""
        return self.agents.get(agent_id)
    
    def list_agents(self) -> List[Agent]:
        """List all agents."""
        return list(self.agents.values())
    
    def update_agent_status(self, agent_id: str, status: AgentStatus):
        """Update agent status."""
        if agent_id in self.agents:
            self.agents[agent_id].status = status
            self.agents[agent_id].last_activity = datetime.now().isoformat()
    
    async def handle_agent_message(self, message: Message):
        """Handle incoming messages for agents."""
        agent = self.get_agent(message.recipient)
        if not agent:
            return
        
        # Process message based on type
        if message.message_type == "task":
            await self.execute_agent_task(message.recipient, message.content)
        elif message.message_type == "tool_request":
            await self.handle_tool_request(message)
    
    async def execute_agent_task(self, agent_id: str, task: str):
        """Execute a task for an agent."""
        agent = self.get_agent(agent_id)
        if not agent:
            return
        
        self.update_agent_status(agent_id, AgentStatus.RUNNING)
        
        try:
            # Use AI to process the task
            response = await self.process_task_with_ai(agent, task)
            
            # Send response back
            response_message = Message(
                id=str(uuid.uuid4()),
                sender=agent_id,
                recipient="system",
                content=response,
                message_type="task_response",
                timestamp=datetime.now().isoformat()
            )
            
            await self.communication_bus.send_message(response_message)
            
            self.update_agent_status(agent_id, AgentStatus.IDLE)
            
        except Exception as e:
            self.update_agent_status(agent_id, AgentStatus.ERROR)
            print(f"Error executing task for agent {agent_id}: {str(e)}")
    
    async def process_task_with_ai(self, agent: Agent, task: str) -> str:
        """Process a task using AI."""
        try:
            # Create context about available tools
            tools_context = ""
            if agent.tools:
                tools_info = []
                for tool_name in agent.tools:
                    tool = self.tool_registry.get_tool(tool_name)
                    if tool:
                        tools_info.append(f"- {tool.name}: {tool.description}")
                tools_context = f"Available tools:\n" + "\n".join(tools_info)
            
            prompt = f"""
            You are an AI agent named '{agent.name}' with the following description:
            {agent.description}
            
            {tools_context}
            
            Task: {task}
            
            Please process this task and provide a response. If you need to use any tools,
            indicate which tool you would use and with what parameters.
            """
            
            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are a helpful AI agent."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            return f"Error processing task: {str(e)}"
    
    async def handle_tool_request(self, message: Message):
        """Handle tool execution requests."""
        try:
            tool_name = message.content.get("tool")
            parameters = message.content.get("parameters", {})
            
            result = self.tool_registry.execute_tool(tool_name, **parameters)
            
            # Send result back
            response_message = Message(
                id=str(uuid.uuid4()),
                sender="system",
                recipient=message.sender,
                content={"tool_result": result},
                message_type="tool_response",
                timestamp=datetime.now().isoformat()
            )
            
            await self.communication_bus.send_message(response_message)
            
        except Exception as e:
            # Send error response
            error_message = Message(
                id=str(uuid.uuid4()),
                sender="system",
                recipient=message.sender,
                content={"error": str(e)},
                message_type="tool_error",
                timestamp=datetime.now().isoformat()
            )
            
            await self.communication_bus.send_message(error_message)
    
    async def send_task_to_agent(self, agent_id: str, task: str):
        """Send a task to an agent."""
        message = Message(
            id=str(uuid.uuid4()),
            sender="system",
            recipient=agent_id,
            content=task,
            message_type="task",
            timestamp=datetime.now().isoformat()
        )
        
        await self.communication_bus.send_message(message)
    
    def get_agent_statistics(self) -> Dict[str, Any]:
        """Get statistics about agents."""
        total_agents = len(self.agents)
        status_counts = {}
        
        for agent in self.agents.values():
            status = agent.status.value
            status_counts[status] = status_counts.get(status, 0) + 1
        
        return {
            "total_agents": total_agents,
            "status_distribution": status_counts,
            "total_messages": len(self.communication_bus.message_history),
            "available_tools": len(self.tool_registry.tools)
        }
    
    def export_agent_data(self, filename: str):
        """Export agent data to file."""
        data = {
            "agents": [asdict(agent) for agent in self.agents.values()],
            "message_history": [asdict(msg) for msg in self.communication_bus.message_history],
            "export_timestamp": datetime.now().isoformat()
        }
        
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        
        print(f"Agent data exported to {filename}")

async def main():
    """Main function to run the agentic AI development toolkit."""
    print("Agentic AI Development Toolkit")
    print("=" * 40)
    
    # Initialize the agent manager
    manager = AgentManager()
    
    # Start the communication bus
    bus_task = asyncio.create_task(manager.communication_bus.start())
    
    try:
        while True:
            print("\nOptions:")
            print("1. Create agent")
            print("2. List agents")
            print("3. Send task to agent")
            print("4. View agent statistics")
            print("5. List available tools")
            print("6. View message history")
            print("7. Export agent data")
            print("8. Quit")
            
            choice = input("\nSelect an option (1-8): ")
            
            if choice == '1':
                name = input("Agent name: ")
                description = input("Agent description: ")
                
                print("Available tools:", ", ".join(manager.tool_registry.list_tools()))
                tools_input = input("Tools (comma-separated, or press Enter for none): ")
                tools = [t.strip() for t in tools_input.split(",")] if tools_input else []
                
                try:
                    agent_id = manager.create_agent(name, description, tools)
                    print(f"Agent created successfully with ID: {agent_id}")
                except Exception as e:
                    print(f"Error creating agent: {str(e)}")
            
            elif choice == '2':
                agents = manager.list_agents()
                if agents:
                    print(f"\nAgents ({len(agents)}):")
                    for agent in agents:
                        print(f"  {agent.name} ({agent.id[:8]}...)")
                        print(f"    Status: {agent.status.value}")
                        print(f"    Tools: {', '.join(agent.tools) if agent.tools else 'None'}")
                        print(f"    Created: {agent.created_at}")
                else:
                    print("No agents found.")
            
            elif choice == '3':
                agents = manager.list_agents()
                if not agents:
                    print("No agents available.")
                    continue
                
                print("Available agents:")
                for i, agent in enumerate(agents):
                    print(f"  {i+1}. {agent.name} ({agent.status.value})")
                
                try:
                    agent_idx = int(input("Select agent (number): ")) - 1
                    if 0 <= agent_idx < len(agents):
                        agent = agents[agent_idx]
                        task = input("Enter task: ")
                        
                        await manager.send_task_to_agent(agent.id, task)
                        print("Task sent to agent.")
                        
                        # Wait a moment for processing
                        await asyncio.sleep(2)
                    else:
                        print("Invalid agent selection.")
                except ValueError:
                    print("Invalid input.")
            
            elif choice == '4':
                stats = manager.get_agent_statistics()
                print("\nAgent Statistics:")
                for key, value in stats.items():
                    print(f"  {key}: {value}")
            
            elif choice == '5':
                tools = manager.tool_registry.list_tools()
                print(f"\nAvailable Tools ({len(tools)}):")
                for tool_name in tools:
                    tool = manager.tool_registry.get_tool(tool_name)
                    print(f"  {tool.name}: {tool.description} (Category: {tool.category})")
            
            elif choice == '6':
                history = manager.communication_bus.get_message_history()
                print(f"\nMessage History ({len(history)} messages):")
                for msg in history[-10:]:  # Show last 10 messages
                    print(f"  {msg.timestamp}: {msg.sender} -> {msg.recipient}")
                    print(f"    Type: {msg.message_type}")
                    print(f"    Content: {str(msg.content)[:100]}...")
            
            elif choice == '7':
                filename = input("Export filename (default: agent_data.json): ") or "agent_data.json"
                manager.export_agent_data(filename)
            
            elif choice == '8':
                break
            
            else:
                print("Invalid option. Please try again.")
    
    finally:
        # Stop the communication bus
        manager.communication_bus.stop()
        bus_task.cancel()
        try:
            await bus_task
        except asyncio.CancelledError:
            pass

if __name__ == "__main__":
    asyncio.run(main())

