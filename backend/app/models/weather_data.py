# backend/app/models/weather_data.py
from sqlalchemy import Column, Integer, String, Float, DateTime, Numeric
from sqlalchemy.sql import func
from backend.app.db.session import Base

class WeatherData(Base):
    __tablename__ = "weather_data"

    id = Column(Integer, primary_key=True, index=True)
    location_name = Column(String(50), nullable=False, index=True) # E.g., 'San Francisco', 'New York City'
    latitude = Column(Numeric(10, 7), nullable=False)
    longitude = Column(Numeric(10, 7), nullable=False)
    
    temperature_celsius = Column(Numeric(5, 2), nullable=True)
    humidity_percent = Column(Integer, nullable=True)
    wind_speed_mps = Column(Numeric(5, 2), nullable=True)
    
    weather_condition = Column(String(255), nullable=True) # E.g., 'Clouds', 'Rain'
    weather_description = Column(String(255), nullable=True) # E.g., 'overcast clouds'
    
    # Precipitation: OpenWeather's 'rain' or 'snow' in 1h or 3h.
    # We will just store the 1h value if available.
    precipitation_1h_mm = Column(Numeric(5, 2), nullable=True) 

    # The timestamp from the weather report itself
    api_timestamp = Column(DateTime(timezone=True), nullable=False, index=True)

    # When this record was inserted into your DB
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    def __repr__(self):
        return (
            f"<WeatherData(id={self.id}, location='{self.location_name}', "
            f"temp={self.temperature_celsius}°C, time={self.api_timestamp})>"
        )