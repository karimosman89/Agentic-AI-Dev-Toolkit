#!/usr/bin/env python3
"""
Agent Management API Routes
===========================

RESTful endpoints for comprehensive agent lifecycle management.

Author: Karim Osman
License: MIT
"""

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends, Request, Query
from fastapi.responses import JSONResponse
import structlog

from ...core.models import Agent, AgentCreate, AgentUpdate, AgentStatus
from ...core.agent_manager import AgentManager
from ...core.config import Settings


router = APIRouter()
logger = structlog.get_logger(__name__)


def get_agent_manager(request: Request) -> AgentManager:
    """Dependency to get agent manager from app state."""
    return request.app.state.agent_manager


def get_settings(request: Request) -> Settings:
    """Dependency to get settings from app state."""
    return request.app.state.settings


@router.get("/", response_model=List[Dict[str, Any]])
async def list_agents(
    status: Optional[str] = Query(None, description="Filter by agent status"),
    agent_type: Optional[str] = Query(None, description="Filter by agent type"),
    limit: int = Query(50, ge=1, le=1000, description="Maximum number of agents to return"),
    offset: int = Query(0, ge=0, description="Number of agents to skip"),
    manager: AgentManager = Depends(get_agent_manager)
):
    """
    List all agents with optional filtering and pagination.
    
    Returns comprehensive agent information including:
    - Basic agent details
    - Current status and activity
    - Performance metrics
    - Tool assignments
    """
    try:
        # Convert status filter
        status_filter = None
        if status:
            try:
                status_filter = AgentStatus(status.lower())
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
        
        # Get filtered agents
        agents = manager.list_agents(status_filter=status_filter, agent_type=agent_type)
        
        # Apply pagination
        total_count = len(agents)
        paginated_agents = agents[offset:offset + limit]
        
        # Convert to dict format with enhanced information
        agent_list = []
        for agent in paginated_agents:
            agent_dict = agent.to_dict()
            
            # Add runtime information
            agent_dict.update({
                "is_available": agent.is_available(),
                "current_task_count": len(agent.current_tasks),
                "uptime_seconds": (
                    manager.metrics.get("start_time") and
                    (manager.metrics["start_time"] != agent.created_at)
                ) or 0
            })
            
            agent_list.append(agent_dict)
        
        return {
            "agents": agent_list,
            "pagination": {
                "total": total_count,
                "limit": limit,
                "offset": offset,
                "has_more": offset + limit < total_count
            },
            "filters": {
                "status": status,
                "agent_type": agent_type
            }
        }
        
    except Exception as e:
        logger.error("Failed to list agents", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to list agents: {str(e)}")


@router.post("/", response_model=Dict[str, Any])
async def create_agent(
    agent_data: AgentCreate,
    manager: AgentManager = Depends(get_agent_manager)
):
    """
    Create a new intelligent agent with specified configuration.
    
    Agent creation includes:
    - Validation of tools and capabilities
    - Registration with communication bus
    - Initial performance metrics setup
    - Welcome message delivery
    """
    try:
        agent_id = await manager.create_agent(
            name=agent_data.name,
            description=agent_data.description,
            agent_type=agent_data.agent_type,
            tools=agent_data.tools,
            capabilities=agent_data.capabilities,
            configuration=agent_data.configuration,
            max_concurrent_tasks=agent_data.max_concurrent_tasks,
            tags=agent_data.tags
        )
        
        # Get the created agent for response
        agent = manager.get_agent(agent_id)
        
        logger.info("Agent created successfully", agent_id=agent_id, name=agent_data.name)
        
        return {
            "message": "Agent created successfully",
            "agent": agent.to_dict(),
            "agent_id": agent_id,
            "status": "created"
        }
        
    except ValueError as e:
        logger.warning("Agent creation validation failed", error=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        logger.error("Agent creation failed", error=str(e))
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.error("Unexpected error creating agent", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to create agent: {str(e)}")


@router.get("/{agent_id}", response_model=Dict[str, Any])
async def get_agent(
    agent_id: str,
    include_performance: bool = Query(True, description="Include performance metrics"),
    manager: AgentManager = Depends(get_agent_manager)
):
    """
    Get detailed information about a specific agent.
    
    Returns comprehensive agent details including:
    - Configuration and capabilities
    - Current status and tasks
    - Performance metrics (optional)
    - Tool assignments and usage
    """
    try:
        agent = manager.get_agent(agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
        
        agent_info = agent.to_dict()
        
        # Add runtime information
        agent_info.update({
            "is_available": agent.is_available(),
            "current_task_count": len(agent.current_tasks),
            "current_tasks": agent.current_tasks
        })
        
        # Include performance metrics if requested
        if include_performance:
            try:
                performance = manager.get_agent_performance(agent_id)
                agent_info["performance"] = performance
            except Exception as e:
                logger.warning("Failed to get performance metrics", agent_id=agent_id, error=str(e))
                agent_info["performance"] = {"error": "Performance metrics unavailable"}
        
        return {
            "agent": agent_info,
            "retrieved_at": "2024-08-23T10:00:00Z"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get agent", agent_id=agent_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get agent: {str(e)}")


@router.put("/{agent_id}", response_model=Dict[str, Any])
async def update_agent(
    agent_id: str,
    update_data: AgentUpdate,
    manager: AgentManager = Depends(get_agent_manager)
):
    """
    Update agent configuration and properties.
    
    Allows updating:
    - Name and description
    - Tool assignments
    - Capabilities and configuration
    - Task concurrency limits
    - Tags and metadata
    """
    try:
        agent = manager.get_agent(agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
        
        # Update agent properties
        updated_fields = []
        
        if update_data.name is not None:
            agent.name = update_data.name
            updated_fields.append("name")
        
        if update_data.description is not None:
            agent.description = update_data.description
            updated_fields.append("description")
        
        if update_data.tools is not None:
            # Validate tools exist
            available_tools = manager.tool_registry.list_tools()
            for tool in update_data.tools:
                if tool not in available_tools:
                    raise HTTPException(
                        status_code=400, 
                        detail=f"Tool '{tool}' not available"
                    )
            agent.tools = update_data.tools
            updated_fields.append("tools")
        
        if update_data.capabilities is not None:
            agent.capabilities = update_data.capabilities
            updated_fields.append("capabilities")
        
        if update_data.max_concurrent_tasks is not None:
            agent.max_concurrent_tasks = update_data.max_concurrent_tasks
            updated_fields.append("max_concurrent_tasks")
        
        if update_data.configuration is not None:
            agent.configuration.update(update_data.configuration)
            updated_fields.append("configuration")
        
        if update_data.tags is not None:
            agent.tags = update_data.tags
            updated_fields.append("tags")
        
        if update_data.status is not None:
            try:
                new_status = AgentStatus(update_data.status.lower())
                await manager.update_agent_status(agent_id, new_status)
                updated_fields.append("status")
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid status: {update_data.status}"
                )
        
        # Update activity timestamp
        agent.update_activity()
        
        logger.info("Agent updated successfully", agent_id=agent_id, updated_fields=updated_fields)
        
        return {
            "message": "Agent updated successfully",
            "agent": agent.to_dict(),
            "updated_fields": updated_fields,
            "updated_at": agent.last_activity
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update agent", agent_id=agent_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to update agent: {str(e)}")


@router.delete("/{agent_id}")
async def delete_agent(
    agent_id: str,
    graceful: bool = Query(True, description="Graceful shutdown (wait for tasks)"),
    manager: AgentManager = Depends(get_agent_manager)
):
    """
    Delete an agent and clean up its resources.
    
    Options:
    - Graceful: Wait for current tasks to complete
    - Force: Immediately terminate and cleanup
    """
    try:
        agent = manager.get_agent(agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
        
        # Shutdown agent
        await manager.shutdown_agent(agent_id, graceful=graceful)
        
        # Remove from agents dictionary
        del manager.agents[agent_id]
        
        logger.info("Agent deleted successfully", agent_id=agent_id, graceful=graceful)
        
        return {
            "message": "Agent deleted successfully",
            "agent_id": agent_id,
            "graceful_shutdown": graceful,
            "deleted_at": "2024-08-23T10:00:00Z"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete agent", agent_id=agent_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to delete agent: {str(e)}")


@router.get("/{agent_id}/status")
async def get_agent_status(
    agent_id: str,
    manager: AgentManager = Depends(get_agent_manager)
):
    """Get current agent status and activity information."""
    try:
        agent = manager.get_agent(agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
        
        return {
            "agent_id": agent_id,
            "status": agent.status.value,
            "is_available": agent.is_available(),
            "current_tasks": agent.current_tasks,
            "current_task_count": len(agent.current_tasks),
            "max_concurrent_tasks": agent.max_concurrent_tasks,
            "last_activity": agent.last_activity,
            "created_at": agent.created_at
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get agent status", agent_id=agent_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get agent status: {str(e)}")


@router.post("/{agent_id}/status")
async def update_agent_status_endpoint(
    agent_id: str,
    status_data: Dict[str, Any],
    manager: AgentManager = Depends(get_agent_manager)
):
    """Update agent status with optional metadata."""
    try:
        agent = manager.get_agent(agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
        
        # Validate status
        new_status_str = status_data.get("status")
        if not new_status_str:
            raise HTTPException(status_code=400, detail="Status is required")
        
        try:
            new_status = AgentStatus(new_status_str.lower())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {new_status_str}")
        
        # Update status
        metadata = status_data.get("metadata", {})
        await manager.update_agent_status(agent_id, new_status, metadata)
        
        logger.info("Agent status updated", agent_id=agent_id, new_status=new_status.value)
        
        return {
            "message": "Agent status updated successfully",
            "agent_id": agent_id,
            "old_status": agent.status.value,
            "new_status": new_status.value,
            "metadata": metadata,
            "updated_at": agent.last_activity
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update agent status", agent_id=agent_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to update agent status: {str(e)}")


@router.get("/{agent_id}/performance")
async def get_agent_performance(
    agent_id: str,
    manager: AgentManager = Depends(get_agent_manager)
):
    """Get detailed performance metrics for an agent."""
    try:
        performance = manager.get_agent_performance(agent_id)
        return {
            "performance": performance,
            "retrieved_at": "2024-08-23T10:00:00Z"
        }
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Failed to get agent performance", agent_id=agent_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get performance metrics: {str(e)}")


@router.get("/available/for-tool/{tool_name}")
async def get_available_agents_for_tool(
    tool_name: str,
    manager: AgentManager = Depends(get_agent_manager)
):
    """Get available agents that can handle a specific tool."""
    try:
        available_agents = manager.get_available_agents(tool_name=tool_name)
        
        return {
            "tool_name": tool_name,
            "available_agents": [agent.to_dict() for agent in available_agents],
            "count": len(available_agents)
        }
        
    except Exception as e:
        logger.error("Failed to get available agents for tool", tool_name=tool_name, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get available agents: {str(e)}")


@router.get("/statistics/summary")
async def get_agents_statistics(
    manager: AgentManager = Depends(get_agent_manager)
):
    """Get comprehensive statistics about all agents."""
    try:
        stats = manager.get_agent_statistics()
        return {
            "statistics": stats,
            "generated_at": "2024-08-23T10:00:00Z"
        }
        
    except Exception as e:
        logger.error("Failed to get agent statistics", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get statistics: {str(e)}")


@router.post("/export")
async def export_agents_data(
    export_request: Dict[str, Any],
    manager: AgentManager = Depends(get_agent_manager)
):
    """Export agent data for backup or migration."""
    try:
        filename = export_request.get("filename")
        agent_ids = export_request.get("agent_ids")
        
        export_file = await manager.export_agent_data(filename, agent_ids)
        
        return {
            "message": "Agent data exported successfully",
            "filename": export_file,
            "exported_at": "2024-08-23T10:00:00Z",
            "agent_count": len(agent_ids) if agent_ids else len(manager.agents)
        }
        
    except Exception as e:
        logger.error("Failed to export agent data", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to export data: {str(e)}")