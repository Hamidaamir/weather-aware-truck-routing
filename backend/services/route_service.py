from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Any

from routing.risk import aggregate_checkpoint_risk, classify_rain, classify_snow, classify_wind, rank_routes, risk_score
from services.checkpoints import build_checkpoints
from services.providers import build_route_geometry, geocode_location
from services.weather_service import determine_weather_for_checkpoints

logger = logging.getLogger(__name__)


def _log_stage(stage: str, started: float, **fields: int) -> None:
    details = ' '.join(f'{name}={value}' for name, value in fields.items())
    logger.info(
        'route_plan_stage stage=%s duration_ms=%.1f%s',
        stage,
        (time.perf_counter() - started) * 1000,
        f' {details}' if details else '',
    )


def generate_plan(origin: str, destination: str, departure_datetime: datetime, load_weight_lbs: float, checkpoint_interval_miles: int, forecast_offset_hours: int) -> dict[str, Any]:
    if origin.strip().lower() == destination.strip().lower():
        raise ValueError('Origin and destination cannot be the same after normalization.')

    geocode_started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=2) as executor:
        origin_future = executor.submit(geocode_location, origin)
        destination_future = executor.submit(geocode_location, destination)
        origin_geo = origin_future.result()
        destination_geo = destination_future.result()
    _log_stage('geocoding', geocode_started, lookups=2)

    routing_started = time.perf_counter()
    route_payload = build_route_geometry(
        (origin_geo['lat'], origin_geo['lon']),
        (destination_geo['lat'], destination_geo['lon']),
    )
    _log_stage('routing', routing_started, routes=len(route_payload['routes']))

    geometry_started = time.perf_counter()
    prepared_routes: list[dict[str, Any]] = []
    all_checkpoints: list[dict[str, Any]] = []
    for index, route in enumerate(route_payload['routes'], start=1):
        distance_miles = route['distance_meters'] / 1609.344
        duration_minutes = route['duration_seconds'] / 60
        checkpoints = build_checkpoints(
            route['geometry'],
            checkpoint_interval_miles,
            departure_datetime,
            route['duration_seconds'],
        )
        for checkpoint in checkpoints:
            checkpoint['arrival'] = datetime.fromisoformat(checkpoint['eta'])
        prepared_routes.append({
            'name': f'Alternative {index}',
            'distance_miles': round(distance_miles, 2),
            'duration_seconds': route['duration_seconds'],
            'duration_minutes': round(duration_minutes, 2),
            'geometry': route['geometry'],
            'checkpoints': checkpoints,
        })
        all_checkpoints.extend(checkpoints)
    _log_stage(
        'geometry_and_checkpoints',
        geometry_started,
        route_count=len(prepared_routes),
        checkpoint_count=len(all_checkpoints),
    )

    weather_started = time.perf_counter()
    forecasts = determine_weather_for_checkpoints(
        all_checkpoints,
        departure_datetime,
        forecast_offset_hours,
    )
    _log_stage('weather_processing', weather_started, checkpoint_count=len(all_checkpoints))

    risk_started = time.perf_counter()
    for checkpoint, weather in zip(all_checkpoints, forecasts):
        checkpoint['forecast'] = weather
        wind_level = classify_wind(weather.get('wind_mph'), load_weight_lbs) if not weather.get('missing') else 'unknown'
        rain_level = classify_rain(weather.get('rain_in_hr')) if not weather.get('missing') else 'unknown'
        snow_level = classify_snow(weather.get('snow_in_hr')) if not weather.get('missing') else 'unknown'
        checkpoint['risk'] = aggregate_checkpoint_risk(wind_level, rain_level, snow_level)
        checkpoint['wind_risk'] = wind_level
        checkpoint['rain_risk'] = rain_level
        checkpoint['snow_risk'] = snow_level

    routes = []
    for route in prepared_routes:
        checkpoints = route['checkpoints']
        severe_miles = sum(cp['distance_miles'] for cp in checkpoints if cp['risk'] == 'severe')
        high_miles = sum(cp['distance_miles'] for cp in checkpoints if cp['risk'] == 'high')
        no_travel_count = sum(1 for cp in checkpoints if cp['risk'] == 'no_travel')
        average_risk = sum(risk_score(cp['risk']) for cp in checkpoints) / len(checkpoints) if checkpoints else 0
        coverage = (
            sum(1 for cp in checkpoints if not cp['forecast'].get('missing')) / len(checkpoints) * 100
            if checkpoints else 0
        )
        routes.append({
            'name': route['name'],
            'distance_miles': route['distance_miles'],
            'duration_minutes': route['duration_minutes'],
            'eta': (departure_datetime + timedelta(seconds=route['duration_seconds'])).isoformat(),
            'geometry': route['geometry'],
            'checkpoints': checkpoints,
            'severe_miles': severe_miles,
            'high_miles': high_miles,
            'no_travel_checkpoints': no_travel_count,
            'average_risk_score': average_risk,
            'weather_coverage_percent': coverage,
            'has_confirmed_no_travel': no_travel_count > 0,
            'recommendation_status': 'eligible',
        })
    ranked = rank_routes(routes)
    recommended = next((route for route in ranked if route.get('eligible_for_recommendation')), None)
    if recommended is not None:
        recommended['recommended'] = True
    _log_stage('risk_and_ranking', risk_started, route_count=len(ranked))

    return {
        'origin': {'name': origin_geo['name'], 'lat': origin_geo['lat'], 'lon': origin_geo['lon']},
        'destination': {'name': destination_geo['name'], 'lat': destination_geo['lat'], 'lon': destination_geo['lon']},
        'routes': ranked,
        'recommended_route': recommended,
        'warnings': route_payload.get('warnings', []),
        'metadata': {
            'weather_offset_hours': forecast_offset_hours,
            'load_weight_lbs': load_weight_lbs,
            'checkpoint_interval_miles': checkpoint_interval_miles,
            'departure_datetime': departure_datetime.isoformat(),
        },
    }
