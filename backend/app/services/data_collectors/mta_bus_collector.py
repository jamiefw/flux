# backend/app/services/data_collectors/mta_bus_collector.py
import os
import sys
import requests
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

# Ensure sys.path is correct for this file (goes up to 'flux/' root)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..')))

from backend.app.db.session import SessionLocal
from backend.app.models.vehicle_position import VehiclePosition
from backend.app.core.config import MTA_BUS_API_KEY, MTA_AGENCY_ID

from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '../../../.env.local'))

# You might eventually define NYC_TIMEZONE for localization if needed in other parts of the app
# NYC_TIMEZONE = pytz.timezone('America/New_York')

def fetch_and_store_mta_bus_positions():
    """
    Fetches real-time MTA Bus vehicle positions from SIRI VehicleMonitoring API
    and stores them in the PostgreSQL database.
    """
    # Define the MTA Bus SIRI VM URL
    # You MUST replace 'MTA%20NYCT_M15' with the specific LineRef you used to get the data
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
    try:
        response = requests.get(MTA_BUS_SIRI_VM_URL, timeout=30)
        response.raise_for_status()

        data = response.json()

        # --- EXTRACTING DATA FROM SIRI JSON ---
        # Path to the list of vehicle activities based on the provided JSON
        vehicle_activities = data.get('Siri', {}).get('ServiceDelivery', {}).get('VehicleMonitoringDelivery', [])[0].get('VehicleActivity', [])

        print(f"Successfully fetched {len(vehicle_activities)} vehicle activities from MTA Bus SIRI VM.")

        db: Session = SessionLocal()
        try:
            new_positions = []
            for activity in vehicle_activities:
                monitored_vehicle_journey = activity.get('MonitoredVehicleJourney', {})

                # RecordedAtTime from SIRI is an ISO formatted string with timezone offset
                recorded_at_time_str = activity.get('RecordedAtTime')
                timestamp_dt = None
                if recorded_at_time_str:
                    # Ensure timezone parsing. fromisoformat handles +HH:MM and -HH:MM.
                    # For 'Z' (UTC), replace with +00:00 before parsing if fromisoformat doesn't directly support Z
                    if recorded_at_time_str.endswith('Z'):
                        recorded_at_time_str = recorded_at_time_str.replace('Z', '+00:00')
                    try:
                         timestamp_dt = datetime.fromisoformat(recorded_at_time_str)
                    except ValueError as e:
                          print(f"Warning: Could not parse timestamp '{recorded_at_time_str}': {e}")
                          timestamp_dt = None
                    timestamp_dt = datetime.fromisoformat(recorded_at_time_str)

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
                        print(f"Warning: Could not parse start_date '{start_date_str}' for vehicle {vehicle_id}. Storing as None.")
                        pass # Keep as None if parsing fails

                # Position
                vehicle_location = monitored_vehicle_journey.get('VehicleLocation', {})
                latitude = vehicle_location.get('Latitude')
                longitude = vehicle_location.get('Longitude')

                # Other fields
                bearing = monitored_vehicle_journey.get('Bearing')

                # Speed: The JSON you provided does NOT have a 'Velocity' or 'Speed' field directly under MonitoredVehicleJourney
                # It has 'ProgressRate'. So speed_mps will likely be None unless you want to infer it.
                speed_mps = None # Can be None if API doesn't provide numerical speed

                # Current Status: Use ProgressRate or MonitoredCall's ArrivalProximityText
                current_status = monitored_vehicle_journey.get('ProgressRate') # e.g., "normalProgress"
                # Or for more specific stop status:
                # monitored_call = monitored_vehicle_journey.get('MonitoredCall', {})
                # current_status = monitored_call.get('ArrivalProximityText') # e.g., "at stop", "approaching", "< 1 stop away"

                current_stop_sequence = None # SIRI VM often doesn't provide a direct numerical sequence without more complex parsing

                # Basic validation before creating object
                if vehicle_id and latitude is not None and longitude is not None and timestamp_dt:
                    new_position = VehiclePosition(
                        vehicle_id=str(vehicle_id),
                        trip_id=str(trip_id) if trip_id else None,
                        route_id=str(route_id) if route_id else None,
                        start_date=start_date_dt,
                        latitude=float(latitude),
                        longitude=float(longitude),
                        bearing=float(bearing) if bearing is not None else None,
                        speed_mps=speed_mps, # Will be None unless you find a speed field
                        current_stop_sequence=current_stop_sequence,
                        current_status=str(current_status) if current_status else None,
                        api_timestamp=timestamp_dt
                    )
                    new_positions.append(new_position)
                else:
                    print(f"Skipping MTA vehicle entity due to missing essential data: ID={vehicle_id}, Lat={latitude}, Lon={longitude}, Timestamp={timestamp_dt}")

            if new_positions:
                db.add_all(new_positions)
                db.commit()
                print(f"Successfully stored {len(new_positions)} new MTA Bus vehicle positions.")
            else:
                print("No new valid MTA Bus vehicle positions to store.")

        except SQLAlchemyError as e:
            db.rollback()
            print(f"Database error during MTA Bus data storage: {e}")
        finally:
            db.close()

    except requests.exceptions.RequestException as e:
        print(f"Network error during MTA Bus data collection: {e}")
    except Exception as e:
        print(f"An unexpected error occurred during MTA Bus data collection: {e}")
        # Ensure response object exists before trying to decode its content
        if 'response' in locals():
            print("Response status:", response.status_code)
            print("Response content (first 500 chars):", response.content[:500].decode('utf-8', errors='ignore'))
        else:
            print("No response object available.")


if __name__ == "__main__":
    fetch_and_store_mta_bus_positions()