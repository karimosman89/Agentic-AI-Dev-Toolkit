#!/usr/bin/env python3
"""
Advanced Communication Bus for Agentic AI Development Toolkit
=============================================================

High-performance, scalable communication infrastructure for inter-agent
messaging with priority queuing, persistence, monitoring, and real-time capabilities.

Author: Karim Osman
License: MIT
"""

import asyncio
import logging
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Callable, Set
from collections import defaultdict, deque
import heapq
from dataclasses import asdict

from .models import Message, MessageType
from .config import get_settings


class MessageQueue:
    """
    Priority-based message queue with advanced features.
    
    Features:
    - Priority-based message ordering
    - Message TTL (Time To Live) support  
    - Batch processing capabilities
    - Statistics collection
    """
    
    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self._queue = []  # Priority heap
        self._counter = 0  # For FIFO ordering within same priority
        self._size = 0
        
    def put(self, message: Message) -> bool:
        """Add message to queue with priority ordering."""
        if self._size >= self.max_size:
            return False
        
        # Higher priority number = higher priority (4=critical, 1=low)
        priority = -message.priority  # Negative for min-heap behavior
        heapq.heappush(self._queue, (priority, self._counter, message))
        self._counter += 1
        self._size += 1
        return True
    
    def get(self) -> Optional[Message]:
        """Get highest priority message from queue."""
        if not self._queue:
            return None
        
        _, _, message = heapq.heappop(self._queue)
        self._size -= 1
        return message
    
    def peek(self) -> Optional[Message]:
        """Peek at next message without removing it."""
        if not self._queue:
            return None
        return self._queue[0][2]
    
    def size(self) -> int:
        """Get current queue size."""
        return self._size
    
    def is_full(self) -> bool:
        """Check if queue is at capacity."""
        return self._size >= self.max_size
    
    def clear_expired(self) -> int:
        """Remove expired messages and return count removed."""
        if not self._queue:
            return 0
        
        current_time = datetime.now()
        expired_count = 0
        new_queue = []
        
        for priority, counter, message in self._queue:
            if message.is_expired():
                expired_count += 1
            else:
                new_queue.append((priority, counter, message))
        
        self._queue = new_queue
        heapq.heapify(self._queue)
        self._size = len(self._queue)
        
        return expired_count


