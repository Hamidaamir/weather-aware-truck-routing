from __future__ import annotations

import math
from bisect import bisect_left
from datetime import datetime, timedelta, timezone
from typing import Any


def haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371000.0
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * radius * math.asin(math.sqrt(a))


def route_distance_meters(points: list[dict[str, float]]) -> list[float]:
    distances = [0.0]
    for index in range(1, len(points)):
        previous = points[index - 1]
        current = points[index]
        distances.append(distances[-1] + haversine_meters(previous['lat'], previous['lon'], current['lat'], current['lon']))
    return distances


def interpolate_point(
    points: list[dict[str, float]],
    segment_distance: float,
    cumulative_distances: list[float] | None = None,
) -> dict[str, float]:
    if not points:
        raise ValueError('No geometry points provided.')
    if len(points) == 1:
        return points[0]
    cumulative = cumulative_distances or route_distance_meters(points)
    if segment_distance <= 0:
        return points[0]
    if segment_distance >= cumulative[-1]:
        return points[-1]

    next_index = bisect_left(cumulative, segment_distance)
    previous_index = max(0, next_index - 1)
    segment = cumulative[next_index] - cumulative[previous_index]
    if segment == 0:
        return points[next_index]
    ratio = (segment_distance - cumulative[previous_index]) / segment
    previous = points[previous_index]
    current = points[next_index]
    return {
        'lat': previous['lat'] + (current['lat'] - previous['lat']) * ratio,
        'lon': previous['lon'] + (current['lon'] - previous['lon']) * ratio,
    }


def build_checkpoints(route_geometry: list[dict[str, float]], interval_miles: int, departure: datetime, duration_seconds: float) -> list[dict[str, Any]]:
    points = route_geometry[:]
    cumulative = route_distance_meters(points)
    total_distance_m = cumulative[-1]
    interval_m = interval_miles * 1609.344
    checkpoints: list[dict[str, Any]] = []
    seen = set()
    for target in [0.0] + [interval_m * step for step in range(1, int(total_distance_m // interval_m) + 2)]:
        if target > total_distance_m:
            continue
        point = interpolate_point(points, target, cumulative)
        key = round(point['lat'], 7), round(point['lon'], 7)
        if key in seen:
            continue
        seen.add(key)
        elapsed = (target / total_distance_m) * duration_seconds if total_distance_m else 0.0
        arrival = departure + timedelta(seconds=elapsed)
        checkpoints.append({
            'distance_meters': float(target),
            'distance_miles': target / 1609.344,
            'lat': float(point['lat']),
            'lon': float(point['lon']),
            'eta': arrival.isoformat(),
            'source_distance': target,
        })
    if not checkpoints or checkpoints[-1]['distance_meters'] != total_distance_m:
        last = points[-1]
        checkpoints.append({
            'distance_meters': float(total_distance_m),
            'distance_miles': total_distance_m / 1609.344,
            'lat': float(last['lat']),
            'lon': float(last['lon']),
            'eta': (departure + timedelta(seconds=duration_seconds)).isoformat(),
            'source_distance': float(total_distance_m),
        })
    checkpoints.sort(key=lambda item: item['distance_meters'])
    cleaned: list[dict[str, Any]] = []
    previous = None
    for checkpoint in checkpoints:
        if previous is not None and abs(checkpoint['distance_meters'] - previous['distance_meters']) < 0.1:
            continue
        cleaned.append(checkpoint)
        previous = checkpoint
    return cleaned
