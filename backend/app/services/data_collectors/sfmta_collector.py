# backend/app/services/data_collectors/sfmta_collector.py
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..')))

import requests
import datetime
from google.transit import gtfs_realtime_pb2
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
import pytz # For timezone-aware datetimes

# Import your database session and model
from backend.app.db.session import SessionLocal
from backend.app.models.vehicle_position import VehiclePosition
from backend.app.core.config import SFBAY_API_TOKEN, SFMTA_AGENCY_ID # Reuse your config

# It's generally good practice to load_dotenv at the application entry point,
# but for a standalone script, it's fine here too.
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '../../../.env.local'))

# Ensure timezone is defined for timestamp conversion
PACIFIC_TIMEZONE = pytz.timezone('America/Los_Angeles') # SF is in this timezone

def fetch_and_store_sfmta_vehicle_positions():
    """
    Fetches real-time SFMTA vehicle positions from 511 SF Bay API
    and stores them in the PostgreSQL database.
    """
    # Construct the API URL using constants from config
    SFBAY_GTFS_REALTIME_VEHICLE_POSITIONS_URL = (
        f"http://api.511.org/transit/VehiclePositions?api_key={SFBAY_API_TOKEN}&agency={SFMTA_AGENCY_ID}"
    )

    if not SFBAY_API_TOKEN:
        print("Error: SFBAY_API_TOKEN not found. Aborting data collection.")
        return

    print(f"[{datetime.datetime.now()}] Attempting to fetch SFMTA vehicle data...")
    try:
        response = requests.get(SFBAY_GTFS_REALTIME_VEHICLE_POSITIONS_URL, timeout=30)
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)

        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(response.content)

        print(f"Successfully fetched {len(feed.entity)} entities from SFMTA API.")

        db: Session = SessionLocal() # Get a new database session
        try:
            new_positions = []
            for entity in feed.entity:
                if entity.HasField('vehicle'):
                    vehicle = entity.vehicle

                    # Convert Unix timestamp to datetime object
                    # Assuming timestamp is in seconds
                    timestamp_dt = datetime.datetime.fromtimestamp(vehicle.timestamp, tz=datetime.timezone.utc)
                    # Convert to local timezone if desired for display/consistency, otherwise UTC is fine for storage
                    # timestamp_dt = timestamp_dt.astimezone(PACIFIC_TIMEZONE)

                    # Extract values, handling optional fields
                    vehicle_id = vehicle.vehicle.id if vehicle.HasField('vehicle') and vehicle.vehicle.HasField('id') else None
                    trip_id = vehicle.trip.trip_id if vehicle.HasField('trip') and vehicle.trip.HasField('trip_id') else None
                    route_id = vehicle.trip.route_id if vehicle.HasField('trip') and vehicle.trip.HasField('route_id') else None
                    start_date_str = vehicle.trip.start_date if vehicle.HasField('trip') and vehicle.trip.HasField('start_date') else None
                    start_date_dt = datetime.datetime.strptime(start_date_str, '%Y%m%d').date() if start_date_str else None

                    latitude = vehicle.position.latitude if vehicle.HasField('position') and vehicle.position.HasField('latitude') else None
                    longitude = vehicle.position.longitude if vehicle.HasField('position') and vehicle.position.HasField('longitude') else None
                    bearing = vehicle.position.bearing if vehicle.HasField('position') and vehicle.position.HasField('bearing') else None
                    speed_mps = vehicle.position.speed if vehicle.HasField('position') and vehicle.position.HasField('speed') else None

                    current_stop_sequence = vehicle.current_stop_sequence if vehicle.HasField('current_stop_sequence') else None
                    current_status = gtfs_realtime_pb2.VehiclePosition.VehicleStopStatus.Name(vehicle.current_status) if vehicle.HasField('current_status') else None


                    # Create a new VehiclePosition object
                    # Only create if we have essential data
                    if vehicle_id and latitude is not None and longitude is not None:
                        new_position = VehiclePosition(
                            vehicle_id=vehicle_id,
                            trip_id=trip_id,
                            route_id=route_id,
                            start_date=start_date_dt,
                            latitude=latitude,
                            longitude=longitude,
                            bearing=bearing,
                            speed_mps=speed_mps,
                            current_stop_sequence=current_stop_sequence,
                            current_status=current_status,
                            api_timestamp=timestamp_dt
                        )
                        new_positions.append(new_position)
                    else:
                        print(f"Skipping vehicle entity due to missing essential data: ID={vehicle_id}, Lat={latitude}, Lon={longitude}")

            if new_positions:
                db.add_all(new_positions) # Add all new records to the session
                db.commit() # Commit the transaction to the database
                print(f"Successfully stored {len(new_positions)} new SFMTA vehicle positions.")
            else:
                print("No new valid SFMTA vehicle positions to store.")

        except SQLAlchemyError as e:
            db.rollback() # Rollback changes if any error occurs during DB operations
            print(f"Database error during SFMTA data storage: {e}")
        finally:
            db.close() # Always close the session

    except requests.exceptions.RequestException as e:
        print(f"Network error during SFMTA data collection: {e}")
    except Exception as e:
        print(f"An unexpected error occurred during SFMTA data collection: {e}")
        print("Response content (first 500 chars):", response.content[:500].decode('utf-8', errors='ignore') if 'response' in locals() else "N/A")

if __name__ == "__main__":
    fetch_and_store_sfmta_vehicle_positions()