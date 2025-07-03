# backend/app/services/data_collectors/sfmta_collector.py
import os
import sys
import requests
import datetime # <--- Use this import style for datetime.datetime.now() etc.
from google.transit import gtfs_realtime_pb2
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
import pytz # For timezone-aware datetimes
import tenacity # <--- NEW IMPORT for retry logic
from pydantic import BaseModel, Field, ValidationError # <--- NEW IMPORT for data validation

# Ensure sys.path is correct for imports from backend.app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..')))

from backend.app.db.session import SessionLocal
from backend.app.models.vehicle_position import VehiclePosition
from backend.app.core.config import SFBAY_API_TOKEN, SFMTA_AGENCY_ID

# It's generally good practice to load_dotenv at the application entry point,
# but for a standalone script, it's fine here too.
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '../../../.env.local'))

# Ensure timezone is defined for timestamp conversion
PACIFIC_TIMEZONE = pytz.timezone('America/Los_Angeles') # SF is in this timezone

# --- Pydantic Model for Data Validation ---
# This model defines the expected structure and types of data
# before it's saved to the database.
class VehiclePositionData(BaseModel):
    vehicle_id: str = Field(..., max_length=50) # '...' means mandatory
    trip_id: str | None = Field(None, max_length=100) # 'None' means optional, default is None
    route_id: str | None = Field(None, max_length=50)
    start_date: datetime.date | None = None # Using datetime.date for date-only type
    latitude: float
    longitude: float
    bearing: float | None = None
    speed_mps: float | None = None
    current_stop_sequence: int | None = None
    current_status: str | None = Field(None, max_length=50)
    api_timestamp: datetime.datetime # Using datetime.datetime for full timestamp

# --- Tenacity Retry Strategy ---
# This defines how API calls will be retried if they fail.
retry_strategy = tenacity.retry(
    stop=tenacity.stop_after_attempt(5), # Stop after 5 total attempts (1 original + 4 retries)
    wait=tenacity.wait_fixed(2), # Wait 2 seconds between retries
    # Retry if a network error occurs (including HTTP 4xx/5xx errors raised by raise_for_status)
    retry=tenacity.retry_if_exception_type(requests.exceptions.RequestException),
    reraise=True # Re-raise the last exception if all retries fail
)

@retry_strategy
def fetch_raw_sfmta_data(url: str) -> bytes:
    """
    Fetches raw Protobuf data from the SFMTA API with retry logic.
    Raises requests.exceptions.RequestException on network/HTTP errors.
    """
    print(f"[{datetime.datetime.now()}] Fetching raw data from: {url}")
    response = requests.get(url, timeout=30)
    response.raise_for_status() # This will raise an HTTPError for 4xx/5xx responses
    print(f"[{datetime.datetime.now()}] Successfully received raw data.")
    return response.content

