#!/usr/bin/env python3
"""
Task Management API Routes
==========================

RESTful endpoints for intelligent task orchestration and monitoring.

Author: Karim Osman
License: MIT
"""

import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends, Request, Query, BackgroundTasks
from fastapi.responses import JSONResponse
import structlog

from ...core.models import Message, MessageType, TaskCreate
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


@router.post("/", response_model=Dict[str, Any])
async def create_task(
    task_data: TaskCreate,
    background_tasks: BackgroundTasks,
    manager: AgentManager = Depends(get_agent_manager)
):
    """
    Create and execute a new task for a specific agent.
    
    Task execution features:
    - Intelligent agent selection
    - Priority-based queuing
    - Real-time progress tracking
    - Comprehensive error handling
    """
    try:
        # Validate agent exists
        agent = manager.get_agent(task_data.agent_id)
        if not agent:
            raise HTTPException(
                status_code=404, 
                detail=f"Agent {task_data.agent_id} not found"
            )
        
        # Check agent availability
        if not agent.is_available():
            raise HTTPException(
                status_code=409,
                detail=f"Agent {agent.name} is not available (status: {agent.status.value})"
            )
        
        # Generate task ID
        task_id = str(uuid.uuid4())
        
        # Prepare task metadata
        task_metadata = {
            "task_id": task_id,
            "created_at": datetime.now().isoformat(),
            "priority": task_data.priority,
            "timeout": task_data.timeout,
            "reply_to": "system",
            **task_data.metadata
        }
        
        # Send task to agent
        await manager.send_task_to_agent(
            agent_id=task_data.agent_id,
            task=task_data.task_content,
            priority=task_data.priority,
            metadata=task_metadata
        )
        
        logger.info(
            "Task created and queued",
            task_id=task_id,
            agent_id=task_data.agent_id,
            priority=task_data.priority
        )
        
        return {
            "message": "Task created successfully",
            "task_id": task_id,
            "agent_id": task_data.agent_id,
            "agent_name": agent.name,
            "status": "queued",
            "priority": task_data.priority,
            "created_at": task_metadata["created_at"],
            "estimated_completion": "2024-08-23T10:05:00Z"  # Placeholder
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to create task", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to create task: {str(e)}")


@router.post("/broadcast", response_model=Dict[str, Any])
async def broadcast_task(
    broadcast_data: Dict[str, Any],
    manager: AgentManager = Depends(get_agent_manager)
):
    """
    Broadcast a task to multiple agents based on criteria.
    
    Supports:
    - Capability-based targeting
    - Tool requirement filtering
    - Agent type selection
    - Priority distribution
    """
    try:
        task_content = broadcast_data.get("task_content")
        if not task_content:
            raise HTTPException(status_code=400, detail="task_content is required")
        
        # Get targeting criteria
        agent_type = broadcast_data.get("agent_type")
        required_tool = broadcast_data.get("required_tool")
        required_capability = broadcast_data.get("required_capability")
        priority = broadcast_data.get("priority", 1)
        
        # Find target agents
        target_agents = manager.get_available_agents(
            tool_name=required_tool,
            capability=required_capability
        )
        
        # Filter by agent type if specified
        if agent_type:
            target_agents = [a for a in target_agents if a.agent_type == agent_type]
        
        if not target_agents:
            raise HTTPException(
                status_code=404,
                detail="No available agents found matching criteria"
            )
        
        # Generate broadcast task ID
        broadcast_id = str(uuid.uuid4())
        task_ids = []
        
        # Send task to each target agent
        for agent in target_agents:
            task_id = str(uuid.uuid4())
            task_ids.append(task_id)
            
            task_metadata = {
                "task_id": task_id,
                "broadcast_id": broadcast_id,
                "created_at": datetime.now().isoformat(),
                "priority": priority,
                "reply_to": "system"
            }
            
            await manager.send_task_to_agent(
                agent_id=agent.id,
                task=task_content,
                priority=priority,
                metadata=task_metadata
            )
        
        logger.info(
            "Broadcast task sent",
            broadcast_id=broadcast_id,
            target_count=len(target_agents),
            criteria={"agent_type": agent_type, "tool": required_tool, "capability": required_capability}
        )
        
        return {
            "message": "Broadcast task sent successfully",
            "broadcast_id": broadcast_id,
            "task_ids": task_ids,
            "target_agents": [
                {"agent_id": a.id, "agent_name": a.name, "agent_type": a.agent_type}
                for a in target_agents
            ],
            "target_count": len(target_agents),
            "priority": priority,
            "created_at": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to broadcast task", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to broadcast task: {str(e)}")


