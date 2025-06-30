# backend/app/services/data_collectors/bay_wheels_collector.py
import os
import sys
import requests
import datetime
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

# Ensure sys.path is correct for this file (goes up to 'flux/' root)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..')))

from backend.app.db.session import SessionLocal
from backend.app.models.bike_station import BikeStation, BikeStationStatus
from backend.app.core.config import BAY_WHEELS_GBFS_URL

from dotenv import load_dotenv # Needed here as well for direct script execution
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '../../../.env.local'))

# This will hold the URLs after discovery
GBFS_FEEDS = {}

def fetch_gbfs_feed_urls():
    """
    Fetches the GBFS discovery feed to get URLs for all other feeds.
    Caches the results in the GBFS_FEEDS dictionary.
    """
    global GBFS_FEEDS
    if GBFS_FEEDS:
        return GBFS_FEEDS # Use cached URLs if already fetched

    print(f"[{datetime.datetime.now()}] Discovering GBFS feed URLs from: {BAY_WHEELS_GBFS_URL}...")
    try:
        response = requests.get(BAY_WHEELS_GBFS_URL, timeout=15)
        response.raise_for_status()
        feed_data = response.json()

        # The GBFS discovery JSON you provided has 'data' -> 'en' -> 'feeds'
        feeds = feed_data.get('data', {}).get('en', {}).get('feeds', [])
        
        # Populate the GBFS_FEEDS dictionary for easy lookup by feed name
        for feed in feeds:
            GBFS_FEEDS[feed['name']] = feed['url']
        
        print("Successfully discovered GBFS feeds:", list(GBFS_FEEDS.keys()))
        return GBFS_FEEDS
    
    except requests.exceptions.RequestException as e:
        print(f"Error fetching GBFS discovery feed: {e}")
        return {}


def fetch_and_store_static_station_info():
    """
    Fetches static station information and performs an upsert into the database.
    This should be run infrequently (e.g., once per day).
    """
    feeds = fetch_gbfs_feed_urls()
    station_info_url = feeds.get('station_information')
    
    if not station_info_url:
        print("Station information URL not found in GBFS feed. Aborting static data collection.")
        return

    print(f"[{datetime.datetime.now()}] Fetching static station info from: {station_info_url}...")
    db: Session = SessionLocal()
    try:
        response = requests.get(station_info_url, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        stations_data = data.get('data', {}).get('stations', [])
        print(f"Successfully fetched {len(stations_data)} static station records.")

        for station_info in stations_data:
            # Check for essential fields
            if station_info.get('station_id') and station_info.get('lat') and station_info.get('lon'):
                # Check if station already exists
                existing_station = db.query(BikeStation).filter(BikeStation.station_id == station_info['station_id']).first()
                
                # Use a dictionary to prepare data for update/insert
                station_data = {
                    'station_id': station_info.get('station_id'),
                    'name': station_info.get('name'),
                    'latitude': station_info.get('lat'),
                    'longitude': station_info.get('lon'),
                    'capacity': station_info.get('capacity'),
                    'rental_methods': ','.join(station_info.get('rental_methods', [])), # Join list into a string
                    'external_id': station_info.get('external_id'),
                    'address': station_info.get('address'),
                    'region_id': station_info.get('region_id'),
                    'is_charging_station': station_info.get('is_charging_station'),
                    'parking_type': station_info.get('parking_type'),
                    'last_updated': datetime.datetime.fromtimestamp(data.get('last_updated', 0)) # Use feed's last_updated timestamp
                }

                if existing_station:
                    # Update existing record
                    for key, value in station_data.items():
                        setattr(existing_station, key, value)
                    print(f"Updated static info for station: {station_info['station_id']}")
                else:
                    # Insert new record
                    new_station = BikeStation(**station_data)
                    db.add(new_station)
                    print(f"Inserted new static info for station: {station_info['station_id']}")
            else:
                print(f"Skipping static record due to missing essential data: {station_info}")

        db.commit()
    except requests.exceptions.RequestException as e:
        print(f"Network error fetching station info: {e}")
    except SQLAlchemyError as e:
        db.rollback()
        print(f"Database error during static station info upsert: {e}")
    finally:
        db.close()


def fetch_and_store_realtime_station_status():
    """
    Fetches real-time station status and inserts new records into the database.
    This should be run frequently (e.g., every 60 seconds).
    """
    feeds = fetch_gbfs_feed_urls()
    station_status_url = feeds.get('station_status')
    
    if not station_status_url:
        print("Station status URL not found in GBFS feed. Aborting real-time data collection.")
        return

    print(f"[{datetime.datetime.now()}] Fetching real-time station status from: {station_status_url}...")
    db: Session = SessionLocal()
    try:
        response = requests.get(station_status_url, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        statuses_data = data.get('data', {}).get('stations', [])
        last_reported_timestamp = data.get('last_updated', None)
        
        if last_reported_timestamp:
            last_reported_dt = datetime.datetime.fromtimestamp(last_reported_timestamp, tz=datetime.timezone.utc)
        else:
            print("Warning: 'last_updated' timestamp missing from status feed. Using current time.")
            last_reported_dt = datetime.datetime.now(datetime.timezone.utc)

        new_status_records = []
        for status_info in statuses_data:
            # Ensure station_id and availability numbers are present
            if status_info.get('station_id') and status_info.get('num_bikes_available') is not None and status_info.get('num_docks_available') is not None:
                new_status = BikeStationStatus(
                    station_id=status_info['station_id'],
                    num_bikes_available=status_info.get('num_bikes_available'),
                    num_docks_available=status_info.get('num_docks_available'),
                    num_ebikes_available=status_info.get('num_ebikes_available'),
                    num_scooters_available=status_info.get('num_scooters_available'),
                    is_renting=bool(status_info.get('is_renting')), # Convert to boolean
                    is_returning=bool(status_info.get('is_returning')), # Convert to boolean
                    is_installed=bool(status_info.get('is_installed')), # Convert to boolean
                    last_reported=datetime.datetime.fromtimestamp(status_info.get('last_reported', last_reported_timestamp), tz=datetime.timezone.utc)
                )
                new_status_records.append(new_status)
            else:
                print(f"Skipping status record due to missing essential data: {status_info}")
        
        if new_status_records:
            db.add_all(new_status_records)
            db.commit()
            print(f"Successfully stored {len(new_status_records)} new Bay Wheels station status records.")
        else:
            print("No new valid Bay Wheels station status records to store.")
            
    except requests.exceptions.RequestException as e:
        print(f"Network error fetching station status: {e}")
    except SQLAlchemyError as e:
        db.rollback()
        print(f"Database error during station status insertion: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    # Example usage for manual execution
    # Run this once a day or manually to update static info
    # fetch_and_store_static_station_info() 
    
    # Run this every 60 seconds via a scheduler (e.g., asyncio loop, cron job)
    fetch_and_store_realtime_station_status()