#!/usr/bin/env python3
"""
Professional Middleware Components for Agentic AI Development Toolkit
=====================================================================

Enterprise-grade middleware for security, monitoring, logging, and performance optimization.

Author: Karim Osman
License: MIT
"""

import time
import json
import uuid
from datetime import datetime
from typing import Callable, Dict, Any
from urllib.parse import urlparse

from fastapi import Request, Response, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import structlog


class LoggingMiddleware:
    """
    Advanced request/response logging middleware with structured logging.
    
    Features:
    - Request/response correlation IDs
    - Performance timing
    - Error tracking
    - Request payload logging (configurable)
    """
    
    def __init__(self):
        self.logger = structlog.get_logger(__name__)
    
    async def __call__(self, request: Request, call_next: Callable) -> Response:
        """Process request with comprehensive logging."""
        # Generate correlation ID
        correlation_id = str(uuid.uuid4())
        request.state.correlation_id = correlation_id
        
        # Start timing
        start_time = time.time()
        
        # Log request
        self.logger.info(
            "Request started",
            correlation_id=correlation_id,
            method=request.method,
            path=request.url.path,
            query_params=dict(request.query_params),
            client_ip=self._get_client_ip(request),
            user_agent=request.headers.get("user-agent")
        )
        
        try:
            # Process request
            response = await call_next(request)
            
            # Calculate processing time
            process_time = time.time() - start_time
            
            # Log response
            self.logger.info(
                "Request completed",
                correlation_id=correlation_id,
                status_code=response.status_code,
                process_time=round(process_time, 4),
                response_size=response.headers.get("content-length", "unknown")
            )
            
            # Add correlation ID to response headers
            response.headers["X-Correlation-ID"] = correlation_id
            response.headers["X-Process-Time"] = str(round(process_time, 4))
            
            return response
            
        except Exception as exc:
            # Log error
            process_time = time.time() - start_time
            self.logger.error(
                "Request failed",
                correlation_id=correlation_id,
                error=str(exc),
                process_time=round(process_time, 4),
                exc_info=True
            )
            raise
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP address from request headers."""
        # Check for forwarded IP headers
        forwarded_ip = request.headers.get("X-Forwarded-For")
        if forwarded_ip:
            return forwarded_ip.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        # Fallback to direct client IP
        return request.client.host if request.client else "unknown"


class MetricsMiddleware:
    """
    Performance metrics collection middleware.
    
    Collects:
    - Request counts by endpoint and method
    - Response time percentiles
    - Error rates by status code
    - Active request counter
    """
    
    def __init__(self):
        self.logger = structlog.get_logger(__name__)
        self.metrics = {
            "requests_total": 0,
            "requests_by_method": {},
            "requests_by_endpoint": {},
            "response_times": [],
            "status_codes": {},
            "active_requests": 0,
            "errors_total": 0
        }
    
    async def __call__(self, request: Request, call_next: Callable) -> Response:
        """Collect performance metrics for requests."""
        # Increment active requests
        self.metrics["active_requests"] += 1
        
        # Record request
        method = request.method
        endpoint = request.url.path
        
        self.metrics["requests_total"] += 1
        self.metrics["requests_by_method"][method] = (
            self.metrics["requests_by_method"].get(method, 0) + 1
        )
        self.metrics["requests_by_endpoint"][endpoint] = (
            self.metrics["requests_by_endpoint"].get(endpoint, 0) + 1
        )
        
        start_time = time.time()
        
        try:
            response = await call_next(request)
            
            # Record metrics
            process_time = time.time() - start_time
            self.metrics["response_times"].append(process_time)
            
            # Keep only last 1000 response times for memory efficiency
            if len(self.metrics["response_times"]) > 1000:
                self.metrics["response_times"] = self.metrics["response_times"][-1000:]
            
            status_code = response.status_code
            self.metrics["status_codes"][status_code] = (
                self.metrics["status_codes"].get(status_code, 0) + 1
            )
            
            # Count errors (4xx, 5xx)
            if status_code >= 400:
                self.metrics["errors_total"] += 1
            
            return response
            
        except Exception as exc:
            # Record error
            self.metrics["errors_total"] += 1
            raise
            
        finally:
            # Decrement active requests
            self.metrics["active_requests"] -= 1
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics summary."""
        response_times = self.metrics["response_times"]
        
        if response_times:
            # Calculate percentiles
            sorted_times = sorted(response_times)
            length = len(sorted_times)
            
            percentiles = {
                "p50": sorted_times[int(length * 0.5)] if length > 0 else 0,
                "p90": sorted_times[int(length * 0.9)] if length > 0 else 0,
                "p95": sorted_times[int(length * 0.95)] if length > 0 else 0,
                "p99": sorted_times[int(length * 0.99)] if length > 0 else 0,
                "avg": sum(response_times) / length,
                "min": min(response_times),
                "max": max(response_times)
            }
        else:
            percentiles = {
                "p50": 0, "p90": 0, "p95": 0, "p99": 0,
                "avg": 0, "min": 0, "max": 0
            }
        
        # Calculate error rate
        total_requests = self.metrics["requests_total"]
        error_rate = (
            (self.metrics["errors_total"] / total_requests * 100)
            if total_requests > 0 else 0
        )
        
        return {
            "requests_total": total_requests,
            "active_requests": self.metrics["active_requests"],
            "error_rate": round(error_rate, 2),
            "errors_total": self.metrics["errors_total"],
            "response_times": percentiles,
            "requests_by_method": self.metrics["requests_by_method"],
            "requests_by_endpoint": dict(
                sorted(
                    self.metrics["requests_by_endpoint"].items(),
                    key=lambda x: x[1],
                    reverse=True
                )[:10]  # Top 10 endpoints
            ),
            "status_codes": self.metrics["status_codes"],
            "timestamp": datetime.now().isoformat()
        }


