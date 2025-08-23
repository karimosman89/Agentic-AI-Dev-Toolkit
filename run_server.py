#!/usr/bin/env python3
"""Simple script to run the API server for demonstration."""

import uvicorn
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

if __name__ == "__main__":
    uvicorn.run(
        "src.api.server:app",
        host="0.0.0.0",
        port=8080,
        reload=False,
        log_level="info"
    )
