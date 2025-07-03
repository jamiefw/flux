# backend/app/services/data_collectors/weather_collector.py
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
from backend.app.models.weather_data import WeatherData
from backend.app.core.config import OPENWEATHER_API_KEY, OPENWEATHER_API_URL, SF_COORDS, NYC_COORDS

from dotenv import load_dotenv # Needed here for manual execution
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '../../../.env.local'))

# --- Pydantic Model for Data Validation ---
# This model mirrors the WeatherData SQLAlchemy model for validation.
class WeatherDataPydantic(BaseModel):
    location_name: str = Field(..., max_length=50)
    latitude: float
    longitude: float
    
    temperature_celsius: float | None = None
    humidity_percent: int | None = None
    wind_speed_mps: float | None = None
    
    weather_condition: str | None = Field(None, max_length=255)
    weather_description: str | None = Field(None, max_length=255)
    
    precipitation_1h_mm: float | None = None # Ensure it matches your DB schema
    
    api_timestamp: datetime # Mandatory datetime object

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
def fetch_raw_weather_data(url: str, params: dict) -> dict:
    """
    Fetches raw JSON data from OpenWeatherMap API with retry logic.
    """
    print(f"[{datetime.now()}] Fetching raw JSON data from: {url} with params {params['lat']},{params['lon']}...")
    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status() # This will raise an HTTPError for 4xx/5xx responses
    print(f"[{datetime.now()}] Successfully received raw JSON data.")
    return response.json()


def fetch_and_store_weather_data():
    """
    Fetches current weather data for SF and NYC from OpenWeatherMap and stores it.
    Includes data validation and robust error handling.
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
                "units": "metric" # For Celsius
            }

            print(f"[{datetime.now()}] Attempting to fetch weather data for {location['name']}...")
            try:
                # --- API Call with Retry Logic ---
                data = fetch_raw_weather_data(OPENWEATHER_API_URL, params)

                # --- Extract and Validate Data ---
                api_timestamp_unix = data.get('dt')
                if api_timestamp_unix is None:
                    print(f"[{datetime.now()}] Warning: Timestamp 'dt' missing from weather data for {location['name']}. Skipping record.")
                    continue # Skip to the next location in the loop

                api_timestamp = datetime.fromtimestamp(api_timestamp_unix, tz=timezone.utc)
                
                weather_main = data.get('weather', [{}])[0]
                main_data = data.get('main', {})
                wind_data = data.get('wind', {})

                # Prepare data for Pydantic validation
                data_dict = {
                    "location_name": location['name'],
                    "latitude": location['lat'],
                    "longitude": location['lon'],
                    "temperature_celsius": main_data.get('temp'),
                    "humidity_percent": main_data.get('humidity'),
                    "wind_speed_mps": wind_data.get('speed'),
                    "weather_condition": weather_main.get('main'),
                    "weather_description": weather_main.get('description'),
                    "precipitation_1h_mm": data.get('rain', {}).get('1h'), # Safely get 1-hour rain volume
                    "api_timestamp": api_timestamp
                }

                try:
                    # Pydantic validation: raises ValidationError if data is not valid
                    validated_data = WeatherDataPydantic(**data_dict)
                    
                    # Create SQLAlchemy model instance from validated data
                    new_record = WeatherData(**validated_data.model_dump())
                    new_weather_records.append(new_record)
                    print(f"[{datetime.now()}] Successfully processed weather data for {location['name']}.")
                    
                except ValidationError as e:
                    print(f"[{datetime.now()}] Data validation failed for weather record for '{location['name']}': {e}. Skipping record.")
                except Exception as e:
                    print(f"[{datetime.now()}] Unexpected error during weather data processing for '{location['name']}': {e}. Skipping record.")
                    continue # Skip to next location if processing fails

            except tenacity.RetryError as e:
                print(f"[{datetime.now()}] Fatal API error after all retries for {location['name']}: {e}")
            except requests.exceptions.RequestException as e:
                print(f"[{datetime.now()}] Network error for {location['name']}: {e}")
            except Exception as e:
                print(f"[{datetime.now()}] An unexpected error occurred for {location['name']}: {e}")

        # This block is outside the 'for' loop and will execute once all API calls are made
        if new_weather_records:
            db.add_all(new_weather_records)
            db.commit()
            print(f"[{datetime.now()}] Successfully stored {len(new_weather_records)} new weather records.")
        else:
            print(f"[{datetime.now()}] No new valid weather records to store.")

    except SQLAlchemyError as e:
        db.rollback()
        print(f"[{datetime.now()}] Database error during weather data insertion: {e}")
    except Exception as e:
        # Catch any other unexpected errors during the entire process
        print(f"[{datetime.now()}] An unexpected error occurred during weather data collection: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    fetch_and_store_weather_data()