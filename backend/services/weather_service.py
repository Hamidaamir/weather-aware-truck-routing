from __future__ import annotations

from bisect import bisect_left
from datetime import datetime, timedelta, timezone
from math import isfinite
from typing import Any

from services.providers import fetch_weather, fetch_weather_batch


def convert_kmh_to_mph(value: float | None) -> float | None:
    if value is None:
        return None
    return value * 0.621371


def convert_mm_to_inches(value: float | None) -> float | None:
    if value is None:
        return None
    return value * 0.0393701


def determine_weather_for_checkpoint(
    checkpoint: dict[str, Any],
    route_departure: datetime,
    forecast_offset_hours: int,
    weather: dict[str, Any] | None = None,
) -> dict[str, Any]:
    lat = checkpoint['lat']
    lon = checkpoint['lon']
    if weather is None:
        weather = fetch_weather(lat, lon, route_departure, forecast_offset_hours)
    payload = weather['payload']
    hourly = payload.get('hourly') or {}
    times = hourly.get('time') or []
    wind = hourly.get('wind_speed_10m') or []
    rain = hourly.get('rain') or []
    snow = hourly.get('snowfall') or []
    if not times:
        return {'missing': True, 'coverage_warning': 'Weather data is unavailable for this checkpoint.', 'wind_mph': None, 'rain_in_hr': None, 'snow_in_hr': None}
    arrival = checkpoint.get('arrival')
    if isinstance(arrival, str):
        arrival = datetime.fromisoformat(arrival)
    delta_seconds = (arrival - route_departure).total_seconds() if isinstance(arrival, datetime) else 0
    target_dt = route_departure + timedelta(seconds=delta_seconds, hours=forecast_offset_hours)
    if target_dt.tzinfo is None:
        target_dt = target_dt.replace(tzinfo=timezone.utc)
    else:
        target_dt = target_dt.astimezone(timezone.utc)
    try:
        forecast_datetimes = [
            datetime.fromisoformat(time_value.replace('Z', '+00:00'))
            for time_value in times
        ]
    except (AttributeError, TypeError, ValueError):
        return {'missing': True, 'coverage_warning': 'Weather data is unavailable for this checkpoint.', 'wind_mph': None, 'rain_in_hr': None, 'snow_in_hr': None}
    forecast_datetimes = [
        forecast_dt.replace(tzinfo=timezone.utc)
        if forecast_dt.tzinfo is None
        else forecast_dt.astimezone(timezone.utc)
        for forecast_dt in forecast_datetimes
    ]
    insertion_index = bisect_left(forecast_datetimes, target_dt)
    candidate_indices = [index for index in (insertion_index - 1, insertion_index) if 0 <= index < len(forecast_datetimes)]
    nearest_index = min(candidate_indices, key=lambda index: abs((forecast_datetimes[index] - target_dt).total_seconds()))
    forecast_dt = forecast_datetimes[nearest_index]
    if any(nearest_index >= len(values) or values[nearest_index] is None for values in (wind, rain, snow)):
        return {'missing': True, 'coverage_warning': 'Weather data is unavailable for this checkpoint.', 'wind_mph': None, 'rain_in_hr': None, 'snow_in_hr': None}
    try:
        wind_value, rain_value, snow_value = (
            float(values[nearest_index])
            for values in (wind, rain, snow)
        )
    except (TypeError, ValueError):
        return {'missing': True, 'coverage_warning': 'Weather data is unavailable for this checkpoint.', 'wind_mph': None, 'rain_in_hr': None, 'snow_in_hr': None}
    if not all(isfinite(value) for value in (wind_value, rain_value, snow_value)):
        return {'missing': True, 'coverage_warning': 'Weather data is unavailable for this checkpoint.', 'wind_mph': None, 'rain_in_hr': None, 'snow_in_hr': None}
    wind_mph = convert_kmh_to_mph(wind_value)
    rain_in_hr = convert_mm_to_inches(rain_value)
    snow_in_hr = convert_mm_to_inches(snow_value)
    return {
        'missing': False,
        'forecast_time': forecast_dt.isoformat(),
        'wind_mph': wind_mph,
        'rain_in_hr': rain_in_hr,
        'snow_in_hr': snow_in_hr,
    }


def determine_weather_for_checkpoints(
    checkpoints: list[dict[str, Any]],
    route_departure: datetime,
    forecast_offset_hours: int,
) -> list[dict[str, Any]]:
    coordinates = [(checkpoint['lat'], checkpoint['lon']) for checkpoint in checkpoints]
    weather_by_coordinate = fetch_weather_batch(coordinates, forecast_offset_hours)
    return [
        determine_weather_for_checkpoint(
            checkpoint,
            route_departure,
            forecast_offset_hours,
            weather_by_coordinate[f'{checkpoint["lat"]:.5f},{checkpoint["lon"]:.5f}'],
        )
        for checkpoint in checkpoints
    ]
