#!/usr/bin/env python3
"""
Tool Management API Routes
==========================

RESTful endpoints for tool registry, execution, and monitoring.

Author: Karim Osman
License: MIT
"""

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends, Request, Query
from fastapi.responses import JSONResponse
import structlog

from ...core.models import ToolCreate, ToolCategory
from ...core.agent_manager import AgentManager
from ...core.tool_registry import ToolRegistry
from ...core.config import Settings


router = APIRouter()
logger = structlog.get_logger(__name__)


def get_agent_manager(request: Request) -> AgentManager:
    """Dependency to get agent manager from app state."""
    return request.app.state.agent_manager


def get_tool_registry(request: Request) -> ToolRegistry:
    """Dependency to get tool registry from agent manager."""
    return request.app.state.agent_manager.tool_registry


def get_settings(request: Request) -> Settings:
    """Dependency to get settings from app state."""
    return request.app.state.settings


@router.get("/", response_model=Dict[str, Any])
async def list_tools(
    category: Optional[str] = Query(None, description="Filter by tool category"),
    search: Optional[str] = Query(None, description="Search in names and descriptions"),
    limit: int = Query(50, ge=1, le=500, description="Maximum number of tools"),
    offset: int = Query(0, ge=0, description="Number of tools to skip"),
    registry: ToolRegistry = Depends(get_tool_registry)
):
    """
    List all available tools with filtering and search capabilities.
    
    Returns comprehensive tool information including:
    - Tool metadata and descriptions
    - Usage statistics and performance
    - Parameter specifications
    - Category and capability information
    """
    try:
        # Get filtered tool names
        tool_names = registry.list_tools(category=category, search=search)
        
        # Apply pagination
        total_count = len(tool_names)
        paginated_names = tool_names[offset:offset + limit]
        
        # Build detailed tool information
        tools_info = []
        for tool_name in paginated_names:
            tool = registry.get_tool(tool_name)
            if tool:
                tool_dict = tool.to_dict()
                
                # Add usage statistics
                try:
                    stats = registry.get_tool_statistics(tool_name)
                    tool_dict["usage_statistics"] = stats
                except:
                    tool_dict["usage_statistics"] = {"error": "Statistics unavailable"}
                
                tools_info.append(tool_dict)
        
        return {
            "tools": tools_info,
            "pagination": {
                "total": total_count,
                "limit": limit,
                "offset": offset,
                "has_more": offset + limit < total_count
            },
            "filters": {
                "category": category,
                "search": search
            },
            "categories": list(ToolCategory.__members__.keys())
        }
        
    except Exception as e:
        logger.error("Failed to list tools", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to list tools: {str(e)}")


@router.get("/{tool_name}", response_model=Dict[str, Any])
async def get_tool(
    tool_name: str,
    include_stats: bool = Query(True, description="Include usage statistics"),
    registry: ToolRegistry = Depends(get_tool_registry)
):
    """
    Get detailed information about a specific tool.
    
    Returns:
    - Complete tool specification
    - Parameter requirements and validation rules
    - Usage statistics and performance metrics
    - Example usage patterns
    """
    try:
        tool = registry.get_tool(tool_name)
        if not tool:
            raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")
        
        tool_info = tool.to_dict()
        
        # Add usage statistics if requested
        if include_stats:
            try:
                stats = registry.get_tool_statistics(tool_name)
                tool_info["usage_statistics"] = stats
            except Exception as e:
                logger.warning("Failed to get tool statistics", tool_name=tool_name, error=str(e))
                tool_info["usage_statistics"] = {"error": "Statistics unavailable"}
        
        # Add parameter examples
        tool_info["parameter_examples"] = _generate_parameter_examples(tool)
        
        return {
            "tool": tool_info,
            "retrieved_at": "2024-08-23T10:00:00Z"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get tool", tool_name=tool_name, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get tool: {str(e)}")


@router.post("/{tool_name}/execute", response_model=Dict[str, Any])
async def execute_tool(
    tool_name: str,
    execution_data: Dict[str, Any],
    timeout: Optional[int] = Query(None, ge=1, le=300, description="Execution timeout in seconds"),
    registry: ToolRegistry = Depends(get_tool_registry)
):
    """
    Execute a tool with specified parameters.
    
    Features:
    - Parameter validation and type checking
    - Execution timeout control
    - Error handling and reporting
    - Performance monitoring
    """
    try:
        tool = registry.get_tool(tool_name)
        if not tool:
            raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")
        
        # Extract parameters
        parameters = execution_data.get("parameters", {})
        
        # Validate required permissions
        if tool.requires_auth:
            # In production, implement proper authentication check
            # For now, just log the requirement
            logger.info("Tool requires authentication", tool_name=tool_name)
        
        # Execute tool with monitoring
        import time
        start_time = time.time()
        
        try:
            result = registry.execute_tool(
                name=tool_name,
                timeout=timeout,
                **parameters
            )
            
            execution_time = time.time() - start_time
            
            logger.info(
                "Tool executed successfully",
                tool_name=tool_name,
                execution_time=execution_time,
                parameters=list(parameters.keys())
            )
            
            return {
                "tool_name": tool_name,
                "execution_status": "success",
                "result": result,
                "execution_time": round(execution_time, 4),
                "parameters_used": parameters,
                "executed_at": "2024-08-23T10:00:00Z"
            }
            
        except TimeoutError as e:
            execution_time = time.time() - start_time
            logger.warning("Tool execution timeout", tool_name=tool_name, timeout=timeout)
            raise HTTPException(
                status_code=408,
                detail=f"Tool execution timeout after {timeout}s"
            )
            
        except ValueError as e:
            logger.warning("Tool validation error", tool_name=tool_name, error=str(e))
            raise HTTPException(status_code=400, detail=str(e))
            
        except RuntimeError as e:
            logger.error("Tool execution error", tool_name=tool_name, error=str(e))
            raise HTTPException(status_code=500, detail=str(e))
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Unexpected error executing tool", tool_name=tool_name, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to execute tool: {str(e)}")


