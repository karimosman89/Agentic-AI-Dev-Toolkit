#!/usr/bin/env python3
"""
Professional FastAPI Server for Agentic AI Development Toolkit
==============================================================

Enterprise-grade REST API server with comprehensive features:
- Agent lifecycle management
- Real-time task orchestration  
- Tool execution and monitoring
- WebSocket support for real-time updates
- Interactive API documentation
- Performance monitoring and metrics

Author: Karim Osman
License: MIT
"""

import asyncio
import logging
import uvicorn
from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBearer
import structlog

# Import core components
from ..core.agent_manager import AgentManager
from ..core.config import get_settings
from .routes import agents, tasks, tools, monitoring, websocket
from .middleware import LoggingMiddleware, MetricsMiddleware, SecurityMiddleware


class AgenticAPIServer:
    """
    Professional API server for the Agentic AI Development Toolkit.
    
    Provides comprehensive REST API endpoints for:
    - Agent management and orchestration
    - Task execution and monitoring
    - Tool registry and execution
    - Real-time communication via WebSocket
    - System monitoring and metrics
    """
    
    def __init__(self, settings=None):
        """Initialize the API server with advanced configuration."""
        self.settings = settings or get_settings()
        self.agent_manager: AgentManager = None
        self.logger = self._setup_structured_logging()
        
        # Create FastAPI app with lifecycle management
        self.app = FastAPI(
            title="🤖 Agentic AI Development Toolkit API",
            description=self._get_api_description(),
            version="2.0.0",
            docs_url="/docs",
            redoc_url="/redoc",
            openapi_url="/openapi.json",
            lifespan=self._lifespan_handler
        )
        
        # Configure middleware
        self._setup_middleware()
        
        # Register routes
        self._register_routes()
        
        # Setup exception handlers
        self._setup_exception_handlers()
        
        self.logger.info("🚀 Agentic API Server initialized successfully")
    
    def _setup_structured_logging(self):
        """Setup structured logging with rich formatting."""
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.TimeStamper(fmt="ISO"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.UnicodeDecoder(),
                structlog.processors.JSONRenderer()
            ],
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
        
        return structlog.get_logger(__name__)
    
    @asynccontextmanager
    async def _lifespan_handler(self, app: FastAPI):
        """Application lifecycle handler for startup/shutdown."""
        # Startup
        self.logger.info("🌟 Server starting up...")
        
        # Initialize agent manager
        self.agent_manager = AgentManager(self.settings)
        
        # Start communication bus
        bus_task = asyncio.create_task(self.agent_manager.communication_bus.start())
        
        # Store in app state for route access
        app.state.agent_manager = self.agent_manager
        app.state.settings = self.settings
        app.state.bus_task = bus_task
        
        self.logger.info("✅ Server startup completed")
        
        yield
        
        # Shutdown
        self.logger.info("🛑 Server shutting down...")
        
        # Cleanup agent manager
        if self.agent_manager:
            await self.agent_manager.cleanup()
        
        # Cancel bus task
        if hasattr(app.state, 'bus_task'):
            app.state.bus_task.cancel()
            try:
                await app.state.bus_task
            except asyncio.CancelledError:
                pass
        
        self.logger.info("✅ Server shutdown completed")
    
    def _setup_middleware(self):
        """Configure middleware stack for security, monitoring, and performance."""
        
        # CORS middleware
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"] if self.settings.debug else ["http://localhost:3000"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        # Compression middleware
        self.app.add_middleware(GZipMiddleware, minimum_size=1000)
        
        # Custom middleware
        self.app.add_middleware(SecurityMiddleware)
        self.app.add_middleware(MetricsMiddleware) 
        self.app.add_middleware(LoggingMiddleware)
    
    def _register_routes(self):
        """Register all API route modules."""
        
        # Include route modules with prefixes
        self.app.include_router(
            agents.router,
            prefix="/api/v1/agents",
            tags=["Agents"],
            responses={404: {"description": "Not found"}}
        )
        
        self.app.include_router(
            tasks.router,
            prefix="/api/v1/tasks", 
            tags=["Tasks"],
            responses={404: {"description": "Not found"}}
        )
        
        self.app.include_router(
            tools.router,
            prefix="/api/v1/tools",
            tags=["Tools"],
            responses={404: {"description": "Not found"}}
        )
        
        self.app.include_router(
            monitoring.router,
            prefix="/api/v1/monitoring",
            tags=["Monitoring"],
            responses={404: {"description": "Not found"}}
        )
        
        self.app.include_router(
            websocket.router,
            prefix="/api/v1/ws",
            tags=["WebSocket"],
        )
        
        # Root endpoints
        self._register_root_endpoints()
    
    def _register_root_endpoints(self):
        """Register root-level endpoints for health checks and info."""
        
        @self.app.get("/", response_class=HTMLResponse)
        async def root():
            """Welcome page with API information."""
            return """
            <!DOCTYPE html>
            <html>
            <head>
                <title>🤖 Agentic AI Development Toolkit</title>
                <style>
                    body { font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }
                    .container { background: white; padding: 30px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
                    .header { text-align: center; color: #333; }
                    .links { display: flex; justify-content: center; gap: 20px; margin: 30px 0; }
                    .link { padding: 10px 20px; background: #007acc; color: white; text-decoration: none; border-radius: 5px; }
                    .link:hover { background: #005999; }
                    .stats { background: #f8f9fa; padding: 20px; border-radius: 5px; margin: 20px 0; }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>🤖 Agentic AI Development Toolkit</h1>
                        <p>Professional Enterprise-Grade Agent Orchestration Platform</p>
                        <p><strong>Version 2.0.0</strong> | <em>Production Ready</em></p>
                    </div>
                    
                    <div class="links">
                        <a href="/docs" class="link">📚 API Documentation</a>
                        <a href="/redoc" class="link">📖 ReDoc</a>
                        <a href="/api/v1/monitoring/health" class="link">🏥 Health Check</a>
                        <a href="/api/v1/monitoring/metrics" class="link">📊 Metrics</a>
                    </div>
                    
                    <div class="stats">
                        <h3>🚀 Features</h3>
                        <ul>
                            <li>🤖 <strong>Advanced Agent Management</strong> - Create, orchestrate, and monitor AI agents</li>
                            <li>⚡ <strong>Real-time Task Execution</strong> - Intelligent task distribution and processing</li>
                            <li>🔧 <strong>Extensible Tool Registry</strong> - Custom tools and capabilities</li>
                            <li>📡 <strong>WebSocket Communication</strong> - Real-time updates and monitoring</li>
                            <li>📊 <strong>Comprehensive Metrics</strong> - Performance monitoring and analytics</li>
                            <li>🛡️ <strong>Enterprise Security</strong> - Production-ready security features</li>
                        </ul>
                    </div>
                    
                    <div style="text-align: center; margin-top: 30px; color: #666;">
                        <p>Built with ❤️ by Karim Osman | <a href="https://github.com/karimosman89">GitHub</a></p>
                    </div>
                </div>
            </body>
            </html>
            """
        
        @self.app.get("/health")
        async def health_check():
            """Basic health check endpoint."""
            return {
                "status": "healthy",
                "timestamp": "2024-08-23T10:00:00Z",
                "version": "2.0.0",
                "service": "agentic-ai-toolkit"
            }
        
        @self.app.get("/api/info")
        async def api_info():
            """Get API information and capabilities."""
            return {
                "name": "Agentic AI Development Toolkit API",
                "version": "2.0.0",
                "description": "Enterprise-grade agent orchestration platform",
                "features": [
                    "Agent lifecycle management",
                    "Task orchestration and monitoring",
                    "Tool registry and execution",
                    "Real-time WebSocket communication",
                    "Performance monitoring and metrics",
                    "Interactive API documentation"
                ],
                "endpoints": {
                    "agents": "/api/v1/agents",
                    "tasks": "/api/v1/tasks",
                    "tools": "/api/v1/tools",
                    "monitoring": "/api/v1/monitoring",
                    "websocket": "/api/v1/ws"
                },
                "documentation": {
                    "swagger": "/docs",
                    "redoc": "/redoc",
                    "openapi": "/openapi.json"
                }
            }
    
    def _setup_exception_handlers(self):
        """Setup global exception handlers for better error responses."""
        
        @self.app.exception_handler(ValueError)
        async def value_error_handler(request: Request, exc: ValueError):
            """Handle validation errors."""
            self.logger.warning("Validation error", error=str(exc), path=request.url.path)
            return JSONResponse(
                status_code=400,
                content={
                    "error": "Validation Error",
                    "message": str(exc),
                    "type": "validation_error",
                    "timestamp": "2024-08-23T10:00:00Z"
                }
            )
        
        @self.app.exception_handler(HTTPException)
        async def http_exception_handler(request: Request, exc: HTTPException):
            """Handle HTTP exceptions with structured responses."""
            self.logger.warning("HTTP error", status_code=exc.status_code, detail=exc.detail, path=request.url.path)
            return JSONResponse(
                status_code=exc.status_code,
                content={
                    "error": f"HTTP {exc.status_code}",
                    "message": exc.detail,
                    "type": "http_error",
                    "timestamp": "2024-08-23T10:00:00Z"
                }
            )
        
        @self.app.exception_handler(Exception)
        async def general_exception_handler(request: Request, exc: Exception):
            """Handle unexpected errors gracefully."""
            self.logger.error("Unexpected error", error=str(exc), path=request.url.path, exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Internal Server Error",
                    "message": "An unexpected error occurred",
                    "type": "internal_error",
                    "timestamp": "2024-08-23T10:00:00Z"
                }
            )
    
    def _get_api_description(self) -> str:
        """Get comprehensive API description for documentation."""
        return """
        ## 🤖 Agentic AI Development Toolkit API
        
        **Professional enterprise-grade platform for developing and managing agentic AI systems.**
        
        ### 🚀 Key Features
        
        - **🤖 Agent Management**: Create, configure, and orchestrate intelligent AI agents
        - **⚡ Task Orchestration**: Intelligent task distribution and execution monitoring  
        - **🔧 Tool Registry**: Extensible tool system with custom capabilities
        - **📡 Real-time Communication**: WebSocket support for live updates and monitoring
        - **📊 Comprehensive Monitoring**: Detailed metrics, performance analytics, and health checks
        - **🛡️ Enterprise Security**: Production-ready security and authentication features
        
        ### 📚 API Sections
        
        - **Agents**: Manage agent lifecycle, configuration, and status
        - **Tasks**: Execute, monitor, and manage agent tasks
        - **Tools**: Register, configure, and execute agent tools  
        - **Monitoring**: System health, metrics, and performance monitoring
        - **WebSocket**: Real-time communication and event streaming
        
        ### 🎯 Perfect For
        
        - Enterprise AI automation platforms
        - Multi-agent system development
        - Intelligent task orchestration
        - AI-powered workflow automation
        - Research and development in agentic AI
        
        ---
        
        **Built with cutting-edge technologies for maximum performance and reliability.**
        """
    
    async def start_server(self):
        """Start the API server with production configuration."""
        config = uvicorn.Config(
            app=self.app,
            host=self.settings.api_host,
            port=self.settings.api_port,
            reload=self.settings.api_reload and self.settings.debug,
            workers=1,  # Single worker for async operations
            log_level=self.settings.log_level.lower(),
            access_log=True,
            use_colors=True
        )
        
        server = uvicorn.Server(config)
        self.logger.info(
            "🌐 Starting API server",
            host=self.settings.api_host,
            port=self.settings.api_port,
            reload=config.reload
        )
        
        await server.serve()


# Global app instance for uvicorn
def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    server = AgenticAPIServer()
    return server.app


# Create app instance
app = create_app()


if __name__ == "__main__":
    import asyncio
    
    async def main():
        """Main entry point for running the server.""" 
        server = AgenticAPIServer()
        await server.start_server()
    
    asyncio.run(main())