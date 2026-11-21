import os
import sys
from pathlib import Path

# Configure DB_PATH for serverless environment
os.environ["DB_PATH"] = "/tmp/cache.db"

# Ensure api directory and backend directory are on sys.path
api_dir = Path(__file__).resolve().parent
if str(api_dir) not in sys.path:
    sys.path.insert(0, str(api_dir))

backend_dir = api_dir.parent / "backend"
if backend_dir.exists() and str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app import app
