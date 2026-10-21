"""
Entry point for the sandbox engine server.
Mirrors PolicyKit's manage.py role — starts the application.

PolicyKit equivalent: manage.py (Django management)
Sandbox equivalent: FastAPI + uvicorn
"""
import uvicorn


if __name__ == "__main__":
    uvicorn.run(
        "sandboxengine.urls:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
    )
