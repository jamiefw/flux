import requests
import os
from google.transit import gtfs_realtime_pb2
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '../../.env.local'))

# --- Configuration ---
SFBAY_API_TOKEN = os.getenv("SFBAY_API_TOKEN") # Safely retrieve API token
SFMTA_AGENCY_ID = "SF"

# GTFS-Realtime Vehicle Positions Endpoint (API 2.16 in the spec)
# Base URL: http://api.511.org/transit/VehiclePositions 
# Parameters: api_key (mandatory), agency (mandatory) 
SFBAY_GTFS_REALTIME_VEHICLE_POSITIONS_URL = f"http://api.511.org/transit/VehiclePositions?api_key={SFBAY_API_TOKEN}&agency={SFMTA_AGENCY_ID}"

def fetch_and_parse_gtfs_realtime_vehicle_data(url: str):
    """Fetches and parses GTFS-Realtime Vehicle Positions data."""
    if not SFBAY_API_TOKEN:
        print("Error: SFBAY_API_TOKEN not found. Please set it in your .env.local file.")
        return None

    print(f"Attempting to fetch GTFS-Realtime data from: {url}")
    try:
        # GTFS-Realtime feeds are binary Protocol Buffers. We fetch content, not JSON.
        response = requests.get(url, timeout=30) # Increased timeout for initial fetch
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)

        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(response.content) # Parse the binary data into a FeedMessage object

        print(f"Successfully fetched and parsed GTFS-Realtime data (contains {len(feed.entity)} entities).")
        return feed

    except requests.exceptions.RequestException as e:
        print(f"Network error fetching GTFS-Realtime data: {e}")
        return None
    except Exception as e:
        print(f"Error parsing GTFS-Realtime data. This often means the API returned non-Protobuf data (e.g., HTML error page): {e}")
        print("Response content (first 500 chars):", response.content[:500].decode('utf-8', errors='ignore') if 'response' in locals() else "N/A")
        return None

if __name__ == "__main__":
    print("--- Initiating 511 SF Bay GTFS-Realtime Vehicle Positions API Test ---")

    vehicle_feed = fetch_and_parse_gtfs_realtime_vehicle_data(SFBAY_GTFS_REALTIME_VEHICLE_POSITIONS_URL)

    if vehicle_feed:
        print("\n--- Sample of Parsed GTFS-Realtime Vehicle Data ---")
        count = 0
        for entity in vehicle_feed.entity:
            # Check if the entity contains vehicle position data
            if entity.HasField('vehicle'):
                vehicle = entity.vehicle
                print(f"\n  Vehicle ID: {vehicle.vehicle.id if vehicle.HasField('vehicle') and vehicle.vehicle.HasField('id') else 'N/A'}")
                print(f"    Trip ID: {vehicle.trip.trip_id if vehicle.HasField('trip') and vehicle.trip.HasField('trip_id') else 'N/A'}")
                print(f"    Route ID: {vehicle.trip.route_id if vehicle.HasField('trip') and vehicle.trip.HasField('route_id') else 'N/A'}")
                print(f"    Start Date: {vehicle.trip.start_date if vehicle.HasField('trip') and vehicle.trip.HasField('start_date') else 'N/A'}")
                print(f"    Lat: {vehicle.position.latitude if vehicle.HasField('position') and vehicle.position.HasField('latitude') else 'N/A'}")
                print(f"    Lon: {vehicle.position.longitude if vehicle.HasField('position') and vehicle.position.HasField('longitude') else 'N/A'}")
                print(f"    Bearing: {vehicle.position.bearing if vehicle.HasField('position') and vehicle.position.HasField('bearing') else 'N/A'} degrees")
                print(f"    Speed: {vehicle.position.speed if vehicle.HasField('position') and vehicle.position.HasField('speed') else 'N/A'} m/s")
                print(f"    Current Stop Seq: {vehicle.current_stop_sequence if vehicle.HasField('current_stop_sequence') else 'N/A'}")
                print(f"    Stop Status: {gtfs_realtime_pb2.VehiclePosition.VehicleStopStatus.Name(vehicle.current_status) if vehicle.HasField('current_status') else 'N/A'}")
                print(f"    Timestamp: {vehicle.timestamp}")

                count += 1
                if count >= 5: # Limit output for brevity
                    print("\n... Displaying first 5 vehicle entities only.")
                    break
            else:
                # Some entities might be TripUpdates or ServiceAlerts, we only care about VehiclePositions for now
                # print(f"Entity {entity.id} is not a vehicle position, skipping.")
                pass
        if count == 0:
            print("No vehicle position entities found in the feed. Check agency ID or API status.")

        print("\n--- Key Action: Analyze This GTFS-Realtime Output! ---")
        print("  - `vehicle.vehicle.id`: Unique identifier for the physical vehicle.")
        print("  - `vehicle.trip.trip_id`: The ID of the trip this vehicle is currently on (from static GTFS).")
        print("  - `vehicle.trip.route_id`: The ID of the route this trip belongs to (from static GTFS).")
        print("  - `vehicle.position.latitude`, `vehicle.position.longitude`: Real-time coordinates.")
        print("  - `vehicle.timestamp`: When this data was last updated (Unix timestamp).")
        print("  - `vehicle.position.speed`: Speed of the vehicle (if available).")
        print("  - `vehicle.current_status`: Whether it's IN_TRANSIT_TO, STOPPED_AT, etc.")
        print("\nThis detailed structure will directly inform your PostgreSQL database schema design for real-time vehicle data.")
    else:
        print("Failed to fetch or parse GTFS-Realtime data. Please check error messages above.")