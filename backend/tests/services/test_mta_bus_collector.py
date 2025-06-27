# backend/tests/services/test_mta_bus_collector.py
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta, date
import os
import sys

# Go up to the 'flux/' project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from backend.app.services.data_collectors.mta_bus_collector import fetch_and_store_mta_bus_positions
from backend.app.models.vehicle_position import VehiclePosition

# Mock environment variables for testing
@pytest.fixture(autouse=True)
def mock_env_vars(monkeypatch):
    monkeypatch.setenv("MTA_BUS_API_KEY", "mock_mta_key")
    monkeypatch.setenv("MTA_AGENCY_ID", "MTA NYCT") # Use the same agency ID you used to get data
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:") # Use in-memory SQLite for tests

@pytest.fixture
def mock_mta_siri_vehicle_data():
    # Minimal representative JSON structure based on the data you provided
    return {
        "Siri": {
            "ServiceDelivery": {
                "ResponseTimestamp": "2025-06-27T19:28:25.639-04:00",
                "VehicleMonitoringDelivery": [
                    {
                        "ResponseTimestamp": "2025-06-27T19:28:25.639-04:00",
                        "ValidUntil": "2025-06-27T19:29:25.639-04:00",
                        "VehicleActivity": [
                            {
                                "MonitoredVehicleJourney": {
                                    "LineRef": "MTA NYCT_M15",
                                    "DirectionRef": "1",
                                    "FramedVehicleJourneyRef": {
                                        "DataFrameRef": "2025-06-27",
                                        "DatedVehicleJourneyRef": "MTA NYCT_OH_B5-Weekday-104600_M15_233"
                                    },
                                    "PublishedLineName": ["M15"],
                                    "OperatorRef": "MTA NYCT",
                                    "DestinationName": ["SOUTH FERRY via 2 AV"],
                                    "Monitored": True,
                                    "VehicleLocation": {
                                        "Longitude": -74.012199,
                                        "Latitude": 40.701549
                                    },
                                    "Bearing": 196.69925,
                                    "ProgressRate": "normalProgress",
                                    "VehicleRef": "MTA NYCT_5888",
                                    "MonitoredCall": {
                                        "AimedArrivalTime": "2025-06-27T19:28:00.672-04:00",
                                        "ExpectedArrivalTime": "2025-06-27T19:28:26.639-04:00",
                                        "DistanceFromStop": 20,
                                        "NumberOfStopsAway": 0,
                                        "StopPointRef": "MTA_405083"
                                    }
                                },
                                "RecordedAtTime": "2025-06-27T19:28:01.000-04:00"
                            },
                            {
                                "MonitoredVehicleJourney": {
                                    "LineRef": "MTA NYCT_M15",
                                    "DirectionRef": "0",
                                    "FramedVehicleJourneyRef": {
                                        "DataFrameRef": "2025-06-27",
                                        "DatedVehicleJourneyRef": "MTA NYCT_OH_B5-Weekday-111100_M15_237"
                                    },
                                    "PublishedLineName": ["M15"],
                                    "OperatorRef": "MTA NYCT",
                                    "DestinationName": ["EAST HARLEM 125 ST via 1 AV"],
                                    "Monitored": True,
                                    "VehicleLocation": {
                                        "Longitude": -73.933551,
                                        "Latitude": 40.798542
                                    },
                                    "Bearing": 54.29331,
                                    "ProgressRate": "normalProgress",
                                    "Occupancy": "seatsAvailable",
                                    "VehicleRef": "MTA NYCT_6047",
                                    "MonitoredCall": {
                                        "AimedArrivalTime": "2025-06-27T19:32:28.747-04:00",
                                        "ExpectedArrivalTime": "2025-06-27T19:28:33.296-04:00",
                                        "DistanceFromStop": 51,
                                        "NumberOfStopsAway": 0,
                                        "StopPointRef": "MTA_401729"
                                    }
                                },
                                "RecordedAtTime": "2025-06-27T19:28:17.842-04:00"
                            }
                        ]
                    }
                ]
            },
            "SituationExchangeDelivery": [
                # Include a sample of SituationExchangeDelivery if you want to explicitly test
                # that it's being ignored, or remove this part if it's always absent in VM calls.
                # For this test, we care only about VehicleActivity, so this can be trimmed.
            ]
        }
    }


@patch('requests.get')
@patch('backend.app.services.data_collectors.mta_bus_collector.SessionLocal')
def test_fetch_and_store_mta_bus_positions_success(mock_session_local, mock_requests_get, mock_mta_siri_vehicle_data):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_mta_siri_vehicle_data
    mock_response.raise_for_status.return_value = None
    mock_requests_get.return_value = mock_response

    mock_db_session = MagicMock()
    mock_session_local.return_value = mock_db_session

    fetch_and_store_mta_bus_positions()

    mock_requests_get.assert_called_once()
    assert mock_requests_get.call_args[0][0].startswith("https://bustime.mta.info/api/siri/vehicle-monitoring.json")

    mock_session_local.assert_called_once()
    mock_db_session.add_all.assert_called_once()
    mock_db_session.commit.assert_called_once()
    mock_db_session.close.assert_called_once()

    added_positions = mock_db_session.add_all.call_args[0][0]
    assert len(added_positions) == 2 # Based on mock data
    assert isinstance(added_positions[0], VehiclePosition)
    assert isinstance(added_positions[1], VehiclePosition)

    # Assertions for the first vehicle
    assert added_positions[0].vehicle_id == "MTA NYCT_5888"
    assert added_positions[0].trip_id == "MTA NYCT_OH_B5-Weekday-104600_M15_233"
    assert added_positions[0].route_id == "MTA NYCT_M15"
    assert added_positions[0].start_date == date(2025, 6, 27)
    assert added_positions[0].latitude == pytest.approx(40.701549)
    assert added_positions[0].longitude == pytest.approx(-74.012199)
    assert added_positions[0].bearing == pytest.approx(196.69925)
    assert added_positions[0].speed_mps is None # No numerical speed in the provided JSON
    assert added_positions[0].current_stop_sequence is None
    assert added_positions[0].current_status == "normalProgress"
    # For timezone-aware datetimes, compare with a timezone-aware datetime
    assert added_positions[0].api_timestamp == datetime(2025, 6, 27, 19, 28, 1, tzinfo=timezone(timedelta(hours=-4)))

    # Assertions for the second vehicle
    assert added_positions[1].vehicle_id == "MTA NYCT_6047"
    assert added_positions[1].trip_id == "MTA NYCT_OH_B5-Weekday-111100_M15_237"
    assert added_positions[1].route_id == "MTA NYCT_M15"
    assert added_positions[1].start_date == date(2025, 6, 27)
    assert added_positions[1].latitude == pytest.approx(40.798542)
    assert added_positions[1].longitude == pytest.approx(-73.933551)
    assert added_positions[1].bearing == pytest.approx(54.29331)
    assert added_positions[1].speed_mps is None
    assert added_positions[1].current_stop_sequence is None
    assert added_positions[1].current_status == "normalProgress"
    assert added_positions[1].api_timestamp == datetime(2025, 6, 27, 19, 28, 17, 842000, tzinfo=timezone(timedelta(hours=-4)))