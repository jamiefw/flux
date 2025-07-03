# backend/app/services/data_collectors/citi_bike_collector.py
import os
import sys
import requests
from datetime import datetime, date, timezone # Explicitly import date, timezone
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
import tenacity # NEW IMPORT for retry logic
from pydantic import BaseModel, Field, ValidationError # NEW IMPORT for data validation

# Ensure sys.path is correct for imports from backend.app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..')))

from backend.app.db.session import SessionLocal
from backend.app.models.bike_station import BikeStation, BikeStationStatus
from backend.app.core.config import CITI_BIKE_GBFS_URL # Use the new Citi Bike URL

from dotenv import load_dotenv # Needed here for manual execution
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '../../../.env.local'))

GBFS_FEEDS = {}

# --- Pydantic Models for Data Validation ---
# These models mirror the BikeStation and BikeStationStatus SQLAlchemy models
# based on the GBFS station_information.json and station_status.json feeds.
class CitiBikeStationData(BaseModel):
    station_id: str = Field(..., max_length=50)
    name: str = Field(..., max_length=255)
    latitude: float
    longitude: float
    capacity: int | None = None
    rental_methods: str | None = Field(None, max_length=255)
    external_id: str | None = Field(None, max_length=255)
    address: str | None = Field(None, max_length=255)
    region_id: str | None = Field(None, max_length=50)
    is_charging_station: bool | None = None
    parking_type: str | None = Field(None, max_length=50)
    last_updated: datetime | None = None

class CitiBikeStationStatusData(BaseModel):
    station_id: str = Field(..., max_length=50)
    num_bikes_available: int
    num_docks_available: int
    num_ebikes_available: int | None = None
    num_scooters_available: int | None = None
    is_renting: bool
    is_returning: bool
    is_installed: bool
    last_reported: datetime

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
def fetch_gbfs_json_data(url: str) -> dict:
    """
    Fetches JSON data from a GBFS URL with retry logic.
    Raises requests.exceptions.RequestException on network/HTTP errors.
    """
    print(f"[{datetime.now()}] Fetching raw JSON data from: {url}")
    response = requests.get(url, timeout=30)
    response.raise_for_status() # This will raise an HTTPError for 4xx/5xx responses
    print(f"[{datetime.now()}] Successfully received raw JSON data.")
    return response.json()

def fetch_gbfs_feed_urls():
    """
    Fetches the GBFS discovery feed for Citi Bike to get URLs for all other feeds.
    Caches the results in the GBFS_FEEDS dictionary.
    """
    global GBFS_FEEDS
    if GBFS_FEEDS:
        return GBFS_FEEDS

    print(f"[{datetime.now()}] Discovering GBFS feed URLs for Citi Bike from: {CITI_BIKE_GBFS_URL}...")
    try:
        feed_data = fetch_gbfs_json_data(CITI_BIKE_GBFS_URL) # Use the new robust fetcher

        feeds = feed_data.get('data', {}).get('en', {}).get('feeds', [])
        
        for feed in feeds:
            GBFS_FEEDS[feed['name']] = feed['url']
        
        print(f"[{datetime.now()}] Successfully discovered Citi Bike GBFS feeds: {list(GBFS_FEEDS.keys())}")
        return GBFS_FEEDS
    
    except tenacity.RetryError as e:
        print(f"[{datetime.now()}] Fatal API error after all retries for Citi Bike GBFS discovery: {e}")
        return {}
    except requests.exceptions.RequestException as e:
        print(f"[{datetime.now()}] Network error fetching Citi Bike GBFS discovery feed: {e}")
        return {}
    except Exception as e:
        print(f"[{datetime.now()}] An unexpected error occurred during Citi Bike GBFS discovery: {e}")
        return {}


