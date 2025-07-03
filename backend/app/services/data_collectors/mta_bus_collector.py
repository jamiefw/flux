# backend/app/services/data_collectors/mta_bus_collector.py
import os
import sys
import requests
from datetime import datetime, date, timezone, timedelta # Explicitly import date, timezone, timedelta
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
import pytz # For timezone-aware datetimes (still useful for general timezone handling)
import tenacity # NEW IMPORT for retry logic
from pydantic import BaseModel, Field, ValidationError # NEW IMPORT for data validation

# Ensure sys.path is correct for imports from backend.app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..')))

from backend.app.db.session import SessionLocal
from backend.app.models.vehicle_position import VehiclePosition
from backend.app.core.config import MTA_BUS_API_KEY, MTA_AGENCY_ID

from dotenv import load_dotenv # Needed here for manual execution
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '../../../.env.local'))

# NYC Timezone (for converting timestamps if needed, or stick to UTC)
NYC_TIMEZONE = pytz.timezone('America/New_York')

# --- Pydantic Model for Data Validation ---
# This model defines the expected structure and types of data
# extracted from the MTA SIRI JSON before it's saved to the database.
class MtaBusVehiclePositionData(BaseModel):
    vehicle_id: str = Field(..., max_length=50)
    trip_id: str | None = Field(None, max_length=100)
    route_id: str | None = Field(None, max_length=50)
    start_date: date | None = None # Using date for date-only type
    latitude: float
    longitude: float
    bearing: float | None = None
    speed_mps: float | None = None # Will likely be None from MTA SIRI VM
    current_stop_sequence: int | None = None # Will likely be None from MTA SIRI VM
    current_status: str | None = Field(None, max_length=50) # e.g., "normalProgress"
    api_timestamp: datetime # Using datetime for full timestamp

# --- Tenacity Retry Strategy ---
# This defines how API calls will be retried if they fail.
retry_strategy = tenacity.retry(
    stop=tenacity.stop_after_attempt(5), # Stop after 5 total attempts (1 original + 4 retries)
    wait=tenacity.wait_fixed(2), # Wait 2 seconds between retries
    # Retry on network errors (including HTTP 4xx/5xx responses raised by raise_for_status)
    retry=tenacity.retry_if_exception_type(requests.exceptions.RequestException),
    reraise=True # Re-raise the last exception if all retries fail
)

@retry_strategy
def fetch_raw_mta_bus_data(url: str) -> dict:
    """
    Fetches raw JSON data from the MTA Bus SIRI API with retry logic.
    Raises requests.exceptions.RequestException on network/HTTP errors.
    """
    print(f"[{datetime.now()}] Fetching raw data from: {url}")
    response = requests.get(url, timeout=30)
    response.raise_for_status() # This will raise an HTTPError for 4xx/5xx responses
    print(f"[{datetime.now()}] Successfully received raw data.")
    return response.json() # Return JSON directly

