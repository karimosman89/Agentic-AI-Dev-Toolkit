#!/usr/bin/env python3
"""
System Monitoring API Routes
============================

Comprehensive monitoring endpoints for system health, metrics, and performance.

Author: Karim Osman
License: MIT
"""

import psutil
import platform
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends, Request, Query
import structlog

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


@router.get("/health")
async def health_check(
    manager: AgentManager = Depends(get_agent_manager),
    settings: Settings = Depends(get_settings)
):
    """
    Comprehensive health check endpoint.
    
    Returns system status, component health, and critical metrics
    for monitoring and alerting systems.
    """
    try:
        # System health checks
        health_status = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "version": "2.0.0",
            "environment": settings.environment
        }
        
        # Component health checks
        components = {}
        
        # Agent Manager Health
        try:
            agent_stats = manager.get_agent_statistics()
            components["agent_manager"] = {
                "status": "healthy",
                "active_agents": agent_stats["active_agents"],
                "total_agents": agent_stats["total_agents"],
                "uptime_seconds": agent_stats["uptime_seconds"]
            }
        except Exception as e:
            components["agent_manager"] = {
                "status": "unhealthy",
                "error": str(e)
            }
            health_status["status"] = "degraded"
        
        # Communication Bus Health
        try:
            bus_stats = manager.communication_bus.get_statistics()
            queue_health = "healthy" if bus_stats["queue_utilization"] < 90 else "warning"
            
            components["communication_bus"] = {
                "status": queue_health,
                "queue_utilization": bus_stats["queue_utilization"],
                "active_subscribers": bus_stats["active_subscribers"],
                "success_rate": bus_stats["success_rate"]
            }
            
            if queue_health == "warning":
                health_status["status"] = "degraded"
                
        except Exception as e:
            components["communication_bus"] = {
                "status": "unhealthy",
                "error": str(e)
            }
            health_status["status"] = "degraded"
        
        # Tool Registry Health
        try:
            tool_stats = manager.tool_registry.get_tool_statistics()
            components["tool_registry"] = {
                "status": "healthy",
                "total_tools": tool_stats["total_tools"],
                "success_rate": tool_stats["success_rate"]
            }
        except Exception as e:
            components["tool_registry"] = {
                "status": "unhealthy", 
                "error": str(e)
            }
            health_status["status"] = "degraded"
        
        # System Resources Health
        try:
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            memory_status = "healthy" if memory.percent < 85 else "warning"
            disk_status = "healthy" if disk.percent < 90 else "warning"
            
            components["system_resources"] = {
                "status": "healthy" if memory_status == "healthy" and disk_status == "healthy" else "warning",
                "memory_percent": memory.percent,
                "disk_percent": disk.percent,
                "cpu_percent": psutil.cpu_percent(interval=1)
            }
            
            if memory_status == "warning" or disk_status == "warning":
                health_status["status"] = "degraded"
                
        except Exception as e:
            components["system_resources"] = {
                "status": "unknown",
                "error": str(e)
            }
        
        health_status["components"] = components
        
        # Determine overall status
        component_statuses = [comp.get("status", "unknown") for comp in components.values()]
        if "unhealthy" in component_statuses:
            health_status["status"] = "unhealthy"
        elif "warning" in component_statuses or "degraded" in component_statuses:
            health_status["status"] = "degraded"
        
        return health_status
        
    except Exception as e:
        logger.error("Health check failed", error=str(e))
        return {
            "status": "unhealthy",
            "timestamp": datetime.now().isoformat(),
            "error": str(e)
        }


