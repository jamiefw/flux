# backend/tests/services/test_sfmta_collector.py
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from backend.app.services.data_collectors.sfmta_collector import fetch_and_store_sfmta_vehicle_positions
from backend.app.models.vehicle_position import VehiclePosition
from google.transit import gtfs_realtime_pb2


# Mock the environment variables for testing
@pytest.fixture(autouse=True)
def mock_env_vars(monkeypatch):
    monkeypatch.setenv("SFBAY_API_TOKEN", "mock_token")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:") # Use in-memory SQLite for tests


# Sample GTFS-Realtime data (simplified protobuf structure for demonstration)
# In a real test, you'd create a more complete mock or load from a fixture file.
@pytest.fixture
def mock_gtfs_feed():
    feed = gtfs_realtime_pb2.FeedMessage()

    feed.header.gtfs_realtime_version = "1.0" # Mandatory field 
    feed.header.incrementality = gtfs_realtime_pb2.FeedHeader.FULL_DATASET 
    feed.header.timestamp = int(datetime.now(timezone.utc).timestamp()) 

    entity = feed.entity.add()
    entity.id = "1"
    entity.vehicle.vehicle.id = "mock_vehicle_1"
    entity.vehicle.trip.trip_id = "mock_trip_123"
    entity.vehicle.trip.route_id = "mock_route_A"
    entity.vehicle.trip.start_date = "20250617"
    entity.vehicle.position.latitude = 37.1234
    entity.vehicle.position.longitude = -122.5678
    entity.vehicle.position.bearing = 90.0
    entity.vehicle.position.speed = 10.5
    entity.vehicle.current_stop_sequence = 5
    entity.vehicle.current_status = gtfs_realtime_pb2.VehiclePosition.VehicleStopStatus.IN_TRANSIT_TO
    entity.vehicle.timestamp = 1750192611

    entity2 = feed.entity.add()
    entity2.id = "2"
    entity2.vehicle.vehicle.id = "mock_vehicle_2"
    # This one has missing trip info, as per your API output
    entity2.vehicle.position.latitude = 37.9999
    entity2.vehicle.position.longitude = -122.1111
    entity2.vehicle.position.speed = 0.0
    entity2.vehicle.timestamp = 1750192620

    return feed


# Test that the data fetching and parsing works
@patch('requests.get')
@patch('backend.app.services.data_collectors.sfmta_collector.SessionLocal') # Mock the DB session to avoid hitting actual DB
def test_fetch_and_store_sfmta_vehicle_positions_success(mock_session_local, mock_requests_get, mock_gtfs_feed):
    # Setup mock requests.get to return a successful response with protobuf content
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = mock_gtfs_feed.SerializeToString() # Serialize the mock feed
    mock_response.raise_for_status.return_value = None # No HTTP errors
    mock_requests_get.return_value = mock_response

    # Mock the database session and its methods
    mock_db_session = MagicMock()
    mock_session_local.return_value = mock_db_session

    # Run the collector function
    fetch_and_store_sfmta_vehicle_positions()

    # Assert that requests.get was called
    mock_requests_get.assert_called_once()
    assert mock_requests_get.call_args[0][0].startswith("http://api.511.org/transit/VehiclePositions")

    # Assert that DB session methods were called
    mock_session_local.assert_called_once() # Session was opened
    mock_db_session.add_all.assert_called_once() # Data was added
    mock_db_session.commit.assert_called_once() # Transaction was committed
    mock_db_session.close.assert_called_once() # Session was closed

    # Verify the type of objects added to the database
    added_positions = mock_db_session.add_all.call_args[0][0]
    assert len(added_positions) == 2 # Expecting 2 vehicles from mock_gtfs_feed
    assert isinstance(added_positions[0], VehiclePosition)
    assert isinstance(added_positions[1], VehiclePosition)

    # Basic data validation on the first parsed object
    assert added_positions[0].vehicle_id == "mock_vehicle_1"
    assert added_positions[0].trip_id == "mock_trip_123" # Add this assertion for trip_id
    assert added_positions[0].route_id == "mock_route_A"
    assert added_positions[0].start_date == datetime.strptime("20250617", '%Y%m%d').date() # Test date conversion
    assert added_positions[0].latitude == pytest.approx(37.1234)
    assert added_positions[0].longitude == pytest.approx(-122.5678)
    assert added_positions[0].bearing == pytest.approx(90.0)
    assert added_positions[0].speed_mps == pytest.approx(10.5)
    assert added_positions[0].current_stop_sequence == 5 # Integer comparison is fine
    assert added_positions[0].current_status == "IN_TRANSIT_TO" # String comparison is fine
    assert added_positions[0].api_timestamp == datetime.fromtimestamp(1750192611, tz=timezone.utc)


    # Validate the second vehicle with missing trip data
    assert added_positions[1].vehicle_id == "mock_vehicle_2"
    assert added_positions[1].trip_id is None
    assert added_positions[1].route_id is None
    assert added_positions[1].start_date is None
    assert added_positions[1].latitude == pytest.approx(37.9999) 
    assert added_positions[1].longitude == pytest.approx(-122.1111) 
    assert added_positions[1].bearing is None 
    assert added_positions[1].speed_mps == pytest.approx(0.0) 
    assert added_positions[1].current_stop_sequence is None 
    assert added_positions[1].current_status is None 
    assert added_positions[1].api_timestamp == datetime.fromtimestamp(1750192620, tz=timezone.utc)


# Future tests:
# - Test error handling for HTTP errors (4xx, 5xx)
# - Test error handling for network issues
# - Test cases with empty vehicle list
# - Test specific data transformations (e.g., timestamp conversion)