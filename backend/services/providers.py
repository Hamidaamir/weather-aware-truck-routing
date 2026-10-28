from __future__ import annotations

import logging
import hashlib
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import requests
from django.conf import settings
from django.core.cache import cache
from requests.adapters import HTTPAdapter

logger = logging.getLogger(__name__)

_SESSION_STATE = threading.local()
_CONNECT_TIMEOUT_SECONDS = 3
_READ_TIMEOUT_SECONDS = 15
_WEATHER_BATCH_SIZE = 50
_WEATHER_CACHE_SECONDS = 300


def _http_session() -> requests.Session:
    session = getattr(_SESSION_STATE, 'session', None)
    if session is None:
        session = requests.Session()
        adapter = HTTPAdapter(pool_connections=10, pool_maxsize=10, max_retries=0)
        session.mount('https://', adapter)
        session.mount('http://', adapter)
        _SESSION_STATE.session = session
    return session


def _provider_timeout(read_timeout_seconds: float) -> tuple[int, float]:
    return (_CONNECT_TIMEOUT_SECONDS, min(read_timeout_seconds, _READ_TIMEOUT_SECONDS))


def _cache_key(namespace: str, values: Any) -> str:
    serialized = json.dumps(values, sort_keys=True, separators=(',', ':'), default=str)
    digest = hashlib.sha256(serialized.encode('utf-8')).hexdigest()
    return f'weather-routing:{namespace}:v1:{digest}'


def _coordinate_key(latitude: float, longitude: float) -> str:
    return f'{latitude:.5f},{longitude:.5f}'


def _fetch_weather_payload(coordinates: list[tuple[float, float]], forecast_hours: int) -> list[dict[str, Any]]:
    started = time.perf_counter()
    params = {
        'latitude': ','.join(f'{latitude:.5f}' for latitude, _ in coordinates),
        'longitude': ','.join(f'{longitude:.5f}' for _, longitude in coordinates),
        'hourly': 'wind_speed_10m,rain,snowfall',
        'timezone': 'UTC',
        'forecast_hours': forecast_hours,
    }
    try:
        response = _http_session().get(
            'https://api.open-meteo.com/v1/forecast',
            params=params,
            timeout=_provider_timeout(getattr(settings, 'WEATHER_TIMEOUT_SECONDS', 15)),
        )
    except requests.Timeout as exc:
        logger.info(
            'provider_request provider=open_meteo operation=forecast locations=%d duration_ms=%.1f outcome=timeout',
            len(coordinates),
            (time.perf_counter() - started) * 1000,
        )
        raise ProviderTimeoutError('Open-Meteo weather request timed out.') from exc
    except requests.RequestException as exc:
        logger.info(
            'provider_request provider=open_meteo operation=forecast locations=%d duration_ms=%.1f outcome=network_error',
            len(coordinates),
            (time.perf_counter() - started) * 1000,
        )
        raise ProviderError('Could not connect to Open-Meteo.') from exc

    logger.info(
        'provider_request provider=open_meteo operation=forecast locations=%d duration_ms=%.1f status=%d',
        len(coordinates),
        (time.perf_counter() - started) * 1000,
        response.status_code,
    )
    if response.status_code == 429:
        raise ProviderRateLimitError('Open-Meteo rate limit reached. Please try again later.')
    if response.status_code >= 500:
        raise ProviderError('Open-Meteo is currently unavailable.')
    if not response.ok:
        raise ProviderError('Failed to retrieve forecast data.')
    try:
        payload = response.json()
    except ValueError as exc:
        raise ProviderMalformedResponseError('Open-Meteo returned an invalid weather response.') from exc

    if len(coordinates) == 1 and isinstance(payload, dict):
        locations = [payload]
    elif isinstance(payload, list):
        locations = payload
    else:
        raise ProviderMalformedResponseError('Open-Meteo returned an invalid multi-location response.')
    if len(locations) != len(coordinates) or any(not isinstance(location, dict) for location in locations):
        raise ProviderMalformedResponseError('Open-Meteo returned an incomplete multi-location response.')
    if any(
        location.get('hourly') is not None
        and not isinstance(location.get('hourly'), dict)
        for location in locations
    ):
        raise ProviderMalformedResponseError('Open-Meteo returned invalid hourly weather data.')
    return locations

class ProviderError(RuntimeError):
    pass