class CommunicationBus:
    """
    Advanced communication bus for inter-agent messaging.
    
    Features:
    - Priority-based message routing
    - Real-time WebSocket support
    - Message persistence and replay
    - Advanced filtering and routing rules
    - Performance monitoring and metrics
    - Broadcast and multicast capabilities
    """
    
    def __init__(self, settings=None):
        """Initialize the advanced communication bus."""
        self.settings = settings or get_settings()
        self.message_queue = MessageQueue(self.settings.message_queue_size)
        self.subscribers: Dict[str, Callable] = {}
        self.message_history: deque = deque(maxlen=10000)  # Keep last 10k messages
        self.running = False
        self.websocket_clients: Set[Any] = set()
        
        # Advanced features
        self.routing_rules: List[Dict[str, Any]] = []
        self.message_filters: List[Callable] = []
        self.delivery_confirmations: Dict[str, bool] = {}
        self.failed_deliveries: Dict[str, List[Message]] = defaultdict(list)
        
        # Monitoring
        self.metrics = {
            "messages_sent": 0,
            "messages_delivered": 0,
            "messages_failed": 0,
            "messages_expired": 0,
            "total_subscribers": 0,
            "websocket_connections": 0,
            "start_time": datetime.now().isoformat(),
            "last_message_time": None
        }
        
        # Setup logging
        self.logger = logging.getLogger(__name__)
        
        # Background tasks
        self._cleanup_task: Optional[asyncio.Task] = None
        self._processing_task: Optional[asyncio.Task] = None
        
        self.logger.info("📡 Advanced Communication Bus initialized")
    
    async def subscribe(self, agent_id: str, callback: Callable):
        """
        Subscribe an agent to receive messages with enhanced features.
        
        Args:
            agent_id: Unique agent identifier
            callback: Async callback function for message delivery
        """
        if not asyncio.iscoroutinefunction(callback):
            raise ValueError("Callback must be an async function")
        
        self.subscribers[agent_id] = callback
        self.metrics["total_subscribers"] = len(self.subscribers)
        
        self.logger.info(f"📥 Agent '{agent_id}' subscribed to communication bus")
        
        # Send welcome message
        welcome = Message(
            sender="communication_bus",
            recipient=agent_id,
            content={"status": "subscribed", "timestamp": datetime.now().isoformat()},
            message_type=MessageType.STATUS_UPDATE.value
        )
        await self.send_message(welcome)
    
    async def unsubscribe(self, agent_id: str):
        """Unsubscribe an agent from receiving messages."""
        if agent_id in self.subscribers:
            del self.subscribers[agent_id]
            self.metrics["total_subscribers"] = len(self.subscribers)
            
            # Clean up failed delivery queue
            if agent_id in self.failed_deliveries:
                del self.failed_deliveries[agent_id]
            
            self.logger.info(f"📤 Agent '{agent_id}' unsubscribed from communication bus")
    
    async def send_message(self, message: Message) -> bool:
        """
        Send a message through the communication bus with enhanced routing.
        
        Args:
            message: Message to send
            
        Returns:
            True if message was queued successfully
        """
        # Apply message filters
        if not self._apply_filters(message):
            self.logger.debug(f"🚫 Message filtered out: {message.id}")
            return False
        
        # Check message validity
        if message.is_expired():
            self.metrics["messages_expired"] += 1
            self.logger.warning(f"⏰ Expired message discarded: {message.id}")
            return False
        
        # Add to queue
        if not self.message_queue.put(message):
            self.logger.warning(f"📬 Message queue full, dropping message: {message.id}")
            return False
        
        # Update metrics
        self.metrics["messages_sent"] += 1
        self.metrics["last_message_time"] = datetime.now().isoformat()
        
        # Add to history
        self.message_history.append(message)
        
        # Notify WebSocket clients
        await self._notify_websocket_clients(message)
        
        self.logger.debug(f"📨 Message queued: {message.sender} → {message.recipient}")
        return True
    
    def _apply_filters(self, message: Message) -> bool:
        """Apply registered filters to determine if message should be processed."""
        for filter_func in self.message_filters:
            try:
                if not filter_func(message):
                    return False
            except Exception as e:
                self.logger.error(f"❌ Message filter error: {str(e)}")
        return True
    
    async def start(self):
        """Start the communication bus with background processing."""
        if self.running:
            return
        
        self.running = True
        self.logger.info("🚀 Communication bus starting...")
        
        # Start background tasks
        self._processing_task = asyncio.create_task(self._process_messages())
        self._cleanup_task = asyncio.create_task(self._cleanup_expired())
        
        try:
            await asyncio.gather(self._processing_task, self._cleanup_task)
        except asyncio.CancelledError:
            self.logger.info("📡 Communication bus stopped")
    
    async def _process_messages(self):
        """Main message processing loop with advanced routing."""
        while self.running:
            try:
                message = self.message_queue.get()
                if message:
                    await self._route_message(message)
                else:
                    # No messages in queue, short sleep
                    await asyncio.sleep(0.1)
                    
            except Exception as e:
                self.logger.error(f"❌ Message processing error: {str(e)}")
                await asyncio.sleep(1)  # Prevent tight error loop
    
    async def _route_message(self, message: Message):
        """Advanced message routing with rules and delivery confirmation."""
        try:
            # Apply routing rules
            recipients = self._determine_recipients(message)
            
            # Deliver to recipients
            delivery_tasks = []
            for recipient in recipients:
                if recipient in self.subscribers:
                    task = self._deliver_to_subscriber(recipient, message)
                    delivery_tasks.append(task)
            
            # Execute deliveries concurrently
            if delivery_tasks:
                results = await asyncio.gather(*delivery_tasks, return_exceptions=True)
                
                # Process results
                successful_deliveries = sum(1 for r in results if r is True)
                failed_deliveries = len(results) - successful_deliveries
                
                self.metrics["messages_delivered"] += successful_deliveries
                self.metrics["messages_failed"] += failed_deliveries
                
                if failed_deliveries > 0:
                    self.logger.warning(f"⚠️  {failed_deliveries} delivery failures for message {message.id}")
            
        except Exception as e:
            self.metrics["messages_failed"] += 1
            self.logger.error(f"❌ Message routing failed: {str(e)}")
    
    def _determine_recipients(self, message: Message) -> List[str]:
        """Determine message recipients based on routing rules."""
        if message.recipient == "broadcast":
            # Broadcast to all subscribers except sender
            return [agent_id for agent_id in self.subscribers.keys() 
                   if agent_id != message.sender]
        elif message.recipient.startswith("group:"):
            # Group messaging (implement based on your group logic)
            group_name = message.recipient[6:]  # Remove "group:" prefix
            return self._get_group_members(group_name)
        else:
            # Direct message
            return [message.recipient] if message.recipient in self.subscribers else []
    
    def _get_group_members(self, group_name: str) -> List[str]:
        """Get members of a named group (placeholder implementation)."""
        # Implement your group membership logic here
        return []
    
    async def _deliver_to_subscriber(self, recipient: str, message: Message) -> bool:
        """Deliver message to a specific subscriber with retry logic."""
        callback = self.subscribers.get(recipient)
        if not callback:
            return False
        
        try:
            # Create a copy of the message for this recipient
            delivery_message = Message(
                id=message.id,
                sender=message.sender,
                recipient=recipient,
                content=message.content,
                message_type=message.message_type,
                timestamp=message.timestamp,
                metadata=message.metadata.copy(),
                priority=message.priority,
                ttl=message.ttl
            )
            
            # Deliver message
            await callback(delivery_message)
            
            self.logger.debug(f"✅ Message delivered to {recipient}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Delivery failed for {recipient}: {str(e)}")
            
            # Add to failed delivery queue for retry
            self.failed_deliveries[recipient].append(message)
            return False
    
    async def _cleanup_expired(self):
        """Background task to clean up expired messages and failed deliveries."""
        while self.running:
            try:
                # Clean expired messages from queue
                expired_count = self.message_queue.clear_expired()
                if expired_count > 0:
                    self.metrics["messages_expired"] += expired_count
                    self.logger.info(f"🗑️  Cleaned {expired_count} expired messages")
                
                # Clean old failed deliveries
                cutoff_time = datetime.now() - timedelta(hours=1)
                for agent_id, failed_msgs in self.failed_deliveries.items():
                    original_count = len(failed_msgs)
                    # Remove messages older than 1 hour
                    self.failed_deliveries[agent_id] = [
                        msg for msg in failed_msgs 
                        if datetime.fromisoformat(msg.timestamp.replace('Z', '+00:00')) > cutoff_time
                    ]
                    cleaned = original_count - len(self.failed_deliveries[agent_id])
                    if cleaned > 0:
                        self.logger.debug(f"🗑️  Cleaned {cleaned} old failed messages for {agent_id}")
                
                # Sleep for cleanup interval
                await asyncio.sleep(300)  # 5 minutes
                
            except Exception as e:
                self.logger.error(f"❌ Cleanup task error: {str(e)}")
                await asyncio.sleep(60)  # Wait before retrying
    
    def stop(self):
        """Stop the communication bus and cleanup resources."""
        self.running = False
        
        # Cancel background tasks
        if self._processing_task and not self._processing_task.done():
            self._processing_task.cancel()
        
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
        
        self.logger.info("🛑 Communication bus stopped")
    
    def add_message_filter(self, filter_func: Callable[[Message], bool]):
        """
        Add a message filter function.
        
        Args:
            filter_func: Function that takes a Message and returns bool
        """
        self.message_filters.append(filter_func)
        self.logger.info(f"🔍 Message filter added (total: {len(self.message_filters)})")
    
    def add_routing_rule(self, rule: Dict[str, Any]):
        """
        Add a custom routing rule.
        
        Args:
            rule: Routing rule configuration
        """
        self.routing_rules.append(rule)
        self.logger.info(f"📋 Routing rule added (total: {len(self.routing_rules)})")
    
    def get_message_history(
        self, 
        agent_id: str = None,
        message_type: str = None,
        limit: int = 100,
        since: datetime = None
    ) -> List[Message]:
        """
        Get message history with advanced filtering.
        
        Args:
            agent_id: Filter by specific agent (sender or recipient)
            message_type: Filter by message type
            limit: Maximum number of messages to return
            since: Only return messages after this timestamp
            
        Returns:
            Filtered list of messages
        """
        messages = list(self.message_history)
        
        # Apply filters
        if agent_id:
            messages = [
                msg for msg in messages
                if msg.sender == agent_id or msg.recipient == agent_id
            ]
        
        if message_type:
            messages = [
                msg for msg in messages
                if msg.message_type == message_type
            ]
        
        if since:
            messages = [
                msg for msg in messages
                if datetime.fromisoformat(msg.timestamp.replace('Z', '+00:00')) > since
            ]
        
        # Sort by timestamp (most recent first) and limit
        messages.sort(key=lambda x: x.timestamp, reverse=True)
        return messages[:limit]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive communication bus statistics."""
        uptime = (
            datetime.now() - 
            datetime.fromisoformat(self.metrics["start_time"])
        ).total_seconds()
        
        return {
            **self.metrics,
            "uptime_seconds": uptime,
            "queue_size": self.message_queue.size(),
            "queue_capacity": self.message_queue.max_size,
            "queue_utilization": (self.message_queue.size() / self.message_queue.max_size) * 100,
            "history_size": len(self.message_history),
            "active_subscribers": len(self.subscribers),
            "failed_delivery_queues": len(self.failed_deliveries),
            "message_filters": len(self.message_filters),
            "routing_rules": len(self.routing_rules),
            "success_rate": (
                self.metrics["messages_delivered"] / 
                max(1, self.metrics["messages_sent"])
            ) * 100
        }
    
    async def retry_failed_deliveries(self, agent_id: str = None):
        """
        Retry failed message deliveries for specific agent or all agents.
        
        Args:
            agent_id: Specific agent ID to retry (optional)
        """
        retry_count = 0
        
        agents_to_retry = [agent_id] if agent_id else list(self.failed_deliveries.keys())
        
        for aid in agents_to_retry:
            if aid not in self.failed_deliveries:
                continue
            
            failed_msgs = self.failed_deliveries[aid].copy()
            self.failed_deliveries[aid].clear()
            
            for message in failed_msgs:
                # Only retry if message hasn't expired
                if not message.is_expired():
                    success = await self.send_message(message)
                    if success:
                        retry_count += 1
        
        if retry_count > 0:
            self.logger.info(f"🔄 Retried {retry_count} failed deliveries")
        
        return retry_count
    
    async def _notify_websocket_clients(self, message: Message):
        """Notify connected WebSocket clients of new messages."""
        if not self.websocket_clients:
            return
        
        notification = {
            "type": "new_message",
            "message": message.to_dict(),
            "timestamp": datetime.now().isoformat()
        }
        
        # Send to all connected WebSocket clients
        disconnected_clients = set()
        for client in self.websocket_clients:
            try:
                await client.send_text(json.dumps(notification))
            except Exception as e:
                self.logger.warning(f"⚠️  WebSocket client disconnected: {str(e)}")
                disconnected_clients.add(client)
        
        # Remove disconnected clients
        self.websocket_clients -= disconnected_clients
        self.metrics["websocket_connections"] = len(self.websocket_clients)
    
    def add_websocket_client(self, client):
        """Add a WebSocket client for real-time notifications."""
        self.websocket_clients.add(client)
        self.metrics["websocket_connections"] = len(self.websocket_clients)
        self.logger.info(f"🔗 WebSocket client connected (total: {len(self.websocket_clients)})")
    
    def remove_websocket_client(self, client):
        """Remove a WebSocket client."""
        self.websocket_clients.discard(client)
        self.metrics["websocket_connections"] = len(self.websocket_clients)
        self.logger.info(f"🔗 WebSocket client disconnected (remaining: {len(self.websocket_clients)})")
    
    async def broadcast_system_message(self, content: Any, message_type: str = MessageType.BROADCAST.value):
        """Send a system broadcast message to all subscribers."""
        message = Message(
            sender="system",
            recipient="broadcast",
            content=content,
            message_type=message_type,
            priority=3  # High priority for system messages
        )
        
        return await self.send_message(message)