def fetch_and_store_static_station_info():
    """
    Fetches static station information for Citi Bike and performs an upsert.
    This should be run infrequently (e.g., once per day).
    """
    feeds = fetch_gbfs_feed_urls()
    station_info_url = feeds.get('station_information')
    
    if not station_info_url:
        print(f"[{datetime.now()}] Citi Bike station information URL not found. Aborting static data collection.")
        return

    print(f"[{datetime.now()}] Fetching static Citi Bike station info from: {station_info_url}...")
    db: Session = SessionLocal()
    try:
        data = fetch_gbfs_json_data(station_info_url) # Use the new robust fetcher
        
        stations_data = data.get('data', {}).get('stations', [])
        print(f"[{datetime.now()}] Successfully fetched {len(stations_data)} Citi Bike static station records.")

        for station_info in stations_data:
            # Prepare data for Pydantic validation
            station_data_dict = {
                'station_id': station_info.get('station_id'),
                'name': station_info.get('name'),
                'latitude': station_info.get('lat'),
                'longitude': station_info.get('lon'),
                'capacity': station_info.get('capacity'),
                'rental_methods': ','.join(station_info.get('rental_methods', [])),
                'external_id': station_info.get('external_id'),
                'address': station_info.get('address'),
                'region_id': station_info.get('region_id'),
                'is_charging_station': station_info.get('is_charging_station'),
                'parking_type': station_info.get('parking_type'),
                'last_updated': datetime.fromtimestamp(data.get('last_updated', 0), tz=timezone.utc) # Use feed's last_updated timestamp
            }

            try:
                validated_data = CitiBikeStationData(**station_data_dict) # Use CitiBikeStationData
                
                # Check if station already exists for upsert
                existing_station = db.query(BikeStation).filter(BikeStation.station_id == validated_data.station_id).first()
                
                if existing_station:
                    # Update existing record using validated data
                    for key, value in validated_data.model_dump(exclude_unset=True).items():
                        setattr(existing_station, key, value)
                    print(f"[{datetime.now()}] Updated static info for Citi Bike station: {validated_data.station_id}")
                else:
                    # Insert new record
                    new_station = BikeStation(**validated_data.model_dump())
                    db.add(new_station)
                    print(f"[{datetime.now()}] Inserted new static info for Citi Bike station: {validated_data.station_id}")
            
            except ValidationError as e:
                print(f"[{datetime.now()}] Data validation failed for static Citi Bike station record '{station_info.get('station_id')}': {e}. Skipping record.")
            except Exception as e:
                print(f"[{datetime.now()}] Unexpected error during static Citi Bike station data processing for '{station_info.get('station_id')}': {e}. Skipping record.")

        db.commit()
        print(f"[{datetime.now()}] Citi Bike static station info upsert complete.")

    except tenacity.RetryError as e:
        print(f"[{datetime.now()}] Fatal API error after all retries for static Citi Bike station info: {e}")
        db.rollback()
    except requests.exceptions.RequestException as e:
        print(f"[{datetime.now()}] Network error fetching static Citi Bike station info: {e}")
        db.rollback()
    except SQLAlchemyError as e:
        print(f"[{datetime.now()}] Database error during static Citi Bike station info upsert: {e}")
        db.rollback()
    except Exception as e:
        print(f"[{datetime.now()}] An unexpected error occurred during static Citi Bike station info collection: {e}")
        db.rollback()
    finally:
        db.close()


def fetch_and_store_realtime_station_status():
    """
    Fetches real-time station status for Citi Bike and inserts new records.
    This should be run frequently (e.g., every 60 seconds).
    """
    feeds = fetch_gbfs_feed_urls()
    station_status_url = feeds.get('station_status')
    
    if not station_status_url:
        print(f"[{datetime.now()}] Citi Bike station status URL not found. Aborting real-time data collection.")
        return

    print(f"[{datetime.now()}] Fetching real-time Citi Bike station status from: {station_status_url}...")
    db: Session = SessionLocal()
    try:
        data = fetch_gbfs_json_data(station_status_url) # Use the new robust fetcher
        
        statuses_data = data.get('data', {}).get('stations', [])
        last_reported_timestamp = data.get('last_updated', None)
        
        if last_reported_timestamp:
            last_reported_dt = datetime.fromtimestamp(last_reported_timestamp, tz=timezone.utc)
        else:
            print(f"[{datetime.now()}] Warning: 'last_updated' timestamp missing from Citi Bike status feed. Using current time.")
            last_reported_dt = datetime.now(timezone.utc)

        new_status_records = []
        for status_info in statuses_data:
            # Prepare data for Pydantic validation
            status_data_dict = {
                'station_id': status_info.get('station_id'),
                'num_bikes_available': status_info.get('num_bikes_available'),
                'num_docks_available': status_info.get('num_docks_available'),
                'num_ebikes_available': status_info.get('num_ebikes_available'),
                'num_scooters_available': status_info.get('num_scooters_available'),
                'is_renting': bool(status_info.get('is_renting')),
                'is_returning': bool(status_info.get('is_returning')),
                'is_installed': bool(status_info.get('is_installed')),
                'last_reported': datetime.fromtimestamp(status_info.get('last_reported', last_reported_timestamp), tz=timezone.utc)
            }
            
            try:
                validated_data = CitiBikeStationStatusData(**status_data_dict) # Use CitiBikeStationStatusData
                new_status = BikeStationStatus(**validated_data.model_dump())
                new_status_records.append(new_status)
            except ValidationError as e:
                print(f"[{datetime.now()}] Data validation failed for status record '{status_info.get('station_id')}': {e}. Skipping record.")
            except Exception as e:
                print(f"[{datetime.now()}] Unexpected error during status data processing for '{status_info.get('station_id')}': {e}. Skipping record.")
                continue # Skip to next entity if processing fails
        
        if new_status_records:
            db.add_all(new_status_records)
            db.commit()
            print(f"[{datetime.now()}] Successfully stored {len(new_status_records)} new Citi Bike station status records.")
        else:
            print(f"[{datetime.now()}] No new valid Citi Bike station status records to store.")
            
    except tenacity.RetryError as e:
        print(f"[{datetime.now()}] Fatal API error after all retries for real-time Citi Bike station status: {e}")
        db.rollback()
    except requests.exceptions.RequestException as e:
        print(f"[{datetime.now()}] Network error fetching Citi Bike station status: {e}")
        db.rollback()
    except SQLAlchemyError as e:
        db.rollback()
        print(f"[{datetime.now()}] Database error during Citi Bike station status insertion: {e}")
        db.rollback()
    except Exception as e:
        print(f"[{datetime.now()}] An unexpected error occurred during real-time Citi Bike station status collection: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    # Example usage for manual execution
    # Run this once a day or manually to update static info
    # fetch_and_store_static_station_info()
    
    # Run this every 60 seconds via a scheduler
    fetch_and_store_realtime_station_status()