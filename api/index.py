import os
import sys
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

# Configure DB_PATH for serverless environment
os.environ["DB_PATH"] = "/tmp/cache.db"

from app import app
