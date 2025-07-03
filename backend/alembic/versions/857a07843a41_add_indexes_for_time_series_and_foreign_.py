"""Add indexes for time-series and foreign key columns

Revision ID: 857a07843a41
Revises: ea49f4099f48
Create Date: 2025-07-03 16:09:59.910617

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '857a07843a41'
down_revision: Union[str, Sequence[str], None] = 'ea49f4099f48'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Indexes for vehicle_positions
    op.create_index('idx_vehicle_positions_api_timestamp', 'vehicle_positions', ['api_timestamp'], unique=False)
    op.create_index('idx_vehicle_positions_route_id', 'vehicle_positions', ['route_id'], unique=False)
    op.create_index('idx_vehicle_positions_vehicle_id', 'vehicle_positions', ['vehicle_id'], unique=False)
    op.create_index('idx_vehicle_positions_trip_id', 'vehicle_positions', ['trip_id'], unique=False)

    # Indexes for bike_station_status
    op.create_index('idx_bike_station_status_last_reported', 'bike_station_status', ['last_reported'], unique=False)
    op.create_index('idx_bike_station_status_station_id', 'bike_station_status', ['station_id'], unique=False)

    # Indexes for weather_data
    op.create_index('idx_weather_data_api_timestamp', 'weather_data', ['api_timestamp'], unique=False)
    op.create_index('idx_weather_data_location_name', 'weather_data', ['location_name'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    # Drop indexes in reverse order
    op.drop_index('idx_weather_data_location_name', table_name='weather_data')
    op.drop_index('idx_weather_data_api_timestamp', table_name='weather_data')

    op.drop_index('idx_bike_station_status_station_id', table_name='bike_station_status')
    op.drop_index('idx_bike_station_status_last_reported', table_name='bike_station_status')

    op.drop_index('idx_vehicle_positions_trip_id', table_name='vehicle_positions')
    op.drop_index('idx_vehicle_positions_vehicle_id', table_name='vehicle_positions')
    op.drop_index('idx_vehicle_positions_route_id', table_name='vehicle_positions')
    op.drop_index('idx_vehicle_positions_api_timestamp', table_name='vehicle_positions')
