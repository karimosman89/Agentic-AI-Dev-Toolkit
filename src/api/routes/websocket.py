#!/usr/bin/env python3
"""
WebSocket API Routes
===================

Real-time communication endpoints for live updates and monitoring.

Author: Karim Osman
License: MIT
"""

import json
import asyncio
from datetime import datetime
from typing import Dict, Any, List
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Request, Query
from fastapi.responses import HTMLResponse
import structlog

from ...core.agent_manager import AgentManager
from ...core.models import Message, MessageType
from ...core.config import Settings


router = APIRouter()
logger = structlog.get_logger(__name__)


def get_agent_manager(request: Request) -> AgentManager:
    """Dependency to get agent manager from app state."""
    return request.app.state.agent_manager


def get_settings(request: Request) -> Settings:
    """Dependency to get settings from app state."""
    return request.app.state.settings


class ConnectionManager:
    """
    WebSocket connection manager for handling multiple clients.
    
    Features:
    - Connection lifecycle management
    - Message broadcasting
    - Client-specific filtering
    - Connection health monitoring
    """
    
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.client_subscriptions: Dict[str, Dict[str, Any]] = {}
        self.logger = structlog.get_logger(__name__)
    
    async def connect(self, websocket: WebSocket, client_id: str):
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        self.active_connections[client_id] = websocket
        self.client_subscriptions[client_id] = {
            "connected_at": datetime.now().isoformat(),
            "filters": {},
            "last_ping": datetime.now().isoformat()
        }
        
        self.logger.info("WebSocket client connected", client_id=client_id, total_connections=len(self.active_connections))
    
    def disconnect(self, client_id: str):
        """Remove a WebSocket connection."""
        if client_id in self.active_connections:
            del self.active_connections[client_id]
        if client_id in self.client_subscriptions:
            del self.client_subscriptions[client_id]
            
        self.logger.info("WebSocket client disconnected", client_id=client_id, remaining_connections=len(self.active_connections))
    
    async def send_personal_message(self, message: Dict[str, Any], client_id: str):
        """Send a message to a specific client."""
        if client_id in self.active_connections:
            try:
                websocket = self.active_connections[client_id]
                await websocket.send_text(json.dumps(message))
            except Exception as e:
                self.logger.warning("Failed to send message to client", client_id=client_id, error=str(e))
                self.disconnect(client_id)
    
    async def broadcast_message(self, message: Dict[str, Any], filter_func=None):
        """Broadcast a message to all connected clients with optional filtering."""
        disconnected_clients = []
        
        for client_id, websocket in self.active_connections.items():
            try:
                # Apply filter if provided
                if filter_func and not filter_func(client_id, self.client_subscriptions.get(client_id, {})):
                    continue
                
                await websocket.send_text(json.dumps(message))
                
            except Exception as e:
                self.logger.warning("Failed to broadcast to client", client_id=client_id, error=str(e))
                disconnected_clients.append(client_id)
        
        # Clean up disconnected clients
        for client_id in disconnected_clients:
            self.disconnect(client_id)
    
    def get_connection_stats(self) -> Dict[str, Any]:
        """Get connection statistics."""
        return {
            "total_connections": len(self.active_connections),
            "connected_clients": list(self.active_connections.keys()),
            "connection_details": self.client_subscriptions
        }


# Global connection manager
connection_manager = ConnectionManager()