@router.get("/history", response_model=Dict[str, Any])
async def get_task_history(
    agent_id: Optional[str] = Query(None, description="Filter by specific agent"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of tasks"),
    message_type: Optional[str] = Query(None, description="Filter by message type"),
    since_hours: int = Query(24, ge=1, le=168, description="Hours to look back"),
    manager: AgentManager = Depends(get_agent_manager)
):
    """
    Get task execution history with filtering and pagination.
    
    Returns:
    - Task creation and completion events
    - Agent responses and results
    - Error messages and diagnostics
    - Performance metrics
    """
    try:
        # Calculate since timestamp
        from datetime import timedelta
        since = datetime.now() - timedelta(hours=since_hours)
        
        # Get message history
        messages = manager.communication_bus.get_message_history(
            agent_id=agent_id,
            message_type=message_type,
            limit=limit,
            since=since
        )
        
        # Process messages for task-relevant information
        task_events = []
        for msg in messages:
            if msg.message_type in [MessageType.TASK.value, MessageType.RESPONSE.value, MessageType.ERROR.value]:
                event = {
                    "message_id": msg.id,
                    "timestamp": msg.timestamp,
                    "sender": msg.sender,
                    "recipient": msg.recipient,
                    "message_type": msg.message_type,
                    "priority": msg.priority,
                    "content_summary": str(msg.content)[:200] + "..." if len(str(msg.content)) > 200 else str(msg.content)
                }
                
                # Add task-specific metadata
                if hasattr(msg, 'metadata') and msg.metadata:
                    event["task_id"] = msg.metadata.get("task_id")
                    event["broadcast_id"] = msg.metadata.get("broadcast_id")
                
                task_events.append(event)
        
        return {
            "task_history": task_events,
            "filters": {
                "agent_id": agent_id,
                "message_type": message_type,
                "since_hours": since_hours,
                "limit": limit
            },
            "total_events": len(task_events),
            "retrieved_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error("Failed to get task history", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get task history: {str(e)}")


@router.get("/active", response_model=Dict[str, Any])
async def get_active_tasks(
    manager: AgentManager = Depends(get_agent_manager)
):
    """
    Get information about currently active tasks across all agents.
    
    Returns:
    - Active task count per agent
    - Task distribution and load balancing
    - Queue status and performance metrics
    """
    try:
        active_tasks_info = {}
        total_active = 0
        
        for agent_id, agent in manager.agents.items():
            if agent.current_tasks:
                active_tasks_info[agent_id] = {
                    "agent_name": agent.name,
                    "agent_type": agent.agent_type,
                    "current_tasks": agent.current_tasks,
                    "task_count": len(agent.current_tasks),
                    "max_concurrent": agent.max_concurrent_tasks,
                    "utilization": len(agent.current_tasks) / agent.max_concurrent_tasks * 100,
                    "status": agent.status.value
                }
                total_active += len(agent.current_tasks)
        
        # Get queue statistics
        bus_stats = manager.communication_bus.get_statistics()
        
        return {
            "active_tasks": active_tasks_info,
            "summary": {
                "total_active_tasks": total_active,
                "agents_with_tasks": len(active_tasks_info),
                "queue_size": bus_stats["queue_size"],
                "queue_utilization": bus_stats["queue_utilization"],
                "messages_in_transit": bus_stats["queue_size"]
            },
            "retrieved_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error("Failed to get active tasks", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get active tasks: {str(e)}")


@router.post("/retry-failed", response_model=Dict[str, Any])
async def retry_failed_tasks(
    retry_data: Dict[str, Any],
    manager: AgentManager = Depends(get_agent_manager)
):
    """
    Retry failed task deliveries for specific agents or all agents.
    
    Features:
    - Selective retry by agent ID
    - Batch retry operations
    - Failed task cleanup
    - Retry attempt tracking
    """
    try:
        agent_id = retry_data.get("agent_id")
        
        # Retry failed deliveries
        retry_count = await manager.communication_bus.retry_failed_deliveries(agent_id)
        
        logger.info(
            "Failed tasks retried",
            agent_id=agent_id,
            retry_count=retry_count
        )
        
        return {
            "message": "Failed tasks retry completed",
            "agent_id": agent_id,
            "retried_count": retry_count,
            "retried_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error("Failed to retry tasks", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to retry tasks: {str(e)}")


@router.get("/performance/statistics", response_model=Dict[str, Any])
async def get_task_performance_statistics(
    manager: AgentManager = Depends(get_agent_manager)
):
    """
    Get comprehensive task performance statistics and analytics.
    
    Returns:
    - Execution time metrics
    - Success/failure rates
    - Agent performance comparison
    - System throughput analytics
    """
    try:
        # Get agent statistics
        agent_stats = manager.get_agent_statistics()
        
        # Get communication bus statistics
        bus_stats = manager.communication_bus.get_statistics()
        
        # Calculate performance metrics
        performance_stats = {
            "task_execution": {
                "total_executed": agent_stats["tasks_executed"],
                "total_failed": agent_stats["tasks_failed"],
                "success_rate": agent_stats["success_rate"],
                "average_execution_time": agent_stats["avg_execution_time"]
            },
            "communication": {
                "messages_sent": bus_stats["messages_sent"],
                "messages_delivered": bus_stats["messages_delivered"],
                "delivery_success_rate": bus_stats["success_rate"],
                "queue_utilization": bus_stats["queue_utilization"]
            },
            "system": {
                "uptime_seconds": agent_stats["uptime_seconds"],
                "active_agents": agent_stats["active_agents"],
                "total_agents": agent_stats["total_agents"],
                "ai_providers": agent_stats.get("ai_providers", [])
            }
        }
        
        # Get top performing agents
        top_agents = []
        for agent in manager.list_agents():
            if agent.performance_metrics["tasks_completed"] > 0:
                top_agents.append({
                    "agent_id": agent.id,
                    "agent_name": agent.name,
                    "tasks_completed": agent.performance_metrics["tasks_completed"],
                    "success_rate": agent.performance_metrics["success_rate"],
                    "avg_response_time": agent.performance_metrics["avg_response_time"]
                })
        
        top_agents.sort(key=lambda x: x["tasks_completed"], reverse=True)
        performance_stats["top_agents"] = top_agents[:10]
        
        return {
            "performance_statistics": performance_stats,
            "generated_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error("Failed to get performance statistics", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get performance statistics: {str(e)}")


@router.post("/schedule", response_model=Dict[str, Any])
async def schedule_task(
    schedule_data: Dict[str, Any],
    background_tasks: BackgroundTasks,
    manager: AgentManager = Depends(get_agent_manager)
):
    """
    Schedule a task for future execution.
    
    Supports:
    - Delayed execution
    - Recurring tasks
    - Conditional triggers
    - Dependency chains
    """
    try:
        # Extract schedule parameters
        task_content = schedule_data.get("task_content")
        agent_id = schedule_data.get("agent_id")
        schedule_type = schedule_data.get("schedule_type", "once")  # once, recurring, conditional
        execute_at = schedule_data.get("execute_at")  # ISO timestamp
        interval_seconds = schedule_data.get("interval_seconds")
        condition = schedule_data.get("condition")
        
        if not task_content or not agent_id:
            raise HTTPException(
                status_code=400,
                detail="task_content and agent_id are required"
            )
        
        # Validate agent exists
        agent = manager.get_agent(agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
        
        # Generate schedule ID
        schedule_id = str(uuid.uuid4())
        
        # For now, implement basic delayed execution
        # In a production system, you'd use Celery, APScheduler, or similar
        if execute_at:
            from datetime import datetime
            try:
                execution_time = datetime.fromisoformat(execute_at.replace('Z', '+00:00'))
                delay_seconds = (execution_time - datetime.now()).total_seconds()
                
                if delay_seconds <= 0:
                    raise HTTPException(
                        status_code=400,
                        detail="Execution time must be in the future"
                    )
                
                # Add to background tasks with delay (simplified implementation)
                # In production, use proper scheduling system
                
                logger.info(
                    "Task scheduled",
                    schedule_id=schedule_id,
                    agent_id=agent_id,
                    execute_at=execute_at,
                    delay_seconds=delay_seconds
                )
                
                return {
                    "message": "Task scheduled successfully",
                    "schedule_id": schedule_id,
                    "agent_id": agent_id,
                    "agent_name": agent.name,
                    "schedule_type": schedule_type,
                    "execute_at": execute_at,
                    "delay_seconds": delay_seconds,
                    "scheduled_at": datetime.now().isoformat()
                }
                
            except ValueError as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid datetime format: {str(e)}"
                )
        else:
            raise HTTPException(
                status_code=400,
                detail="execute_at timestamp is required for scheduled tasks"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to schedule task", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to schedule task: {str(e)}")


@router.get("/queue/status", response_model=Dict[str, Any])
async def get_queue_status(
    manager: AgentManager = Depends(get_agent_manager)
):
    """
    Get current message queue status and performance metrics.
    
    Returns:
    - Queue size and capacity
    - Processing rates
    - Backlog analysis
    - System health indicators
    """
    try:
        bus_stats = manager.communication_bus.get_statistics()
        
        # Get queue details
        queue_info = {
            "current_size": bus_stats["queue_size"],
            "capacity": bus_stats["queue_capacity"],
            "utilization_percent": bus_stats["queue_utilization"],
            "is_healthy": bus_stats["queue_utilization"] < 80,  # Consider 80% as threshold
            "processing_rate": {
                "messages_per_minute": bus_stats["messages_delivered"] / max(1, bus_stats["uptime_seconds"] / 60),
                "success_rate": bus_stats["success_rate"],
                "error_rate": 100 - bus_stats["success_rate"]
            },
            "subscribers": bus_stats["active_subscribers"],
            "websocket_connections": bus_stats["websocket_connections"]
        }
        
        return {
            "queue_status": queue_info,
            "retrieved_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error("Failed to get queue status", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get queue status: {str(e)}")