def fetch_and_store_mta_bus_positions():
    """
    Fetches real-time MTA Bus vehicle positions from SIRI VehicleMonitoring API
    and stores them in the PostgreSQL database.
    Includes data validation and robust error handling.
    """
    # Define the MTA Bus SIRI VM URL
    # Replace 'MTA%20NYCT_M15' with the specific LineRef you used to get the data
    # Ensure MTA_AGENCY_ID in config.py matches the agency part of your LineRef (e.g., "MTA NYCT")
    MTA_BUS_SIRI_VM_URL = (
        f"https://bustime.mta.info/api/siri/vehicle-monitoring.json?"
        f"key={MTA_BUS_API_KEY}&version=2&OperatorRef={MTA_AGENCY_ID}&LineRef=MTA%20NYCT_M15"
        # Example LineRef, ensure this matches what you used to get data
    )

    if not MTA_BUS_API_KEY:
        print("Error: MTA_BUS_API_KEY not found. Aborting data collection.")
        return

    print(f"[{datetime.now()}] Attempting to fetch MTA Bus vehicle data from SIRI VM for agency: {MTA_AGENCY_ID} and LineRef: MTA NYCT_M15...")
    
    db: Session = SessionLocal()
    try:
        # --- API Call with Retry Logic ---
        data = fetch_raw_mta_bus_data(MTA_BUS_SIRI_VM_URL)

        # --- EXTRACTING DATA FROM SIRI JSON ---
        # Path to the list of vehicle activities based on the provided JSON
        vehicle_activities = data.get('Siri', {}).get('ServiceDelivery', {}).get('VehicleMonitoringDelivery', [])
        # The VehicleMonitoringDelivery is a list, and the actual content is in the first item's VehicleActivity
        if vehicle_activities and isinstance(vehicle_activities, list) and vehicle_activities[0].get('VehicleActivity'):
            vehicle_activities = vehicle_activities[0].get('VehicleActivity', [])
        else:
            print(f"[{datetime.now()}] No 'VehicleActivity' found in MTA Bus response. Check API filters or data structure.")
            vehicle_activities = [] # Ensure it's an empty list if no activities

        print(f"Successfully parsed {len(vehicle_activities)} vehicle activities from MTA Bus SIRI VM.")

        new_positions = []
        for activity in vehicle_activities:
            monitored_vehicle_journey = activity.get('MonitoredVehicleJourney', {})
            
            # RecordedAtTime from SIRI is an ISO formatted string with timezone offset
            recorded_at_time_str = activity.get('RecordedAtTime')
            timestamp_dt = None
            if recorded_at_time_str:
                if recorded_at_time_str.endswith('Z'):
                    recorded_at_time_str = recorded_at_time_str.replace('Z', '+00:00')
                try:
                    timestamp_dt = datetime.fromisoformat(recorded_at_time_str)
                except ValueError as e:
                    print(f"[{datetime.now()}] Warning: Could not parse timestamp '{recorded_at_time_str}': {e}. Skipping record.")
                    continue # Skip this record if timestamp parsing fails
            else:
                print(f"[{datetime.now()}] Warning: Missing 'RecordedAtTime' for a vehicle activity. Skipping record.")
                continue # Skip if timestamp is missing

            # Vehicle identification
            vehicle_id = monitored_vehicle_journey.get('VehicleRef')
            
            # Trip and Route information
            framed_journey_ref = monitored_vehicle_journey.get('FramedVehicleJourneyRef', {})
            trip_id = framed_journey_ref.get('DatedVehicleJourneyRef')
            route_id = monitored_vehicle_journey.get('LineRef')
            
            # Start Date: Extracted from DataFrameRef, usually YYYY-MM-DD
            start_date_str = framed_journey_ref.get('DataFrameRef')
            start_date_dt = None
            if start_date_str:
                try:
                    start_date_dt = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                except ValueError:
                    print(f"[{datetime.now()}] Warning: Could not parse start_date '{start_date_str}' for vehicle {vehicle_id}. Storing as None.")
                    pass # Keep as None if parsing fails

            # Position
            vehicle_location = monitored_vehicle_journey.get('VehicleLocation', {})
            latitude = vehicle_location.get('Latitude')
            longitude = vehicle_location.get('Longitude')
            
            # Other fields
            bearing = monitored_vehicle_journey.get('Bearing')
            speed_mps = None # MTA SIRI VM typically doesn't provide numerical speed directly

            current_status = monitored_vehicle_journey.get('ProgressStatus') # e.g., "normalProgress"
            current_stop_sequence = None # SIRI VM often doesn't provide a direct numerical sequence

            # --- Prepare data for Pydantic validation ---
            data_dict = {
                "vehicle_id": str(vehicle_id) if vehicle_id else None, # Ensure string type
                "trip_id": str(trip_id) if trip_id else None,
                "route_id": str(route_id) if route_id else None,
                "start_date": start_date_dt,
                "latitude": float(latitude) if latitude is not None else None,
                "longitude": float(longitude) if longitude is not None else None,
                "bearing": float(bearing) if bearing is not None else None,
                "speed_mps": speed_mps, # Will be None
                "current_stop_sequence": current_stop_sequence,
                "current_status": str(current_status) if current_status else None,
                "api_timestamp": timestamp_dt
            }

            # --- Validate and Store Data ---
            try:
                # Pydantic validation: raises ValidationError if data is not valid
                validated_data = MtaBusVehiclePositionData(**data_dict)
                
                # Create SQLAlchemy model instance from validated data
                new_position = VehiclePosition(**validated_data.model_dump())
                new_positions.append(new_position)
                
            except ValidationError as e:
                print(f"[{datetime.now()}] Data validation failed for vehicle_id '{vehicle_id}': {e}. Skipping record.")
            except Exception as e:
                print(f"[{datetime.now()}] Unexpected error during data processing for vehicle_id '{vehicle_id}': {e}. Skipping record.")
                continue # Skip to next entity if processing fails

        if new_positions:
            db.add_all(new_positions)
            db.commit()
            print(f"[{datetime.now()}] Successfully stored {len(new_positions)} new MTA Bus vehicle positions.")
        else:
            print(f"[{datetime.now()}] No new valid MTA Bus vehicle positions to store.")

    except tenacity.RetryError as e:
        print(f"[{datetime.now()}] Fatal API error after all retries for MTA Bus: {e}")
        db.rollback()
    except requests.exceptions.RequestException as e:
        print(f"[{datetime.now()}] Network error during MTA Bus data collection: {e}")
        db.rollback()
    except SQLAlchemyError as e:
        print(f"[{datetime.now()}] Database error during MTA Bus data storage: {e}")
        db.rollback()
    except Exception as e:
        print(f"[{datetime.now()}] An unexpected error occurred during MTA Bus data collection: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    fetch_and_store_mta_bus_positions()