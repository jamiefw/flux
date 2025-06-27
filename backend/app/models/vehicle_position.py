# backend/app/models/vehicle_position.py
from sqlalchemy import Column, Integer, String, Float, DateTime, Numeric, Date
from sqlalchemy.sql import func # For default timestamps
from sqlalchemy.dialects.postgresql import UUID # If you choose UUIDs for IDs

from backend.app.db.session import Base # Import Base from your session setup

class VehiclePosition(Base):
    __tablename__ = "vehicle_positions" # Name of the table in your database

    id = Column(Integer, primary_key=True, index=True) # Auto-incrementing PK
    vehicle_id = Column(String(50), nullable=False, index=True) # Unique ID for the vehicle (e.g., '1006')
    trip_id = Column(String(100), nullable=True, index=True) # GTFS trip ID (e.g., '11734075_M41')
    route_id = Column(String(50), nullable=True, index=True) # GTFS route ID (e.g., 'F')
    start_date = Column(Date, nullable=True) # Date the trip started (e.g., '20250617')

    latitude = Column(Numeric(10, 7), nullable=False) # Vehicle's current latitude
    longitude = Column(Numeric(10, 7), nullable=False) # Vehicle's current longitude
    bearing = Column(Numeric(5, 2), nullable=True) # Direction in degrees
    speed_mps = Column(Numeric(10, 2), nullable=True) # Speed in meters per second

    current_stop_sequence = Column(Integer, nullable=True) # Current stop in trip sequence
    current_status = Column(String(50), nullable=True) # e.g., 'IN_TRANSIT_TO', 'STOPPED_AT'

    # The timestamp from the GTFS-Realtime feed (when data was reported)
    # Using BigInt to store the raw Unix timestamp, or DateTime to convert and store
    # For better querying and standard practice, DateTime is usually preferred.
    # We will convert the Unix timestamp from the API to a datetime object before saving.
    api_timestamp = Column(DateTime(timezone=True), nullable=False, index=True)

    # Optional: A timestamp for when the record was *inserted* into your DB
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return (
            f"<VehiclePosition(id={self.id}, vehicle_id='{self.vehicle_id}', "
            f"route_id='{self.route_id}', lat={self.latitude}, lon={self.longitude}, "
            f"timestamp={self.api_timestamp})>"
        )