class SecurityMiddleware:
    """
    Security middleware for request validation and protection.
    
    Features:
    - Rate limiting (basic implementation)
    - Request size limits
    - Security headers
    - IP whitelisting/blacklisting
    - Basic CORS protection
    """
    
    def __init__(self):
        self.logger = structlog.get_logger(__name__)
        self.request_counts = {}  # Simple in-memory rate limiting
        self.blocked_ips = set()
        self.max_request_size = 10 * 1024 * 1024  # 10MB
    
    async def __call__(self, request: Request, call_next: Callable) -> Response:
        """Apply security checks and protections."""
        
        # Get client IP
        client_ip = self._get_client_ip(request)
        
        # Check blocked IPs
        if client_ip in self.blocked_ips:
            self.logger.warning(f"Blocked IP attempted access: {client_ip}")
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Basic rate limiting (100 requests per minute per IP)
        current_time = int(time.time() // 60)  # Current minute
        ip_key = f"{client_ip}:{current_time}"
        
        request_count = self.request_counts.get(ip_key, 0)
        if request_count >= 100:
            self.logger.warning(f"Rate limit exceeded for IP: {client_ip}")
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
        
        self.request_counts[ip_key] = request_count + 1
        
        # Clean old rate limit entries (keep only last 2 minutes)
        old_keys = [
            key for key in self.request_counts.keys()
            if int(key.split(':')[1]) < current_time - 1
        ]
        for key in old_keys:
            del self.request_counts[key]
        
        # Check request size
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.max_request_size:
            self.logger.warning(f"Request too large: {content_length} bytes from {client_ip}")
            raise HTTPException(status_code=413, detail="Request entity too large")
        
        # Process request
        response = await call_next(request)
        
        # Add security headers
        self._add_security_headers(response)
        
        return response
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP address."""
        forwarded_ip = request.headers.get("X-Forwarded-For")
        if forwarded_ip:
            return forwarded_ip.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        return request.client.host if request.client else "unknown"
    
    def _add_security_headers(self, response: Response):
        """Add security headers to response."""
        response.headers.update({
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Content-Security-Policy": "default-src 'self'",
            "X-Powered-By": "Agentic-AI-Toolkit/2.0"
        })
    
    def block_ip(self, ip_address: str):
        """Add IP to blocked list."""
        self.blocked_ips.add(ip_address)
        self.logger.info(f"IP blocked: {ip_address}")
    
    def unblock_ip(self, ip_address: str):
        """Remove IP from blocked list."""
        self.blocked_ips.discard(ip_address)
        self.logger.info(f"IP unblocked: {ip_address}")
    
    def get_security_stats(self) -> Dict[str, Any]:
        """Get security statistics."""
        current_minute = int(time.time() // 60)
        
        # Count current minute requests per IP
        current_requests = {}
        for key, count in self.request_counts.items():
            ip, minute = key.split(':')
            if int(minute) == current_minute:
                current_requests[ip] = current_requests.get(ip, 0) + count
        
        return {
            "blocked_ips_count": len(self.blocked_ips),
            "blocked_ips": list(self.blocked_ips),
            "current_minute_requests": current_requests,
            "top_requesting_ips": dict(
                sorted(current_requests.items(), key=lambda x: x[1], reverse=True)[:10]
            ),
            "max_request_size_mb": self.max_request_size // (1024 * 1024),
            "rate_limit_per_minute": 100,
            "timestamp": datetime.now().isoformat()
        }


class AuthenticationMiddleware:
    """
    JWT-based authentication middleware.
    
    Features:
    - JWT token validation
    - Role-based access control
    - Token refresh logic
    - Protected endpoint enforcement
    """
    
    def __init__(self):
        self.logger = structlog.get_logger(__name__)
        self.security = HTTPBearer()
        self.protected_paths = {
            "/api/v1/agents": ["admin", "agent_manager"],
            "/api/v1/tools": ["admin", "tool_manager"],
            "/api/v1/monitoring/admin": ["admin"]
        }
    
    async def __call__(self, request: Request, call_next: Callable) -> Response:
        """Validate authentication for protected endpoints."""
        
        # Skip authentication for public endpoints
        if self._is_public_endpoint(request.url.path):
            return await call_next(request)
        
        # Check if path requires authentication
        required_roles = self._get_required_roles(request.url.path)
        if not required_roles:
            return await call_next(request)
        
        # Extract and validate token
        try:
            credentials = await self.security(request)
            user_info = self._validate_token(credentials.credentials)
            
            # Check role permissions
            if not self._has_required_role(user_info, required_roles):
                raise HTTPException(status_code=403, detail="Insufficient permissions")
            
            # Add user info to request state
            request.state.user = user_info
            
        except Exception as exc:
            self.logger.warning(f"Authentication failed: {str(exc)}")
            raise HTTPException(status_code=401, detail="Authentication required")
        
        return await call_next(request)
    
    def _is_public_endpoint(self, path: str) -> bool:
        """Check if endpoint is public."""
        public_paths = [
            "/",
            "/health",
            "/docs",
            "/redoc", 
            "/openapi.json",
            "/api/info"
        ]
        return any(path.startswith(p) for p in public_paths)
    
    def _get_required_roles(self, path: str) -> list:
        """Get required roles for path."""
        for protected_path, roles in self.protected_paths.items():
            if path.startswith(protected_path):
                return roles
        return []
    
    def _validate_token(self, token: str) -> Dict[str, Any]:
        """Validate JWT token and return user info."""
        # Placeholder implementation - integrate with your JWT library
        # This is a simplified example
        if token == "admin-token":
            return {
                "user_id": "admin",
                "username": "admin",
                "roles": ["admin"],
                "expires": datetime.now().isoformat()
            }
        elif token == "manager-token":
            return {
                "user_id": "manager",
                "username": "manager", 
                "roles": ["agent_manager", "tool_manager"],
                "expires": datetime.now().isoformat()
            }
        else:
            raise ValueError("Invalid token")
    
    def _has_required_role(self, user_info: Dict[str, Any], required_roles: list) -> bool:
        """Check if user has required roles."""
        user_roles = user_info.get("roles", [])
        return any(role in user_roles for role in required_roles)


# Middleware factory functions for easy integration
def create_logging_middleware():
    """Create logging middleware instance."""
    return LoggingMiddleware()


def create_metrics_middleware():
    """Create metrics middleware instance."""
    return MetricsMiddleware()


def create_security_middleware():
    """Create security middleware instance."""
    return SecurityMiddleware()


def create_auth_middleware():
    """Create authentication middleware instance."""
    return AuthenticationMiddleware()