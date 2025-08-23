#!/usr/bin/env python3
"""
Advanced Tool Registry for Agentic AI Development Toolkit
=========================================================

Professional tool management system with dynamic registration, validation,
monitoring, and extensible architecture for custom tool development.

Author: Karim Osman
License: MIT
"""

import os
import json
import time
import asyncio
import logging
import importlib
import inspect
from datetime import datetime
from typing import Dict, List, Any, Optional, Callable, Union
from pathlib import Path
from dataclasses import asdict

from .models import Tool, ToolCategory
from .config import get_settings


class ToolRegistry:
    """
    Advanced tool registry with comprehensive management capabilities.
    
    Features:
    - Dynamic tool registration and discovery
    - Tool validation and parameter checking
    - Usage monitoring and analytics
    - Hot-reload for development
    - Security and permission management
    - Tool categorization and search
    """
    
    def __init__(self, settings=None):
        """Initialize the enhanced tool registry."""
        self.settings = settings or get_settings()
        self.tools: Dict[str, Tool] = {}
        self.tool_modules: Dict[str, Any] = {}
        self.usage_stats: Dict[str, Dict[str, Any]] = {}
        
        # Setup logging
        self.logger = logging.getLogger(__name__)
        
        # Initialize with default tools
        self._register_default_tools()
        
        # Load custom tools if directory exists
        self._load_custom_tools()
        
        self.logger.info(f"🔧 Tool Registry initialized with {len(self.tools)} tools")
    
    def register_tool(self, tool: Tool) -> bool:
        """
        Register a new tool with validation and monitoring setup.
        
        Args:
            tool: Tool instance to register
            
        Returns:
            True if registration successful, False otherwise
            
        Raises:
            ValueError: If tool validation fails
        """
        try:
            # Validate tool
            self._validate_tool(tool)
            
            # Check for naming conflicts
            if tool.name in self.tools:
                self.logger.warning(f"⚠️  Overwriting existing tool: {tool.name}")
            
            # Register tool
            self.tools[tool.name] = tool
            
            # Initialize usage statistics
            self.usage_stats[tool.name] = {
                "total_executions": 0,
                "successful_executions": 0,
                "failed_executions": 0,
                "total_execution_time": 0.0,
                "avg_execution_time": 0.0,
                "last_used": None,
                "registered_at": datetime.now().isoformat()
            }
            
            self.logger.info(f"✅ Tool '{tool.name}' registered successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to register tool '{tool.name}': {str(e)}")
            return False
    
    def _validate_tool(self, tool: Tool):
        """Validate tool configuration and requirements."""
        if not tool.name or not tool.name.strip():
            raise ValueError("Tool name cannot be empty")
        
        if not tool.description or not tool.description.strip():
            raise ValueError("Tool description cannot be empty")
        
        if not callable(tool.function):
            raise ValueError("Tool function must be callable")
        
        # Validate parameters schema
        if tool.parameters:
            for param_name, param_info in tool.parameters.items():
                if not isinstance(param_info, dict):
                    raise ValueError(f"Parameter '{param_name}' must have dict configuration")
                
                if 'type' not in param_info:
                    raise ValueError(f"Parameter '{param_name}' must specify type")
        
        # Validate category
        try:
            ToolCategory(tool.category)
        except ValueError:
            raise ValueError(f"Invalid tool category: {tool.category}")
    
    def get_tool(self, name: str) -> Optional[Tool]:
        """Get a tool by name with access logging."""
        tool = self.tools.get(name)
        if tool:
            self.logger.debug(f"🔍 Tool '{name}' accessed")
        return tool
    
    def list_tools(self, category: str = None, search: str = None) -> List[str]:
        """
        List available tools with optional filtering.
        
        Args:
            category: Filter by tool category
            search: Search in tool names and descriptions
            
        Returns:
            List of tool names matching criteria
        """
        tools = list(self.tools.keys())
        
        if category:
            tools = [name for name in tools 
                    if self.tools[name].category == category]
        
        if search:
            search_lower = search.lower()
            tools = [name for name in tools 
                    if (search_lower in name.lower() or 
                        search_lower in self.tools[name].description.lower())]
        
        return sorted(tools)
    
    def get_tools_by_category(self) -> Dict[str, List[str]]:
        """Get tools organized by category."""
        categories = {}
        for tool_name, tool in self.tools.items():
            category = tool.category
            if category not in categories:
                categories[category] = []
            categories[category].append(tool_name)
        
        return {k: sorted(v) for k, v in categories.items()}
    
    def execute_tool(
        self, 
        name: str, 
        timeout: Optional[int] = None,
        **kwargs
    ) -> Any:
        """
        Execute a tool with comprehensive monitoring and error handling.
        
        Args:
            name: Tool name to execute
            timeout: Optional timeout override
            **kwargs: Tool parameters
            
        Returns:
            Tool execution result
            
        Raises:
            ValueError: If tool not found or parameters invalid
            RuntimeError: If tool execution fails
            TimeoutError: If execution exceeds timeout
        """
        tool = self.get_tool(name)
        if not tool:
            raise ValueError(f"Tool '{name}' not found")
        
        # Validate parameters
        try:
            tool.validate_parameters(kwargs)
        except Exception as e:
            self.usage_stats[name]["failed_executions"] += 1
            raise ValueError(f"Parameter validation failed: {str(e)}")
        
        # Execute with monitoring
        start_time = time.time()
        execution_timeout = timeout or tool.timeout
        
        try:
            self.logger.info(f"🔧 Executing tool '{name}' with params: {kwargs}")
            
            if tool.async_execution:
                # Handle async tools
                if asyncio.iscoroutinefunction(tool.function):
                    result = asyncio.run(
                        asyncio.wait_for(tool.function(**kwargs), timeout=execution_timeout)
                    )
                else:
                    # Wrap sync function for async execution
                    result = asyncio.run(
                        asyncio.wait_for(
                            asyncio.to_thread(tool.function, **kwargs),
                            timeout=execution_timeout
                        )
                    )
            else:
                # Synchronous execution with timeout
                import signal
                
                def timeout_handler(signum, frame):
                    raise TimeoutError(f"Tool execution exceeded {execution_timeout}s")
                
                signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(execution_timeout)
                
                try:
                    result = tool.function(**kwargs)
                finally:
                    signal.alarm(0)  # Cancel alarm
            
            # Update usage statistics
            execution_time = time.time() - start_time
            self._update_usage_stats(name, True, execution_time)
            
            self.logger.info(f"✅ Tool '{name}' executed successfully in {execution_time:.2f}s")
            return result
            
        except TimeoutError:
            execution_time = time.time() - start_time
            self._update_usage_stats(name, False, execution_time)
            raise TimeoutError(f"Tool '{name}' execution timeout ({execution_timeout}s)")
            
        except Exception as e:
            execution_time = time.time() - start_time
            self._update_usage_stats(name, False, execution_time)
            self.logger.error(f"❌ Tool '{name}' execution failed: {str(e)}")
            raise RuntimeError(f"Tool execution failed: {str(e)}")
    
    def _update_usage_stats(self, tool_name: str, success: bool, execution_time: float):
        """Update usage statistics for a tool."""
        stats = self.usage_stats[tool_name]
        
        stats["total_executions"] += 1
        stats["total_execution_time"] += execution_time
        stats["last_used"] = datetime.now().isoformat()
        
        if success:
            stats["successful_executions"] += 1
        else:
            stats["failed_executions"] += 1
        
        # Update average execution time
        if stats["total_executions"] > 0:
            stats["avg_execution_time"] = (
                stats["total_execution_time"] / stats["total_executions"]
            )
        
        # Update tool object usage count
        if tool_name in self.tools:
            self.tools[tool_name].usage_count = stats["total_executions"]
            self.tools[tool_name].last_used = stats["last_used"]
    
    def get_tool_statistics(self, tool_name: str = None) -> Dict[str, Any]:
        """
        Get usage statistics for tools.
        
        Args:
            tool_name: Specific tool name (optional)
            
        Returns:
            Statistics dictionary
        """
        if tool_name:
            if tool_name not in self.usage_stats:
                raise ValueError(f"No statistics for tool '{tool_name}'")
            return self.usage_stats[tool_name].copy()
        
        # Return aggregate statistics
        total_executions = sum(stats["total_executions"] for stats in self.usage_stats.values())
        successful_executions = sum(stats["successful_executions"] for stats in self.usage_stats.values())
        
        return {
            "total_tools": len(self.tools),
            "total_executions": total_executions,
            "successful_executions": successful_executions,
            "failed_executions": total_executions - successful_executions,
            "success_rate": (successful_executions / max(1, total_executions)) * 100,
            "most_used_tools": self._get_most_used_tools(5),
            "categories": list(set(tool.category for tool in self.tools.values()))
        }
    
    def _get_most_used_tools(self, limit: int) -> List[Dict[str, Any]]:
        """Get most frequently used tools."""
        tool_usage = [
            {
                "name": name,
                "executions": stats["total_executions"],
                "success_rate": (
                    stats["successful_executions"] / max(1, stats["total_executions"])
                ) * 100
            }
            for name, stats in self.usage_stats.items()
        ]
        
        return sorted(tool_usage, key=lambda x: x["executions"], reverse=True)[:limit]
    
    def unregister_tool(self, name: str) -> bool:
        """
        Unregister a tool and clean up its data.
        
        Args:
            name: Tool name to unregister
            
        Returns:
            True if successful, False if tool not found
        """
        if name not in self.tools:
            return False
        
        del self.tools[name]
        if name in self.usage_stats:
            del self.usage_stats[name]
        
        self.logger.info(f"🗑️  Tool '{name}' unregistered")
        return True
    
    def reload_tool(self, name: str) -> bool:
        """
        Reload a tool from its module (useful for development).
        
        Args:
            name: Tool name to reload
            
        Returns:
            True if successful, False otherwise
        """
        if name not in self.tools:
            return False
        
        if name in self.tool_modules:
            try:
                # Reload module
                module = self.tool_modules[name]
                importlib.reload(module)
                
                # Re-register tool
                if hasattr(module, 'create_tool'):
                    new_tool = module.create_tool()
                    self.register_tool(new_tool)
                    self.logger.info(f"🔄 Tool '{name}' reloaded successfully")
                    return True
                    
            except Exception as e:
                self.logger.error(f"❌ Failed to reload tool '{name}': {str(e)}")
        
        return False
    
    def _register_default_tools(self):
        """Register default system tools."""
        
        # Web Search Tool
        def web_search(query: str, max_results: int = 5) -> Dict[str, Any]:
            """Search the web for information."""
            # Placeholder implementation - in production, integrate with real search API
            return {
                "query": query,
                "results": [
                    {
                        "title": f"Search result {i+1} for '{query}'",
                        "url": f"https://example.com/result-{i+1}",
                        "snippet": f"This is a sample search result snippet for query: {query}"
                    }
                    for i in range(min(max_results, 3))
                ],
                "total_results": max_results,
                "search_time": time.time(),
                "timestamp": datetime.now().isoformat()
            }
        
        self.register_tool(Tool(
            name="web_search",
            description="Search the web for information and return relevant results",
            function=web_search,
            parameters={
                "query": {
                    "type": "string",
                    "description": "Search query",
                    "required": True
                },
                "max_results": {
                    "type": "integer", 
                    "description": "Maximum number of results",
                    "default": 5,
                    "required": False
                }
            },
            category=ToolCategory.INFORMATION.value,
            timeout=30
        ))
        
        # File Operations Tool
        def read_file(filepath: str, encoding: str = "utf-8") -> Dict[str, Any]:
            """Read content from a file with error handling."""
            try:
                # Security check - prevent path traversal
                filepath = os.path.abspath(filepath)
                if not filepath.startswith(os.path.abspath(self.settings.data_directory)):
                    raise PermissionError("Access denied: File outside allowed directory")
                
                with open(filepath, 'r', encoding=encoding) as f:
                    content = f.read()
                
                return {
                    "filepath": filepath,
                    "content": content,
                    "size_bytes": len(content.encode(encoding)),
                    "encoding": encoding,
                    "read_time": datetime.now().isoformat()
                }
                
            except Exception as e:
                return {
                    "filepath": filepath,
                    "error": str(e),
                    "content": None
                }
        
        self.register_tool(Tool(
            name="read_file",
            description="Read content from a file with security controls",
            function=read_file,
            parameters={
                "filepath": {
                    "type": "string",
                    "description": "Path to the file to read",
                    "required": True
                },
                "encoding": {
                    "type": "string",
                    "description": "File encoding",
                    "default": "utf-8",
                    "required": False
                }
            },
            category=ToolCategory.FILE_OPERATIONS.value,
            requires_auth=True,
            timeout=10
        ))
        
        # Write File Tool
        def write_file(filepath: str, content: str, encoding: str = "utf-8", append: bool = False) -> Dict[str, Any]:
            """Write content to a file with security controls."""
            try:
                # Security check
                filepath = os.path.abspath(filepath)
                if not filepath.startswith(os.path.abspath(self.settings.data_directory)):
                    raise PermissionError("Access denied: File outside allowed directory")
                
                # Ensure directory exists
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
                
                mode = 'a' if append else 'w'
                with open(filepath, mode, encoding=encoding) as f:
                    f.write(content)
                
                return {
                    "filepath": filepath,
                    "bytes_written": len(content.encode(encoding)),
                    "mode": mode,
                    "encoding": encoding,
                    "write_time": datetime.now().isoformat(),
                    "success": True
                }
                
            except Exception as e:
                return {
                    "filepath": filepath,
                    "error": str(e),
                    "success": False
                }
        
        self.register_tool(Tool(
            name="write_file",
            description="Write content to a file with security controls",
            function=write_file,
            parameters={
                "filepath": {"type": "string", "required": True},
                "content": {"type": "string", "required": True},
                "encoding": {"type": "string", "default": "utf-8", "required": False},
                "append": {"type": "boolean", "default": False, "required": False}
            },
            category=ToolCategory.FILE_OPERATIONS.value,
            requires_auth=True,
            timeout=15
        ))
        
        # Calculator Tool
        def calculate(expression: str) -> Dict[str, Any]:
            """Perform safe mathematical calculations."""
            try:
                # Security: only allow safe mathematical operations
                allowed_chars = set('0123456789+-*/.() ')
                if not all(c in allowed_chars for c in expression):
                    raise ValueError("Invalid characters in expression")
                
                # Additional security: prevent common attack patterns
                dangerous_patterns = ['__', 'exec', 'eval', 'import', 'open']
                if any(pattern in expression.lower() for pattern in dangerous_patterns):
                    raise ValueError("Potentially dangerous expression")
                
                result = eval(expression)
                
                return {
                    "expression": expression,
                    "result": result,
                    "result_type": type(result).__name__,
                    "calculation_time": datetime.now().isoformat(),
                    "success": True
                }
                
            except Exception as e:
                return {
                    "expression": expression,
                    "error": str(e),
                    "result": None,
                    "success": False
                }
        
        self.register_tool(Tool(
            name="calculate",
            description="Perform safe mathematical calculations",
            function=calculate,
            parameters={
                "expression": {
                    "type": "string",
                    "description": "Mathematical expression to evaluate",
                    "required": True
                }
            },
            category=ToolCategory.UTILITIES.value,
            timeout=5
        ))
        
        # System Information Tool
        def get_system_info() -> Dict[str, Any]:
            """Get system information and resource usage."""
            try:
                import psutil
                import platform
                
                return {
                    "platform": platform.platform(),
                    "python_version": platform.python_version(),
                    "cpu_percent": psutil.cpu_percent(interval=1),
                    "memory": {
                        "total": psutil.virtual_memory().total,
                        "available": psutil.virtual_memory().available,
                        "percent": psutil.virtual_memory().percent
                    },
                    "disk": {
                        "total": psutil.disk_usage('/').total,
                        "free": psutil.disk_usage('/').free,
                        "percent": psutil.disk_usage('/').percent
                    },
                    "timestamp": datetime.now().isoformat()
                }
                
            except ImportError:
                return {
                    "error": "psutil not available",
                    "basic_info": {
                        "platform": platform.platform(),
                        "python_version": platform.python_version()
                    }
                }
        
        self.register_tool(Tool(
            name="get_system_info",
            description="Get system information and resource usage",
            function=get_system_info,
            parameters={},
            category=ToolCategory.UTILITIES.value,
            timeout=10
        ))
    
    def _load_custom_tools(self):
        """Load custom tools from tools directory."""
        tools_dir = Path("src/tools/custom")
        if not tools_dir.exists():
            return
        
        for tool_file in tools_dir.glob("*.py"):
            if tool_file.stem.startswith("_"):
                continue
            
            try:
                # Import module
                module_name = f"src.tools.custom.{tool_file.stem}"
                module = importlib.import_module(module_name)
                
                # Look for tool creation function
                if hasattr(module, 'create_tool'):
                    tool = module.create_tool()
                    self.register_tool(tool)
                    self.tool_modules[tool.name] = module
                    
                self.logger.info(f"📦 Loaded custom tool from {tool_file}")
                
            except Exception as e:
                self.logger.error(f"❌ Failed to load tool from {tool_file}: {str(e)}")
    
    def export_tools(self, filename: str = None) -> str:
        """
        Export tool registry data for backup or migration.
        
        Args:
            filename: Output filename (optional)
            
        Returns:
            Export filename
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{self.settings.data_directory}/tools_export_{timestamp}.json"
        
        export_data = {
            "metadata": {
                "export_timestamp": datetime.now().isoformat(),
                "total_tools": len(self.tools),
                "exporter": "Agentic AI Dev Toolkit v2.0"
            },
            "tools": [tool.to_dict() for tool in self.tools.values()],
            "usage_statistics": self.usage_stats,
            "categories": list(set(tool.category for tool in self.tools.values()))
        }
        
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, default=str)
        
        self.logger.info(f"📄 Tools exported to {filename}")
        return filename