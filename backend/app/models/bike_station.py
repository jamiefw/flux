# backend/app/models/bike_station.py
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Numeric, ForeignKey
from sqlalchemy.orm import relationship # Used for defining relationships between models
from sqlalchemy.sql import func # For default timestamps

from backend.app.db.session import Base # Import Base from your session setup

class BikeStation(Base):
    __tablename__ = "bike_stations" # Table for static station information

    station_id = Column(String(50), primary_key=True, index=True) # Unique ID for the station
    name = Column(String(255), nullable=False) # Name of the station
    latitude = Column(Numeric(10, 7), nullable=False) # Latitude of the station
    longitude = Column(Numeric(10, 7), nullable=False) # Longitude of the station
    capacity = Column(Integer, nullable=True) # Total number of docks
    
    # These fields are common in station_information, make nullable=True if not always present
    rental_methods = Column(String(255), nullable=True) # E.g., 'KEY,CREDITCARD'
    external_id = Column(String(255), nullable=True, index=True)
    address = Column(String(255), nullable=True)
    region_id = Column(String(50), nullable=True, index=True)
    is_charging_station = Column(Boolean, nullable=True)
    parking_type = Column(String(50), nullable=True) # e.g., 'docked', 'free_floating'

    last_updated = Column(DateTime(timezone=True), nullable=True) # When this static data was last updated by the provider

    # Relationship to BikeStationStatus (one-to-many: one station has many status records)
    # This allows you to access station_status records from a BikeStation object
    statuses = relationship("BikeStationStatus", back_populates="station")

    def __repr__(self):
        return (
            f"<BikeStation(station_id='{self.station_id}', name='{self.name}', "
            f"lat={self.latitude}, lon={self.longitude}, capacity={self.capacity})>"
        )


class BikeStationStatus(Base):
    __tablename__ = "bike_station_status" # Table for real-time station status

    id = Column(Integer, primary_key=True, index=True) # Auto-incrementing primary key
    station_id = Column(String(50), ForeignKey("bike_stations.station_id"), nullable=False, index=True) # Foreign key

    num_bikes_available = Column(Integer, nullable=False) # Number of available bikes
    num_docks_available = Column(Integer, nullable=False) # Number of available docks

    # These fields can be null if not provided by the API
    num_ebikes_available = Column(Integer, nullable=True)
    num_scooters_available = Column(Integer, nullable=True) # If they ever add scooters

    is_renting = Column(Boolean, nullable=False) # Is the station active for rentals?
    is_returning = Column(Boolean, nullable=False) # Is the station active for returns?
    is_installed = Column(Boolean, nullable=False) # Is the station installed?

    last_reported = Column(DateTime(timezone=True), nullable=False, index=True) # Timestamp of this status report from the feed

    # When this record was inserted into your DB
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationship to BikeStation (many-to-one: many status records belong to one station)
    # This allows you to access station details from a BikeStationStatus object
    station = relationship("BikeStation", back_populates="statuses")

    def __repr__(self):
        return (
            f"<BikeStationStatus(id={self.id}, station_id='{self.station_id}', "
            f"bikes_available={self.num_bikes_available}, docks_available={self.num_docks_available}, "
            f"last_reported={self.last_reported})>"
        )