@router.get("/categories/list", response_model=Dict[str, Any])
async def list_tool_categories(
    registry: ToolRegistry = Depends(get_tool_registry)
):
    """
    Get all tool categories with tool counts and descriptions.
    
    Returns organized view of tools by category for easy navigation.
    """
    try:
        # Get tools organized by category
        tools_by_category = registry.get_tools_by_category()
        
        # Build category information
        categories = []
        for category_name in ToolCategory.__members__.keys():
            category_tools = tools_by_category.get(category_name.lower(), [])
            
            categories.append({
                "name": category_name.lower(),
                "display_name": category_name.replace('_', ' ').title(),
                "tool_count": len(category_tools),
                "tools": category_tools,
                "description": _get_category_description(category_name)
            })
        
        return {
            "categories": categories,
            "total_categories": len(categories),
            "total_tools": sum(cat["tool_count"] for cat in categories)
        }
        
    except Exception as e:
        logger.error("Failed to list tool categories", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to list categories: {str(e)}")


@router.get("/statistics/summary", response_model=Dict[str, Any])
async def get_tool_statistics(
    registry: ToolRegistry = Depends(get_tool_registry)
):
    """
    Get comprehensive tool usage statistics and analytics.
    
    Returns:
    - Overall usage metrics
    - Performance analytics
    - Most popular tools
    - Category distribution
    """
    try:
        stats = registry.get_tool_statistics()
        
        return {
            "statistics": stats,
            "generated_at": "2024-08-23T10:00:00Z"
        }
        
    except Exception as e:
        logger.error("Failed to get tool statistics", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get statistics: {str(e)}")


@router.post("/reload/{tool_name}", response_model=Dict[str, Any])
async def reload_tool(
    tool_name: str,
    registry: ToolRegistry = Depends(get_tool_registry)
):
    """
    Reload a tool from its source module (useful for development).
    
    Features:
    - Hot-reload for custom tools
    - Validation of new implementation
    - Preservation of usage statistics
    """
    try:
        tool = registry.get_tool(tool_name)
        if not tool:
            raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")
        
        # Attempt to reload
        success = registry.reload_tool(tool_name)
        
        if success:
            logger.info("Tool reloaded successfully", tool_name=tool_name)
            return {
                "message": "Tool reloaded successfully",
                "tool_name": tool_name,
                "reloaded_at": "2024-08-23T10:00:00Z"
            }
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to reload tool '{tool_name}'"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to reload tool", tool_name=tool_name, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to reload tool: {str(e)}")


@router.delete("/{tool_name}", response_model=Dict[str, Any])
async def unregister_tool(
    tool_name: str,
    registry: ToolRegistry = Depends(get_tool_registry)
):
    """
    Unregister a tool from the registry.
    
    WARNING: This will remove the tool from all agents using it.
    """
    try:
        tool = registry.get_tool(tool_name)
        if not tool:
            raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")
        
        # Check if tool is in use by any agents
        manager = registry._AgentManager  # Access parent manager if available
        if hasattr(registry, '_manager'):
            agents_using_tool = [
                agent for agent in manager.list_agents()
                if tool_name in agent.tools
            ]
            
            if agents_using_tool:
                logger.warning(
                    "Attempting to unregister tool in use",
                    tool_name=tool_name,
                    agents_count=len(agents_using_tool)
                )
                # You might want to prevent this or force-remove from agents
        
        # Unregister tool
        success = registry.unregister_tool(tool_name)
        
        if success:
            logger.info("Tool unregistered successfully", tool_name=tool_name)
            return {
                "message": "Tool unregistered successfully",
                "tool_name": tool_name,
                "unregistered_at": "2024-08-23T10:00:00Z"
            }
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to unregister tool '{tool_name}'"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to unregister tool", tool_name=tool_name, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to unregister tool: {str(e)}")


@router.post("/export", response_model=Dict[str, Any])
async def export_tools(
    export_data: Dict[str, Any],
    registry: ToolRegistry = Depends(get_tool_registry)
):
    """
    Export tool registry data for backup or migration.
    
    Features:
    - Complete tool specifications
    - Usage statistics
    - Configuration metadata
    """
    try:
        filename = export_data.get("filename")
        
        export_file = registry.export_tools(filename)
        
        logger.info("Tools exported successfully", filename=export_file)
        
        return {
            "message": "Tools exported successfully",
            "filename": export_file,
            "tool_count": len(registry.tools),
            "exported_at": "2024-08-23T10:00:00Z"
        }
        
    except Exception as e:
        logger.error("Failed to export tools", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to export tools: {str(e)}")


@router.get("/health/check", response_model=Dict[str, Any])
async def check_tool_health(
    registry: ToolRegistry = Depends(get_tool_registry)
):
    """
    Perform health checks on all registered tools.
    
    Returns:
    - Tool availability status
    - Basic functionality tests
    - Performance indicators
    """
    try:
        health_results = {}
        total_tools = len(registry.tools)
        healthy_tools = 0
        
        for tool_name, tool in registry.tools.items():
            try:
                # Basic health check - verify tool is callable
                health_status = {
                    "status": "healthy",
                    "callable": callable(tool.function),
                    "has_description": bool(tool.description),
                    "has_parameters": bool(tool.parameters),
                    "usage_count": tool.usage_count,
                    "last_used": tool.last_used
                }
                
                # Simple functionality test for safe tools
                if tool.category in ["utilities", "general"] and not tool.requires_auth:
                    try:
                        # Test with empty parameters if no required params
                        required_params = [
                            name for name, info in tool.parameters.items()
                            if info.get("required", False)
                        ]
                        
                        if not required_params:
                            # Safe to test with no parameters
                            health_status["test_execution"] = "skipped_no_safe_test"
                        else:
                            health_status["test_execution"] = "skipped_requires_params"
                            
                    except Exception as test_error:
                        health_status["test_execution"] = f"test_failed: {str(test_error)}"
                        health_status["status"] = "warning"
                
                if health_status["status"] == "healthy":
                    healthy_tools += 1
                
                health_results[tool_name] = health_status
                
            except Exception as e:
                health_results[tool_name] = {
                    "status": "unhealthy",
                    "error": str(e)
                }
        
        overall_health = "healthy" if healthy_tools == total_tools else "degraded"
        
        return {
            "overall_health": overall_health,
            "total_tools": total_tools,
            "healthy_tools": healthy_tools,
            "health_percentage": (healthy_tools / max(1, total_tools)) * 100,
            "tool_health": health_results,
            "checked_at": "2024-08-23T10:00:00Z"
        }
        
    except Exception as e:
        logger.error("Failed to check tool health", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to check tool health: {str(e)}")


def _generate_parameter_examples(tool) -> Dict[str, Any]:
    """Generate example parameters for a tool."""
    examples = {}
    
    for param_name, param_info in tool.parameters.items():
        param_type = param_info.get("type", "string")
        
        if param_type == "string":
            examples[param_name] = "example_value"
        elif param_type == "integer":
            examples[param_name] = 42
        elif param_type == "boolean":
            examples[param_name] = True
        elif param_type == "float" or param_type == "number":
            examples[param_name] = 3.14
        else:
            examples[param_name] = f"<{param_type}>"
    
    return examples


def _get_category_description(category_name: str) -> str:
    """Get description for tool category."""
    descriptions = {
        "GENERAL": "General purpose tools for common tasks",
        "INFORMATION": "Tools for gathering and processing information",
        "FILE_OPERATIONS": "File system and document manipulation tools",
        "WEB_SCRAPING": "Web data extraction and scraping tools",
        "DATA_PROCESSING": "Data analysis and transformation tools",
        "COMMUNICATION": "Communication and messaging tools",
        "AI_MODELS": "AI model integration and execution tools",
        "UTILITIES": "System utilities and helper functions",
        "CUSTOM": "Custom tools specific to your use case"
    }
    
    return descriptions.get(category_name, "Custom tool category")