class ProviderConfigError(ProviderError):
    pass


class ProviderTimeoutError(ProviderError):
    pass


class ProviderRateLimitError(ProviderError):
    pass


class ProviderAuthenticationError(ProviderError):
    pass


class ProviderMalformedResponseError(ProviderError):
    pass


def _require_api_key() -> str:
    key = getattr(settings, 'ORS_API_KEY', '')
    if not key:
        raise ProviderConfigError(
            'OpenRouteService API key is missing. Set ORS_API_KEY in the backend environment.'
        )
    return key


def search_locations(query: str, limit: int = 6) -> list[dict[str, Any]]:
    normalized_query = ' '.join(query.casefold().split())
    key = _cache_key('geocode-search', [normalized_query, limit])
    cached = cache.get(key)
    if cached is not None:
        logger.info('provider_cache provider=openrouteservice operation=geocode_search result=hit')
        return cached
    api_key = _require_api_key()
    started = time.perf_counter()
    try:
        response = _http_session().get(
            'https://api.openrouteservice.org/geocode/search',
            params={
                'api_key': api_key,
                'text': query,
                'boundary.country': 'USA',
                'size': limit,
            },
            timeout=_provider_timeout(getattr(settings, 'ORS_TIMEOUT_SECONDS', 15)),
        )
    except requests.Timeout as exc:
        logger.info('provider_request provider=openrouteservice operation=geocode_search duration_ms=%.1f outcome=timeout', (time.perf_counter() - started) * 1000)
        raise ProviderTimeoutError('OpenRouteService location search timed out.') from exc
    except requests.RequestException as exc:
        logger.info('provider_request provider=openrouteservice operation=geocode_search duration_ms=%.1f outcome=network_error', (time.perf_counter() - started) * 1000)
        raise ProviderError('Could not connect to OpenRouteService location search.') from exc
    logger.info(
        'provider_request provider=openrouteservice operation=geocode_search duration_ms=%.1f status=%d',
        (time.perf_counter() - started) * 1000,
        response.status_code,
    )

    if response.status_code in {401, 403}:
        raise ProviderAuthenticationError('OpenRouteService rejected the geocoding credentials.')
    if response.status_code == 429:
        raise ProviderRateLimitError('OpenRouteService rate limit reached. Please try again shortly.')
    if response.status_code >= 500:
        raise ProviderError('OpenRouteService is currently unavailable.')
    if not response.ok:
        raise ProviderError('OpenRouteService could not search for this location.')

    try:
        features = response.json().get('features') or []
    except (ValueError, AttributeError) as exc:
        raise ProviderMalformedResponseError('OpenRouteService returned an invalid location response.') from exc

    suggestions = []
    seen = set()
    for feature in features[:limit]:
        try:
            coordinates = feature['geometry']['coordinates']
            properties = feature.get('properties') or {}
            longitude, latitude = float(coordinates[0]), float(coordinates[1])
            if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                continue
        except (KeyError, IndexError, TypeError, ValueError):
            continue

        primary = properties.get('name') or properties.get('locality') or properties.get('label')
        label = properties.get('label') or primary
        if not primary or not label:
            continue
        country = properties.get('country_a') or properties.get('country_code') or properties.get('country')
        if country and str(country).strip().upper() not in {
            'US', 'USA', 'UNITED STATES', 'UNITED STATES OF AMERICA',
        }:
            continue
        dedupe_key = (round(latitude, 5), round(longitude, 5), str(label).strip().casefold())
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        secondary_parts = []
        for part in (properties.get('region'), properties.get('country')):
            if part and part != primary and part not in secondary_parts:
                secondary_parts.append(part)
        if not secondary_parts and properties.get('label'):
            secondary_parts = [part.strip() for part in properties['label'].split(',')[1:] if part.strip()]
        suggestions.append({
            'id': str(properties.get('gid') or f'{latitude:.6f},{longitude:.6f}'),
            'primary': str(primary),
            'secondary': ', '.join(secondary_parts),
            'label': str(label),
            'lat': latitude,
            'lon': longitude,
        })
    cache.set(key, suggestions, timeout=3600)
    return suggestions


