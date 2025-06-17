# backend/app/core/config.py
import os
from dotenv import load_dotenv

# Load environment variables from .env.local in the project root
# Adjust the path based on your current working directory relative to .env.local
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '../../.env.local'))

# Database connection URL (for PostgreSQL running in Docker)
# This will use the service name 'db' from docker-compose.yml as the host
# when your FastAPI app is containerized later. For local development, 'localhost' works.
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://user:password@localhost:5432/flux_db" # Default for local dev
)

# You can add other configurations here later, e.g., Redis, API settings.
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))