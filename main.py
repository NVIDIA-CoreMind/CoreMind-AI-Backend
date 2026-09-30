"""
CoreMind Backend — Entrypoint.

Starts the FastAPI server with uvicorn.
"""

from src.app.bootstrap import main

if __name__ == "__main__":
    main()
