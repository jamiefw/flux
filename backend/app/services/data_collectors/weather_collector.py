# backend/app/services/data_collectors/weather_collector.py
import os
import sys
import requests
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

# Ensure sys.path is correct for this file
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..')))

from backend.app.db.session import SessionLocal
from backend.app.models.weather_data import WeatherData
from backend.app.core.config import OPENWEATHER_API_KEY, OPENWEATHER_API_URL, SF_COORDS, NYC_COORDS

from dotenv import load_dotenv # Needed here for manual execution
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '../../../.env.local'))

def fetch_and_store_weather_data():
    """
    Fetches current weather data for SF and NYC from OpenWeatherMap and stores it.
    """
    if not OPENWEATHER_API_KEY:
        print("Error: OPENWEATHER_API_KEY not found. Aborting weather data collection.")
        return


    locations = [SF_COORDS, NYC_COORDS]

    db: Session = SessionLocal()
    try:
        new_weather_records = []
        for location in locations:
            params = {
                "lat": location["lat"],
                "lon": location["lon"],
                "appid": OPENWEATHER_API_KEY,
                "units": "metric"
            }

            print(f"[{datetime.now()}] Fetching weather data for {location['name']}...")
            try:
                response = requests.get(OPENWEATHER_API_URL, params=params, timeout=15)
                response.raise_for_status()
                data = response.json()

                # --- Refined Parsing and Validation Logic ---
                # Check for essential fields and skip the record if they are missing
                api_timestamp_unix = data.get('dt')
                if api_timestamp_unix is None:
                    print(f"Warning: Timestamp 'dt' missing from weather data for {location['name']}. Skipping record.")
                    continue # Skip to the next location in the loop

                # All essential data is present, so we can create the record object
                # Convert Unix timestamp to datetime object
                api_timestamp = datetime.fromtimestamp(api_timestamp_unix, tz=timezone.utc)

                weather_main = data.get('weather', [{}])[0]
                main_data = data.get('main', {})
                wind_data = data.get('wind', {})

                new_record = WeatherData(
                    location_name=location['name'],
                    latitude=location['lat'],
                    longitude=location['lon'],
                    temperature_celsius=main_data.get('temp'),
                    humidity_percent=main_data.get('humidity'),
                    wind_speed_mps=wind_data.get('speed'),
                    weather_condition=weather_main.get('main'),
                    weather_description=weather_main.get('description'),
                    # Safely get precipitation data
                    precipitation_1h_mm=data.get('rain', {}).get('1h'),
                    api_timestamp=api_timestamp # This is guaranteed to be a datetime object here
                )
                new_weather_records.append(new_record)
                print(f"Successfully processed weather data for {location['name']}.")

            except requests.exceptions.RequestException as e:
                print(f"Network error for {location['name']}: {e}")
            except Exception as e:
                print(f"An unexpected error occurred for {location['name']}: {e}")

        # This block is outside the 'for' loop and will execute once all API calls are made
        if new_weather_records:
            db.add_all(new_weather_records)
            db.commit()
            print(f"Successfully stored {len(new_weather_records)} new weather records.")
        else:
            print("No valid weather records to store.")

    except SQLAlchemyError as e:
        db.rollback()
        print(f"Database error during weather data insertion: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    fetch_and_store_weather_data()