@router.get("/metrics")
async def get_system_metrics(
    manager: AgentManager = Depends(get_agent_manager)
):
    """
    Get comprehensive system metrics for monitoring dashboards.
    
    Returns detailed performance metrics, resource usage,
    and operational statistics.
    """
    try:
        # Get core metrics
        agent_stats = manager.get_agent_statistics()
        bus_stats = manager.communication_bus.get_statistics()
        tool_stats = manager.tool_registry.get_tool_statistics()
        
        # System metrics
        try:
            system_metrics = {
                "cpu": {
                    "percent": psutil.cpu_percent(interval=1),
                    "count": psutil.cpu_count(),
                    "freq": psutil.cpu_freq()._asdict() if psutil.cpu_freq() else None
                },
                "memory": psutil.virtual_memory()._asdict(),
                "disk": psutil.disk_usage('/')._asdict(),
                "platform": {
                    "system": platform.system(),
                    "platform": platform.platform(),
                    "python_version": platform.python_version()
                }
            }
        except Exception as e:
            system_metrics = {"error": str(e)}
        
        # Application metrics
        app_metrics = {
            "agents": {
                "total": agent_stats["total_agents"],
                "active": agent_stats["active_agents"],
                "tasks_executed": agent_stats["tasks_executed"],
                "tasks_failed": agent_stats["tasks_failed"],
                "success_rate": agent_stats["success_rate"],
                "avg_execution_time": agent_stats["avg_execution_time"],
                "uptime_seconds": agent_stats["uptime_seconds"]
            },
            "communication": {
                "messages_sent": bus_stats["messages_sent"],
                "messages_delivered": bus_stats["messages_delivered"], 
                "success_rate": bus_stats["success_rate"],
                "queue_size": bus_stats["queue_size"],
                "queue_utilization": bus_stats["queue_utilization"],
                "active_subscribers": bus_stats["active_subscribers"],
                "websocket_connections": bus_stats["websocket_connections"]
            },
            "tools": {
                "total_tools": tool_stats["total_tools"],
                "total_executions": tool_stats["total_executions"],
                "success_rate": tool_stats["success_rate"],
                "most_used": tool_stats["most_used_tools"][:5]  # Top 5
            }
        }
        
        return {
            "system": system_metrics,
            "application": app_metrics,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error("Failed to get metrics", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get metrics: {str(e)}")


@router.get("/performance")
async def get_performance_analytics(
    hours: int = Query(24, ge=1, le=168, description="Hours of data to analyze"),
    manager: AgentManager = Depends(get_agent_manager)
):
    """
    Get performance analytics and trends over time.
    
    Returns performance trends, bottleneck analysis,
    and optimization recommendations.
    """
    try:
        # Get current performance snapshot
        agent_stats = manager.get_agent_statistics()
        bus_stats = manager.communication_bus.get_statistics()
        
        # Calculate performance metrics
        performance_data = {
            "current_snapshot": {
                "timestamp": datetime.now().isoformat(),
                "agents": {
                    "total": agent_stats["total_agents"],
                    "active": agent_stats["active_agents"],
                    "utilization": (agent_stats["active_agents"] / max(1, agent_stats["total_agents"])) * 100
                },
                "tasks": {
                    "total_executed": agent_stats["tasks_executed"],
                    "success_rate": agent_stats["success_rate"],
                    "avg_execution_time": agent_stats["avg_execution_time"],
                    "throughput_per_hour": agent_stats["tasks_executed"] / max(1, agent_stats["uptime_seconds"] / 3600)
                },
                "communication": {
                    "queue_utilization": bus_stats["queue_utilization"],
                    "message_throughput": bus_stats["messages_delivered"] / max(1, bus_stats["uptime_seconds"] / 3600),
                    "delivery_success_rate": bus_stats["success_rate"]
                }
            },
            "performance_indicators": {
                "system_health": "healthy" if bus_stats["queue_utilization"] < 80 else "warning",
                "bottlenecks": [],
                "recommendations": []
            }
        }
        
        # Identify bottlenecks and recommendations
        bottlenecks = []
        recommendations = []
        
        if bus_stats["queue_utilization"] > 80:
            bottlenecks.append("High message queue utilization")
            recommendations.append("Consider increasing queue capacity or adding more agents")
        
        if agent_stats["success_rate"] < 90:
            bottlenecks.append("Low task success rate")
            recommendations.append("Review agent configurations and error logs")
        
        if agent_stats["avg_execution_time"] > 30:
            bottlenecks.append("High average task execution time")
            recommendations.append("Optimize tool implementations or increase timeout limits")
        
        agent_utilization = (agent_stats["active_agents"] / max(1, agent_stats["total_agents"])) * 100
        if agent_utilization > 90:
            bottlenecks.append("High agent utilization")
            recommendations.append("Consider creating more agents to distribute load")
        
        performance_data["performance_indicators"]["bottlenecks"] = bottlenecks
        performance_data["performance_indicators"]["recommendations"] = recommendations
        
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
        
        top_agents.sort(key=lambda x: x["success_rate"], reverse=True)
        performance_data["top_performers"] = top_agents[:10]
        
        return performance_data
        
    except Exception as e:
        logger.error("Failed to get performance analytics", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get performance analytics: {str(e)}")


@router.get("/logs/recent")
async def get_recent_logs(
    level: Optional[str] = Query("INFO", description="Log level filter"),
    limit: int = Query(100, ge=1, le=1000, description="Number of log entries"),
    component: Optional[str] = Query(None, description="Filter by component")
):
    """
    Get recent log entries for system monitoring and debugging.
    
    Returns filtered log entries with timestamps and context.
    """
    try:
        # In a production system, this would read from actual log files
        # For now, return a structured response indicating log access
        
        return {
            "message": "Log access endpoint",
            "note": "In production, this would return actual log entries from log files",
            "filters": {
                "level": level,
                "limit": limit,
                "component": component
            },
            "log_files": [
                "/home/user/webapp/logs/agent_manager.log",
                "/home/user/webapp/logs/api_server.log",
                "/home/user/webapp/logs/system.log"
            ],
            "sample_entry": {
                "timestamp": datetime.now().isoformat(),
                "level": "INFO",
                "component": "agent_manager",
                "message": "Agent created successfully",
                "context": {"agent_id": "abc123", "agent_name": "example"}
            }
        }
        
    except Exception as e:
        logger.error("Failed to get logs", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get logs: {str(e)}")


@router.get("/alerts")
async def get_system_alerts(
    severity: Optional[str] = Query(None, description="Filter by severity"),
    manager: AgentManager = Depends(get_agent_manager)
):
    """
    Get current system alerts and warnings.
    
    Returns active alerts based on system thresholds and conditions.
    """
    try:
        alerts = []
        
        # Check system resource alerts
        try:
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            cpu_percent = psutil.cpu_percent(interval=1)
            
            if memory.percent > 90:
                alerts.append({
                    "id": "memory_high",
                    "severity": "critical",
                    "title": "High Memory Usage",
                    "message": f"Memory usage at {memory.percent:.1f}%",
                    "timestamp": datetime.now().isoformat(),
                    "component": "system"
                })
            elif memory.percent > 80:
                alerts.append({
                    "id": "memory_warning",
                    "severity": "warning",
                    "title": "Memory Usage Warning",
                    "message": f"Memory usage at {memory.percent:.1f}%",
                    "timestamp": datetime.now().isoformat(),
                    "component": "system"
                })
            
            if disk.percent > 95:
                alerts.append({
                    "id": "disk_critical",
                    "severity": "critical",
                    "title": "Disk Space Critical",
                    "message": f"Disk usage at {disk.percent:.1f}%",
                    "timestamp": datetime.now().isoformat(),
                    "component": "system"
                })
            
            if cpu_percent > 95:
                alerts.append({
                    "id": "cpu_high",
                    "severity": "warning",
                    "title": "High CPU Usage",
                    "message": f"CPU usage at {cpu_percent:.1f}%",
                    "timestamp": datetime.now().isoformat(),
                    "component": "system"
                })
                
        except Exception as e:
            alerts.append({
                "id": "system_monitoring_error",
                "severity": "warning",
                "title": "System Monitoring Error",
                "message": f"Unable to get system metrics: {str(e)}",
                "timestamp": datetime.now().isoformat(),
                "component": "monitoring"
            })
        
        # Check application alerts
        try:
            bus_stats = manager.communication_bus.get_statistics()
            
            if bus_stats["queue_utilization"] > 90:
                alerts.append({
                    "id": "queue_critical",
                    "severity": "critical", 
                    "title": "Message Queue Critical",
                    "message": f"Queue utilization at {bus_stats['queue_utilization']:.1f}%",
                    "timestamp": datetime.now().isoformat(),
                    "component": "communication_bus"
                })
            elif bus_stats["queue_utilization"] > 80:
                alerts.append({
                    "id": "queue_warning",
                    "severity": "warning",
                    "title": "Message Queue Warning", 
                    "message": f"Queue utilization at {bus_stats['queue_utilization']:.1f}%",
                    "timestamp": datetime.now().isoformat(),
                    "component": "communication_bus"
                })
            
            if bus_stats["success_rate"] < 95:
                alerts.append({
                    "id": "delivery_rate_low",
                    "severity": "warning",
                    "title": "Low Message Delivery Rate",
                    "message": f"Success rate at {bus_stats['success_rate']:.1f}%",
                    "timestamp": datetime.now().isoformat(),
                    "component": "communication_bus"
                })
                
        except Exception as e:
            alerts.append({
                "id": "app_monitoring_error",
                "severity": "warning",
                "title": "Application Monitoring Error",
                "message": f"Unable to get application metrics: {str(e)}",
                "timestamp": datetime.now().isoformat(),
                "component": "monitoring"
            })
        
        # Filter by severity if specified
        if severity:
            alerts = [alert for alert in alerts if alert["severity"] == severity.lower()]
        
        return {
            "alerts": alerts,
            "total_count": len(alerts),
            "severity_counts": {
                "critical": len([a for a in alerts if a["severity"] == "critical"]),
                "warning": len([a for a in alerts if a["severity"] == "warning"]),
                "info": len([a for a in alerts if a["severity"] == "info"])
            },
            "generated_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error("Failed to get alerts", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get alerts: {str(e)}")


@router.get("/diagnostics")
async def run_system_diagnostics(
    manager: AgentManager = Depends(get_agent_manager),
    settings: Settings = Depends(get_settings)
):
    """
    Run comprehensive system diagnostics and health tests.
    
    Returns detailed diagnostic information for troubleshooting.
    """
    try:
        diagnostics = {
            "timestamp": datetime.now().isoformat(),
            "test_results": {},
            "recommendations": [],
            "system_info": {}
        }
        
        # System Information
        diagnostics["system_info"] = {
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "environment": settings.environment,
            "debug_mode": settings.debug,
            "uptime": "calculated_from_metrics"
        }
        
        # Test Agent Manager
        try:
            agent_count = len(manager.agents)
            tool_count = len(manager.tool_registry.tools)
            
            diagnostics["test_results"]["agent_manager"] = {
                "status": "pass",
                "agents_registered": agent_count,
                "tools_available": tool_count,
                "ai_providers": list(manager.ai_clients.keys()) if hasattr(manager, 'ai_clients') else []
            }
        except Exception as e:
            diagnostics["test_results"]["agent_manager"] = {
                "status": "fail",
                "error": str(e)
            }
            diagnostics["recommendations"].append("Check agent manager initialization")
        
        # Test Communication Bus
        try:
            bus_stats = manager.communication_bus.get_statistics()
            diagnostics["test_results"]["communication_bus"] = {
                "status": "pass",
                "queue_size": bus_stats["queue_size"],
                "subscribers": bus_stats["active_subscribers"],
                "message_throughput": bus_stats.get("messages_delivered", 0)
            }
        except Exception as e:
            diagnostics["test_results"]["communication_bus"] = {
                "status": "fail",
                "error": str(e)
            }
            diagnostics["recommendations"].append("Check communication bus connectivity")
        
        # Test Tool Registry
        try:
            tool_stats = manager.tool_registry.get_tool_statistics()
            diagnostics["test_results"]["tool_registry"] = {
                "status": "pass",
                "total_tools": tool_stats["total_tools"],
                "categories": tool_stats["categories"],
                "success_rate": tool_stats["success_rate"]
            }
        except Exception as e:
            diagnostics["test_results"]["tool_registry"] = {
                "status": "fail",
                "error": str(e)
            }
            diagnostics["recommendations"].append("Check tool registry configuration")
        
        # Overall diagnostic status
        failed_tests = [name for name, result in diagnostics["test_results"].items() 
                       if result.get("status") == "fail"]
        
        diagnostics["overall_status"] = "healthy" if not failed_tests else "issues_detected"
        diagnostics["failed_components"] = failed_tests
        
        return diagnostics
        
    except Exception as e:
        logger.error("Failed to run diagnostics", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to run diagnostics: {str(e)}")


@router.post("/maintenance")
async def trigger_maintenance_tasks(
    maintenance_data: Dict[str, Any],
    manager: AgentManager = Depends(get_agent_manager)
):
    """
    Trigger system maintenance tasks.
    
    Supports cleanup, optimization, and maintenance operations.
    """
    try:
        task_type = maintenance_data.get("task_type", "cleanup")
        
        results = {
            "task_type": task_type,
            "started_at": datetime.now().isoformat(),
            "results": {}
        }
        
        if task_type == "cleanup":
            # Perform cleanup tasks
            cleanup_results = {}
            
            # Clean up expired messages
            try:
                expired_count = manager.communication_bus.message_queue.clear_expired()
                cleanup_results["expired_messages"] = f"Cleaned {expired_count} expired messages"
            except Exception as e:
                cleanup_results["expired_messages"] = f"Error: {str(e)}"
            
            # Clean up old message history
            try:
                history_size = len(manager.communication_bus.message_history)
                cleanup_results["message_history"] = f"Current history size: {history_size} messages"
            except Exception as e:
                cleanup_results["message_history"] = f"Error: {str(e)}"
            
            results["results"] = cleanup_results
            
        elif task_type == "optimization":
            # Perform optimization tasks
            optimization_results = {
                "message": "Optimization tasks would be implemented here",
                "suggestions": [
                    "Analyze agent performance patterns",
                    "Optimize tool execution paths", 
                    "Review resource allocation"
                ]
            }
            results["results"] = optimization_results
            
        else:
            raise HTTPException(status_code=400, detail=f"Unknown maintenance task: {task_type}")
        
        results["completed_at"] = datetime.now().isoformat()
        
        logger.info("Maintenance task completed", task_type=task_type)
        
        return results
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to run maintenance", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to run maintenance: {str(e)}")