def geocode_location(query: str) -> dict[str, Any]:
    normalized_query = ' '.join(query.casefold().split())
    key = _cache_key('geocode-location', normalized_query)
    cached = cache.get(key)
    if cached is not None:
        logger.info('provider_cache provider=openrouteservice operation=geocode_location result=hit')
        return cached
    api_key = _require_api_key()
    started = time.perf_counter()
    try:
        response = _http_session().get(
            'https://api.openrouteservice.org/geocode/search',
            params={'api_key': api_key, 'text': query, 'boundary.country': 'USA'},
            timeout=_provider_timeout(getattr(settings, 'ORS_TIMEOUT_SECONDS', 15)),
        )
    except requests.Timeout as exc:
        logger.info('provider_request provider=openrouteservice operation=geocode_location duration_ms=%.1f outcome=timeout', (time.perf_counter() - started) * 1000)
        raise ProviderTimeoutError('OpenRouteService location lookup timed out.') from exc
    except requests.RequestException as exc:
        logger.info('provider_request provider=openrouteservice operation=geocode_location duration_ms=%.1f outcome=network_error', (time.perf_counter() - started) * 1000)
        raise ProviderError('Could not connect to OpenRouteService location lookup.') from exc
    logger.info(
        'provider_request provider=openrouteservice operation=geocode_location duration_ms=%.1f status=%d',
        (time.perf_counter() - started) * 1000,
        response.status_code,
    )
    if response.status_code in {401, 403}:
        raise ProviderAuthenticationError('OpenRouteService rejected the geocoding credentials.')
    if response.status_code == 429:
        raise ProviderRateLimitError('OpenRouteService rate limit reached. Please try again later.')
    if response.status_code >= 500:
        raise ProviderError('OpenRouteService is currently unavailable.')
    if not response.ok:
        raise ProviderError('Failed to geocode the provided location.')
    try:
        features = response.json().get('features') or []
    except (ValueError, AttributeError) as exc:
        raise ProviderMalformedResponseError('OpenRouteService returned an invalid geocoding response.') from exc
    if not features:
        raise ProviderError(f'No geocoded result was found for "{query}".')
    if not isinstance(features, list) or not features or not isinstance(features[0], dict):
        raise ProviderMalformedResponseError('OpenRouteService returned an invalid geocoding response.')
    first = features[0]
    geometry = first.get('geometry', {})
    coords = geometry.get('coordinates', [])
    if not isinstance(coords, list) or len(coords) < 2:
        raise ProviderMalformedResponseError(f'Malformed geocoding response for "{query}".')
    try:
        longitude, latitude = float(coords[0]), float(coords[1])
    except (TypeError, ValueError) as exc:
        raise ProviderMalformedResponseError(f'Malformed geocoding response for "{query}".') from exc
    result = {'name': first.get('properties', {}).get('label', query), 'lat': latitude, 'lon': longitude}
    cache.set(key, result, timeout=3600)
    return result


def _safe_upstream_excerpt(response: requests.Response, api_key: str) -> str:
    excerpt = response.text[:1000].replace(api_key, '[redacted]')
    excerpt = re.sub(r'(?i)(authorization|api[_-]?key)(["\'\s:=]+)[^,\s"}]+', r'\1\2[redacted]', excerpt)
    return ' '.join(excerpt.split())[:500]


def _log_directions_failure(response: requests.Response, api_key: str, attempt: str) -> None:
    logger.warning(
        'OpenRouteService directions %s request failed: upstream_status=%s body_excerpt=%s',
        attempt,
        response.status_code,
        _safe_upstream_excerpt(response, api_key),
    )


