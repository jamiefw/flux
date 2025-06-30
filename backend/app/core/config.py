# backend/app/core/config.py
import os
from dotenv import load_dotenv

# Load environment variables from .env.local in the project root
# Adjust the path based on your current working directory relative to .env.local
load_dotenv(dotenv_path=os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '.env.local')))


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
SFBAY_API_TOKEN = os.getenv("SFBAY_API_TOKEN")
SFMTA_AGENCY_ID = "SF" 
MTA_BUS_API_KEY = os.getenv("MTA_BUS_API_KEY") 
MTA_AGENCY_ID = "MTA NYCT"
# --- New Bay Wheels GBFS URLs ---
BAY_WHEELS_STATION_INFO_URL = "https://gbfs.lyft.com/gbfs/2.3/bay/en/station_information.json" 
BAY_WHEELS_STATION_STATUS_URL = "https://gbfs.lyft.com/gbfs/2.3/bay/en/station_status.json" 
BAY_WHEELS_GBFS_URL = "https://gbfs.lyft.com/gbfs/2.3/bay/gbfs.json"
CITI_BIKE_GBFS_URL = "https://gbfs.lyft.com/gbfs/2.3/bkn/gbfs.json"
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY") # This should be loaded from .env.local
OPENWEATHER_API_URL = "https://api.openweathermap.org/data/2.5/weather"

# Coordinates for SF and NYC
SF_COORDS = {"lat": 37.7749, "lon": -122.4194, "name": "San Francisco"}
NYC_COORDS = {"lat": 40.7128, "lon": -74.0060, "name": "New York City"}