def fetch_and_store_sfmta_vehicle_positions():
    """
    Fetches real-time SFMTA vehicle positions from 511 SF Bay API
    and stores them in the PostgreSQL database.
    Includes data validation and robust error handling.
    """
    # Construct the API URL using constants from config
    SFBAY_GTFS_REALTIME_VEHICLE_POSITIONS_URL = (
        f"http://api.511.org/transit/VehiclePositions?api_key={SFBAY_API_TOKEN}&agency={SFMTA_AGENCY_ID}"
    )

    if not SFBAY_API_TOKEN:
        print("Error: SFBAY_API_TOKEN not found. Aborting data collection.")
        return

    print(f"[{datetime.datetime.now()}] Attempting to fetch SFMTA vehicle data...")
    
    db: Session = SessionLocal() # Get a new database session
    try:
        # --- API Call with Retry Logic ---
        raw_content = fetch_raw_sfmta_data(SFBAY_GTFS_REALTIME_VEHICLE_POSITIONS_URL)
        
        # Parse the GTFS-Realtime Protobuf content
        feed = gtfs_realtime_pb2.FeedMessage()
        try:
            feed.ParseFromString(raw_content)
        except Exception as e:
            print(f"Error parsing GTFS-Realtime protobuf message: {e}. Raw content (first 500 chars): {raw_content[:500].decode('utf-8', errors='ignore')}")
            # If parsing fails, treat it as a non-recoverable error for this attempt
            raise e # Re-raise to be caught by the outer except block

        print(f"Successfully parsed {len(feed.entity)} entities from SFMTA API.")

        new_positions = []
        for entity in feed.entity:
            if entity.HasField('vehicle'):
                vehicle = entity.vehicle

                # Extract values from Protobuf, handling optional fields gracefully
                vehicle_id = getattr(vehicle.vehicle, 'id', None) if vehicle.HasField('vehicle') else None
                trip_id = getattr(vehicle.trip, 'trip_id', None) if vehicle.HasField('trip') else None
                route_id = getattr(vehicle.trip, 'route_id', None) if vehicle.HasField('trip') else None
                
                start_date_str = getattr(vehicle.trip, 'start_date', None) if vehicle.HasField('trip') else None
                start_date_dt = datetime.datetime.strptime(start_date_str, '%Y%m%d').date() if start_date_str else None

                latitude = getattr(vehicle.position, 'latitude', None) if vehicle.HasField('position') else None
                longitude = getattr(vehicle.position, 'longitude', None) if vehicle.HasField('position') else None
                bearing = getattr(vehicle.position, 'bearing', None) if vehicle.HasField('position') else None
                speed_mps = getattr(vehicle.position, 'speed', None) if vehicle.HasField('position') else None

                current_stop_sequence = getattr(vehicle, 'current_stop_sequence', None)
                current_status = gtfs_realtime_pb2.VehiclePosition.VehicleStopStatus.Name(vehicle.current_status) if vehicle.HasField('current_status') else None
                
                api_timestamp_unix = getattr(vehicle, 'timestamp', None)
                api_timestamp = datetime.datetime.fromtimestamp(api_timestamp_unix, tz=datetime.timezone.utc) if api_timestamp_unix else None
                
                # --- Prepare data for Pydantic validation ---
                data_dict = {
                    "vehicle_id": vehicle_id,
                    "trip_id": trip_id,
                    "route_id": route_id,
                    "start_date": start_date_dt,
                    "latitude": latitude,
                    "longitude": longitude,
                    "bearing": bearing,
                    "speed_mps": speed_mps,
                    "current_stop_sequence": current_stop_sequence,
                    "current_status": current_status,
                    "api_timestamp": api_timestamp
                }

                # --- Validate and Store Data ---
                try:
                    # Pydantic validation: raises ValidationError if data is not valid
                    validated_data = VehiclePositionData(**data_dict)
                    
                    # Create SQLAlchemy model instance from validated data
                    new_position = VehiclePosition(**validated_data.model_dump())
                    new_positions.append(new_position)
                    
                except ValidationError as e:
                    print(f"[{datetime.datetime.now()}] Data validation failed for vehicle_id '{vehicle_id}': {e}. Skipping record.")
                except Exception as e:
                    print(f"[{datetime.datetime.now()}] Unexpected error during data processing for vehicle_id '{vehicle_id}': {e}. Skipping record.")
                    continue # Skip to next entity if processing fails

            else: # If entity does not have a 'vehicle' field (e.g., TripUpdate, ServiceAlert)
                # print(f"[{datetime.datetime.now()}] Entity {entity.id} is not a vehicle position, skipping.")
                pass # Silently skip non-vehicle entities

        if new_positions:
            db.add_all(new_positions) # Add all valid records to the session
            db.commit() # Commit the transaction to the database
            print(f"[{datetime.datetime.now()}] Successfully stored {len(new_positions)} new SFMTA vehicle positions.")
        else:
            print(f"[{datetime.datetime.now()}] No new valid SFMTA vehicle positions to store.")

    except tenacity.RetryError as e:
        # This catches the error if all retries failed for the API call
        print(f"[{datetime.datetime.now()}] Fatal API error after all retries for SFMTA: {e}")
        db.rollback() # Ensure rollback if any DB operations started before the final API failure
    except requests.exceptions.RequestException as e:
        # Catches network errors that bypass tenacity or non-retriable HTTP errors
        print(f"[{datetime.datetime.now()}] Network error during SFMTA data collection: {e}")
        db.rollback()
    except SQLAlchemyError as e:
        # Catches database-specific errors during add_all or commit
        print(f"[{datetime.datetime.now()}] Database error during SFMTA data storage: {e}")
        db.rollback() # Rollback changes if any error occurs during DB operations
    except Exception as e:
        # Catch any other unexpected errors during the entire process
        print(f"[{datetime.datetime.now()}] An unexpected error occurred during SFMTA data collection: {e}")
        db.rollback()
    finally:
        db.close() # Always close the session

if __name__ == "__main__":
    fetch_and_store_sfmta_vehicle_positions()