def _parse_directions_response(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        raise ProviderMalformedResponseError('OpenRouteService returned an invalid route response.')

    if payload.get('type') == 'FeatureCollection':
        features = payload.get('features')
        if not isinstance(features, list):
            raise ProviderMalformedResponseError('OpenRouteService returned an invalid route response.')
        candidates = [
            {
                'geometry': feature.get('geometry'),
                'summary': (feature.get('properties') or {}).get('summary')
                    or feature.get('properties')
                    or {},
            }
            for feature in features
            if isinstance(feature, dict)
            and isinstance(feature.get('properties') or {}, dict)
        ]
    else:
        candidates = payload.get('routes')
        if not isinstance(candidates, list):
            raise ProviderMalformedResponseError('OpenRouteService returned an invalid route response.')

    normalized = []
    for candidate in candidates:
        try:
            geometry = candidate.get('geometry')
            coordinates = geometry.get('coordinates') if isinstance(geometry, dict) else None
            summary = candidate.get('summary') or {}
            distance_meters = float(summary['distance'])
            duration_seconds = float(summary['duration'])
            if not isinstance(coordinates, list) or not coordinates:
                continue
            route_geometry = []
            for coordinate in coordinates:
                longitude, latitude = float(coordinate[0]), float(coordinate[1])
                if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                    raise ValueError('Coordinate out of range.')
                route_geometry.append({'lat': latitude, 'lon': longitude})
            if len(route_geometry) < 2 or distance_meters <= 0 or duration_seconds <= 0:
                continue
        except (KeyError, IndexError, TypeError, ValueError):
            continue
        normalized.append({
            'distance_meters': distance_meters,
            'duration_seconds': duration_seconds,
            'geometry': route_geometry,
        })

    if not normalized:
        raise ProviderMalformedResponseError('OpenRouteService returned no valid route geometry.')
    return normalized[:3]


def _post_directions(api_key: str, body: dict[str, Any], attempt: str) -> requests.Response:
    started = time.perf_counter()
    try:
        response = _http_session().post(
            'https://api.openrouteservice.org/v2/directions/driving-car/geojson',
            headers={'Authorization': api_key},
            json=body,
            timeout=_provider_timeout(getattr(settings, 'ORS_TIMEOUT_SECONDS', 15)),
        )
    except requests.Timeout as exc:
        logger.info(
            'provider_request provider=openrouteservice operation=directions attempt=%s duration_ms=%.1f outcome=timeout',
            attempt,
            (time.perf_counter() - started) * 1000,
        )
        raise ProviderTimeoutError('OpenRouteService route generation timed out.') from exc
    except requests.RequestException as exc:
        logger.info(
            'provider_request provider=openrouteservice operation=directions attempt=%s duration_ms=%.1f outcome=network_error',
            attempt,
            (time.perf_counter() - started) * 1000,
        )
        raise ProviderError('Could not connect to OpenRouteService route generation.') from exc

    logger.info(
        'provider_request provider=openrouteservice operation=directions attempt=%s duration_ms=%.1f status=%d',
        attempt,
        (time.perf_counter() - started) * 1000,
        response.status_code,
    )
    if response.status_code in {401, 403}:
        _log_directions_failure(response, api_key, attempt)
        raise ProviderAuthenticationError('OpenRouteService rejected the routing credentials.')
    if response.status_code == 429:
        _log_directions_failure(response, api_key, attempt)
        raise ProviderRateLimitError('OpenRouteService rate limit reached. Please try again shortly.')
    if not response.ok:
        _log_directions_failure(response, api_key, attempt)
    return response


def _great_circle_distance_meters(first: tuple[float, float], second: tuple[float, float]) -> float:
    from math import asin, cos, radians, sin, sqrt

    lat1, lon1 = first
    lat2, lon2 = second
    delta_lat = radians(lat2 - lat1)
    delta_lon = radians(lon2 - lon1)
    haversine = sin(delta_lat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(delta_lon / 2) ** 2
    return 2 * 6371000 * asin(sqrt(haversine))


def _standard_route(api_key: str, base_body: dict[str, Any]) -> dict[str, Any]:
    standard_response = _post_directions(api_key, base_body, 'standard')
    if standard_response.status_code == 404:
        logger.warning('OpenRouteService could not snap a geocoded waypoint within the default radius; retrying standard directions with a 2 km radius.')
        standard_body = {**base_body, 'radiuses': [2000, 2000]}
        standard_response = _post_directions(api_key, standard_body, 'standard-expanded-radius')
    if not standard_response.ok:
        if standard_response.status_code >= 500:
            raise ProviderError('OpenRouteService is currently unavailable. Please retry the request.')
        raise ProviderError('OpenRouteService could not generate a route for these locations. Check the locations and try again.')
    try:
        routes = _parse_directions_response(standard_response.json())
    except (ValueError, ProviderMalformedResponseError) as exc:
        logger.warning('OpenRouteService standard directions response was malformed.')
        raise ProviderMalformedResponseError('OpenRouteService returned an invalid route response.') from exc
    return {
        'routes': routes[:1],
        'warnings': ['OpenRouteService did not provide alternatives for this trip; showing its standard route.'],
    }


def build_route_geometry(origin: tuple[float, float], destination: tuple[float, float]) -> dict[str, Any]:
    cache_key = _cache_key('directions', [round(origin[0], 5), round(origin[1], 5), round(destination[0], 5), round(destination[1], 5)])
    cached = cache.get(cache_key)
    if cached is not None:
        logger.info('provider_cache provider=openrouteservice operation=directions result=hit')
        return cached
    api_key = _require_api_key()
    base_body = {
        'coordinates': [[origin[1], origin[0]], [destination[1], destination[0]]],
    }
    if _great_circle_distance_meters(origin, destination) > 100_000:
        result = _standard_route(api_key, base_body)
        cache.set(cache_key, result, timeout=900)
        return result

    alternative_body = {
        **base_body,
        'alternative_routes': {
            'target_count': 3,
            'weight_factor': 1.4,
            'share_factor': 0.6,
        },
    }

    alternatives_response = _post_directions(api_key, alternative_body, 'alternative')
    if alternatives_response.ok:
        try:
            routes = _parse_directions_response(alternatives_response.json())
        except (ValueError, ProviderMalformedResponseError):
            logger.warning('OpenRouteService alternatives response was malformed; retrying standard directions.')
            routes = []
        if routes:
            result = {'routes': routes, 'warnings': []}
            cache.set(cache_key, result, timeout=900)
            return result
    elif alternatives_response.status_code not in {400, 404, 406, 422}:
        raise ProviderError('OpenRouteService could not generate route alternatives. Please retry the request.')

    result = _standard_route(api_key, base_body)
    cache.set(cache_key, result, timeout=900)
    return result


def fetch_weather_batch(
    coordinates: list[tuple[float, float]],
    forecast_offset_hours: int,
) -> dict[str, dict[str, Any]]:
    if forecast_offset_hours < 0 or forecast_offset_hours > 48:
        raise ProviderError('Forecast offset must be between 0 and 48 hours inclusive.')
    unique_coordinates = {
        _coordinate_key(latitude, longitude): (latitude, longitude)
        for latitude, longitude in coordinates
    }
    forecast_hours = max(48, int(forecast_offset_hours) + 48)
    weather_by_key: dict[str, dict[str, Any]] = {}
    missing: list[tuple[str, tuple[float, float]]] = []
    for key, coordinate in unique_coordinates.items():
        cache_key = _cache_key('weather', [key, forecast_hours])
        cached = cache.get(cache_key)
        if cached is None:
            missing.append((key, coordinate))
        else:
            weather_by_key[key] = cached

    chunks = [missing[index:index + _WEATHER_BATCH_SIZE] for index in range(0, len(missing), _WEATHER_BATCH_SIZE)]
    started = time.perf_counter()
    logger.info(
        'weather_batch locations=%d cache_hits=%d requests=%d',
        len(unique_coordinates),
        len(weather_by_key),
        len(chunks),
    )

    def fetch_chunk(chunk: list[tuple[str, tuple[float, float]]]):
        data = _fetch_weather_payload([coordinate for _, coordinate in chunk], forecast_hours)
        return chunk, data

    if len(chunks) == 1:
        results = [fetch_chunk(chunks[0])]
    elif chunks:
        results = []
        with ThreadPoolExecutor(max_workers=min(3, len(chunks))) as executor:
            futures = [executor.submit(fetch_chunk, chunk) for chunk in chunks]
            for future in as_completed(futures):
                results.append(future.result())
    else:
        results = []

    for chunk, payloads in results:
        for (key, _), payload in zip(chunk, payloads):
            hourly = payload.get('hourly') or {}
            times = hourly.get('time') or []
            if not isinstance(times, list):
                raise ProviderMalformedResponseError('Open-Meteo returned invalid hourly weather data.')
            weather = {'payload': payload, 'forecast_times': times}
            weather_by_key[key] = weather
            cache.set(_cache_key('weather', [key, forecast_hours]), weather, timeout=_WEATHER_CACHE_SECONDS)

    logger.info(
        'weather_batch_complete locations=%d cache_hits=%d requests=%d duration_ms=%.1f',
        len(unique_coordinates),
        len(unique_coordinates) - len(missing),
        len(chunks),
        (time.perf_counter() - started) * 1000,
    )
    return weather_by_key


def fetch_weather(latitude: float, longitude: float, arrival_dt, forecast_offset_hours: int) -> dict[str, Any]:
    return fetch_weather_batch([(latitude, longitude)], forecast_offset_hours)[_coordinate_key(latitude, longitude)]