@router.websocket("/events")
async def websocket_events_endpoint(
    websocket: WebSocket,
    client_id: str = Query(..., description="Unique client identifier"),
    agent_manager: AgentManager = Depends(get_agent_manager)  # This won't work directly in WebSocket
):
    """
    WebSocket endpoint for real-time event streaming.
    
    Provides:
    - Agent status updates
    - Task execution events
    - System alerts and notifications
    - Performance metrics updates
    """
    await connection_manager.connect(websocket, client_id)
    
    try:
        # Send welcome message
        welcome_msg = {
            "type": "connection_established",
            "client_id": client_id,
            "timestamp": datetime.now().isoformat(),
            "message": "Connected to Agentic AI Toolkit WebSocket"
        }
        await connection_manager.send_personal_message(welcome_msg, client_id)
        
        # Main message loop
        while True:
            try:
                # Receive message from client
                data = await websocket.receive_text()
                message = json.loads(data)
                
                # Handle different message types
                await handle_client_message(message, client_id, websocket)
                
            except WebSocketDisconnect:
                break
                
            except json.JSONDecodeError:
                error_msg = {
                    "type": "error",
                    "error": "Invalid JSON format",
                    "timestamp": datetime.now().isoformat()
                }
                await connection_manager.send_personal_message(error_msg, client_id)
                
            except Exception as e:
                logger.error("WebSocket message handling error", client_id=client_id, error=str(e))
                error_msg = {
                    "type": "error",
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                }
                await connection_manager.send_personal_message(error_msg, client_id)
                
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("WebSocket connection error", client_id=client_id, error=str(e))
    finally:
        connection_manager.disconnect(client_id)


async def handle_client_message(message: Dict[str, Any], client_id: str, websocket: WebSocket):
    """Handle incoming messages from WebSocket clients."""
    message_type = message.get("type", "unknown")
    
    if message_type == "ping":
        # Handle ping/keepalive
        connection_manager.client_subscriptions[client_id]["last_ping"] = datetime.now().isoformat()
        response = {
            "type": "pong",
            "timestamp": datetime.now().isoformat()
        }
        await connection_manager.send_personal_message(response, client_id)
        
    elif message_type == "subscribe":
        # Handle subscription filters
        filters = message.get("filters", {})
        connection_manager.client_subscriptions[client_id]["filters"] = filters
        
        response = {
            "type": "subscription_updated",
            "filters": filters,
            "timestamp": datetime.now().isoformat()
        }
        await connection_manager.send_personal_message(response, client_id)
        
    elif message_type == "get_status":
        # Send current system status
        # Note: We can't use dependency injection in WebSocket handlers
        # In production, you'd pass the agent_manager differently
        status_msg = {
            "type": "system_status",
            "data": {
                "message": "System status would be retrieved here",
                "active_connections": len(connection_manager.active_connections)
            },
            "timestamp": datetime.now().isoformat()
        }
        await connection_manager.send_personal_message(status_msg, client_id)
        
    else:
        # Unknown message type
        response = {
            "type": "error",
            "error": f"Unknown message type: {message_type}",
            "timestamp": datetime.now().isoformat()
        }
        await connection_manager.send_personal_message(response, client_id)


