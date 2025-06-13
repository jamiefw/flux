
import requests
import json
import os # To potentially read API keys if needed later (not for SFMTA)

# SFMTA (NextBus) API endpoint for vehicle locations.
SFMTA_VEHICLE_LOCATIONS_URL = "http://webservices.nextbus.com/service/publicJSONFeed?command=vehicleLocations&a=sf-muni&t=0"

# specific routes
# N-Judah line:
SFMTA_N_JUDAH_URL = "http://webservices.nextbus.com/service/publicJSONFeed?command=vehicleLocations&a=sf-muni&r=N&t=0"


def fetch_sfmta_vehicle_data(url: str):
    """Fetches vehicle location data from the SFMTA (NextBus) API."""
    print(f"Fetching data from: {url}")
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
        data = response.json()
        return data
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data from SFMTA API: {e}")
        return None

if __name__ == "__main__":
    print("--- Testing ALL SFMTA Muni Vehicle Locations ---")
    all_vehicle_data = fetch_sfmta_vehicle_data(SFMTA_VEHICLE_LOCATIONS_URL)
    if all_vehicle_data:
        
        print(json.dumps(all_vehicle_data, indent=2))
        if 'vehicle' in all_vehicle_data.get('vehicleList', {}):
            print(f"\n--- Sample of SFMTA Muni Vehicles ({len(all_vehicle_data['vehicleList']['vehicle'])} total) ---")
            for i, vehicle in enumerate(all_vehicle_data['vehicleList']['vehicle'][:5]): # Display first 5 vehicles
                print(f"  Vehicle ID: {vehicle.get('id')}, Route: {vehicle.get('routeTag')}, Lat: {vehicle.get('lat')}, Lon: {vehicle.get('lon')}, Speed: {vehicle.get('speedKmHr')}, SecsSinceReport: {vehicle.get('secsSinceReport')}")
        else:
            print("No 'vehicle' key found in vehicleList. Check the JSON structure for 'vehicleList'.")
    else:
        print("Failed to fetch all vehicle data.")

    print("\n" + "="*80 + "\n") # Separator

    print("--- Testing SFMTA Muni N-Judah (N) Line Vehicle Locations ---")
    n_judah_data = fetch_sfmta_vehicle_data(SFMTA_N_JUDAH_URL)
    if n_judah_data:
        print(json.dumps(n_judah_data, indent=2))
        if 'vehicle' in n_judah_data.get('vehicleList', {}):
            print(f"\n--- Sample of N-Judah Vehicles ({len(n_judah_data['vehicleList']['vehicle'])} total) ---")
            for i, vehicle in enumerate(n_judah_data['vehicleList']['vehicle'][:5]):
                print(f"  Vehicle ID: {vehicle.get('id')}, Route: {vehicle.get('routeTag')}, Lat: {vehicle.get('lat')}, Lon: {vehicle.get('lon')}, Speed: {vehicle.get('speedKmHr')}, SecsSinceReport: {vehicle.get('secsSinceReport')}")
        else:
            print("No 'vehicle' key found in vehicleList for N-Judah. Check JSON structure.")
    else:
        print("Failed to fetch N-Judah data.")


    print("\n--- Important Next Step: Analyze This JSON! ---")
    print("Look for fields like: 'id', 'routeTag', 'dirTag', 'lat', 'lon', 'speedKmHr', 'heading', 'secsSinceReport', 'predictable'.")
    print("These will be the columns in your PostgreSQL database for vehicle location data.")