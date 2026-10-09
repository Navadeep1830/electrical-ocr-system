#!/usr/bin/env python3
import sys
import uvicorn
from pathlib import Path

# Add backend directory to python path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.config import HOST, PORT, DEBUG

if __name__ == "__main__":
    print(f"Starting PowerNext Electrical OCR System on http://{HOST}:{PORT}")
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=DEBUG, log_level="info")