@router.get("/test-client", response_class=HTMLResponse)
async def websocket_test_client():
    """
    Simple WebSocket test client for development and testing.
    
    Returns an HTML page with JavaScript WebSocket client for testing.
    """
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>🤖 Agentic AI WebSocket Test Client</title>
        <style>
            body { 
                font-family: 'Monaco', 'Menlo', 'Consolas', monospace; 
                margin: 20px; 
                background: #1e1e1e; 
                color: #d4d4d4; 
            }
            .container { 
                max-width: 1200px; 
                margin: 0 auto; 
                background: #2d2d2d; 
                padding: 20px; 
                border-radius: 8px; 
            }
            .header { 
                text-align: center; 
                margin-bottom: 30px; 
                color: #569cd6; 
            }
            .connection-status { 
                padding: 10px; 
                margin: 10px 0; 
                border-radius: 4px; 
                font-weight: bold; 
            }
            .connected { background: #0e5a2b; color: #4ec9b0; }
            .disconnected { background: #5a1e1e; color: #f44747; }
            .controls { 
                display: flex; 
                gap: 10px; 
                margin: 20px 0; 
                flex-wrap: wrap; 
            }
            button { 
                padding: 10px 15px; 
                background: #0e639c; 
                color: white; 
                border: none; 
                border-radius: 4px; 
                cursor: pointer; 
                font-family: inherit; 
            }
            button:hover { background: #1177bb; }
            button:disabled { background: #666; cursor: not-allowed; }
            .message-area { 
                display: grid; 
                grid-template-columns: 1fr 1fr; 
                gap: 20px; 
                margin-top: 20px; 
            }
            textarea, .log-area { 
                width: 100%; 
                height: 300px; 
                background: #1e1e1e; 
                color: #d4d4d4; 
                border: 1px solid #3e3e3e; 
                border-radius: 4px; 
                padding: 10px; 
                font-family: inherit; 
                resize: vertical; 
            }
            .log-area { 
                overflow-y: auto; 
                white-space: pre-wrap; 
            }
            .timestamp { color: #608b4e; }
            .message-type { color: #569cd6; font-weight: bold; }
            .error { color: #f44747; }
            .success { color: #4ec9b0; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🤖 Agentic AI WebSocket Test Client</h1>
                <p>Real-time communication testing interface</p>
            </div>
            
            <div id="status" class="connection-status disconnected">
                Disconnected
            </div>
            
            <div class="controls">
                <button onclick="connect()">Connect</button>
                <button onclick="disconnect()">Disconnect</button>
                <button onclick="sendPing()">Send Ping</button>
                <button onclick="getStatus()">Get Status</button>
                <button onclick="subscribe()">Subscribe to Events</button>
                <button onclick="clearLog()">Clear Log</button>
            </div>
            
            <div class="message-area">
                <div>
                    <h3>Send Message</h3>
                    <textarea id="messageInput" placeholder='{"type": "ping"}'></textarea>
                    <br><br>
                    <button onclick="sendCustomMessage()">Send Custom Message</button>
                </div>
                
                <div>
                    <h3>Message Log</h3>
                    <div id="log" class="log-area"></div>
                </div>
            </div>
        </div>

        <script>
            let socket = null;
            const clientId = 'test-client-' + Math.random().toString(36).substr(2, 9);
            
            function log(message, type = 'info') {
                const logArea = document.getElementById('log');
                const timestamp = new Date().toISOString();
                const className = type === 'error' ? 'error' : type === 'success' ? 'success' : '';
                
                logArea.innerHTML += `<span class="timestamp">[${timestamp}]</span> <span class="${className}">${message}</span>\\n`;
                logArea.scrollTop = logArea.scrollHeight;
            }
            
            function updateStatus(connected) {
                const statusEl = document.getElementById('status');
                if (connected) {
                    statusEl.textContent = `Connected (Client ID: ${clientId})`;
                    statusEl.className = 'connection-status connected';
                } else {
                    statusEl.textContent = 'Disconnected';
                    statusEl.className = 'connection-status disconnected';
                }
            }
            
            function connect() {
                if (socket && socket.readyState === WebSocket.OPEN) {
                    log('Already connected', 'error');
                    return;
                }
                
                const wsUrl = `ws://localhost:8080/api/v1/ws/events?client_id=${clientId}`;
                log(`Connecting to ${wsUrl}...`);
                
                socket = new WebSocket(wsUrl);
                
                socket.onopen = function(event) {
                    log('Connected successfully!', 'success');
                    updateStatus(true);
                };
                
                socket.onmessage = function(event) {
                    try {
                        const data = JSON.parse(event.data);
                        log(`<span class="message-type">[${data.type}]</span> ${JSON.stringify(data, null, 2)}`, 'success');
                    } catch (e) {
                        log(`Received: ${event.data}`, 'success');
                    }
                };
                
                socket.onclose = function(event) {
                    log(`Connection closed (Code: ${event.code})`, 'error');
                    updateStatus(false);
                };
                
                socket.onerror = function(error) {
                    log(`WebSocket error: ${error}`, 'error');
                    updateStatus(false);
                };
            }
            
            function disconnect() {
                if (socket) {
                    socket.close();
                    socket = null;
                    log('Disconnected');
                    updateStatus(false);
                }
            }
            
            function sendMessage(message) {
                if (!socket || socket.readyState !== WebSocket.OPEN) {
                    log('Not connected!', 'error');
                    return;
                }
                
                const messageStr = JSON.stringify(message);
                socket.send(messageStr);
                log(`Sent: ${messageStr}`);
            }
            
            function sendPing() {
                sendMessage({ type: 'ping' });
            }
            
            function getStatus() {
                sendMessage({ type: 'get_status' });
            }
            
            function subscribe() {
                sendMessage({ 
                    type: 'subscribe', 
                    filters: { 
                        agent_events: true, 
                        task_events: true, 
                        system_alerts: true 
                    } 
                });
            }
            
            function sendCustomMessage() {
                const input = document.getElementById('messageInput');
                try {
                    const message = JSON.parse(input.value);
                    sendMessage(message);
                } catch (e) {
                    log(`Invalid JSON: ${e.message}`, 'error');
                }
            }
            
            function clearLog() {
                document.getElementById('log').innerHTML = '';
            }
            
            // Initialize
            updateStatus(false);
            document.getElementById('messageInput').value = '{"type": "ping"}';
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@router.get("/connections")
async def get_websocket_connections():
    """Get information about active WebSocket connections."""
    return {
        "connections": connection_manager.get_connection_stats(),
        "timestamp": datetime.now().isoformat()
    }


@router.post("/broadcast")
async def broadcast_message(
    broadcast_data: Dict[str, Any]
):
    """
    Broadcast a message to all connected WebSocket clients.
    
    Useful for sending system-wide notifications or alerts.
    """
    try:
        message_type = broadcast_data.get("type", "notification")
        content = broadcast_data.get("content", {})
        target_filters = broadcast_data.get("filters", {})
        
        broadcast_message = {
            "type": message_type,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "source": "api_broadcast"
        }
        
        # Define filter function if filters are provided
        filter_func = None
        if target_filters:
            def filter_func(client_id, subscription_info):
                client_filters = subscription_info.get("filters", {})
                
                # Check if client has matching filters
                for filter_key, filter_value in target_filters.items():
                    if client_filters.get(filter_key) != filter_value:
                        return False
                return True
        
        # Broadcast to matching clients
        await connection_manager.broadcast_message(broadcast_message, filter_func)
        
        affected_clients = len(connection_manager.active_connections)
        if filter_func:
            # Count matching clients
            affected_clients = sum(
                1 for client_id, subscription_info in connection_manager.client_subscriptions.items()
                if filter_func(client_id, subscription_info)
            )
        
        logger.info("Message broadcasted", message_type=message_type, affected_clients=affected_clients)
        
        return {
            "message": "Broadcast sent successfully",
            "message_type": message_type,
            "affected_clients": affected_clients,
            "total_connections": len(connection_manager.active_connections),
            "sent_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error("Failed to broadcast message", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to broadcast message: {str(e)}")


# Background task to send periodic updates
async def periodic_updates_task():
    """
    Background task to send periodic system updates to WebSocket clients.
    
    This would run continuously to provide real-time monitoring data.
    """
    while True:
        try:
            if connection_manager.active_connections:
                # Send periodic status update
                status_update = {
                    "type": "periodic_update",
                    "data": {
                        "timestamp": datetime.now().isoformat(),
                        "active_connections": len(connection_manager.active_connections),
                        "server_status": "running"
                    }
                }
                
                await connection_manager.broadcast_message(status_update)
            
            # Wait 30 seconds before next update
            await asyncio.sleep(30)
            
        except Exception as e:
            logger.error("Periodic updates task error", error=str(e))
            await asyncio.sleep(30)  # Continue despite errors


# Function to integrate with agent manager for real-time events
async def setup_realtime_integration(agent_manager: AgentManager):
    """
    Setup integration between agent manager and WebSocket broadcasts.
    
    This would be called during application startup to connect
    agent events to WebSocket notifications.
    """
    try:
        # Add WebSocket clients to communication bus
        for client_id, websocket in connection_manager.active_connections.items():
            agent_manager.communication_bus.add_websocket_client(websocket)
        
        logger.info("Real-time integration setup completed")
        
    except Exception as e:
        logger.error("Failed to setup real-time integration", error=str(e))