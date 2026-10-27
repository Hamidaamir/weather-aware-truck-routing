from __future__ import annotations

from typing import Any

RISK_ORDER = {
    'low': 1,
    'moderate': 2,
    'high': 3,
    'severe': 4,
    'no_travel': 5,
    'unknown': 0,
}


def classify_wind(wind_mph: float | None, load_weight_lbs: float | None = None) -> str:
    if wind_mph is None:
        return 'unknown'
    if wind_mph >= 55:
        return 'no_travel'
    if 45 <= wind_mph < 55:
        if load_weight_lbs is not None and load_weight_lbs > 30000:
            return 'no_travel'
        return 'severe'
    if 35 <= wind_mph < 45:
        if load_weight_lbs is not None and load_weight_lbs > 40000:
            return 'severe'
        return 'high'
    if 25 <= wind_mph < 35:
        return 'moderate'
    return 'low'


def classify_rain(rain_in_hr: float | None) -> str:
    if rain_in_hr is None:
        return 'unknown'
    if rain_in_hr < 0.10:
        return 'low'
    if 0.10 <= rain_in_hr < 0.25:
        return 'moderate'
    if 0.25 <= rain_in_hr < 0.50:
        return 'high'
    if 0.50 <= rain_in_hr <= 1.00:
        return 'severe'
    return 'no_travel'


def classify_snow(snow_in_hr: float | None) -> str:
    if snow_in_hr is None:
        return 'unknown'
    if snow_in_hr < 0.5:
        return 'low'
    if 0.5 <= snow_in_hr < 1.0:
        return 'moderate'
    if 1.0 <= snow_in_hr < 2.0:
        return 'high'
    if 2.0 <= snow_in_hr <= 3.0:
        return 'severe'
    return 'no_travel'


def highest_risk(*levels: str | None) -> str:
    valid_levels = [level for level in levels if level not in (None, '', 'unknown')]
    if not valid_levels:
        return 'unknown'
    return max(valid_levels, key=lambda level: RISK_ORDER.get(level, -1))


def aggregate_checkpoint_risk(wind_level: str | None, rain_level: str | None, snow_level: str | None) -> str:
    return highest_risk(wind_level, rain_level, snow_level)


def risk_score(risk_level: str | None) -> int:
    if risk_level is None:
        return 0
    return RISK_ORDER.get(risk_level, 0)


def evaluate_route_eligibility(routes: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    confirmed_no_travel = [route for route in routes if route.get('has_confirmed_no_travel')]
    if confirmed_no_travel and any(not route.get('has_confirmed_no_travel') for route in routes):
        for route in routes:
            route['eligible_for_recommendation'] = not route.get('has_confirmed_no_travel')
        return routes, {'status': 'some_routes_ineligible'}
    if confirmed_no_travel and len(confirmed_no_travel) == len(routes):
        for route in routes:
            route['eligible_for_recommendation'] = False
        return routes, {'status': 'all_routes_blocked'}
    for route in routes:
        route['eligible_for_recommendation'] = True
    return routes, {'status': 'eligible'}


def rank_routes(routes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    adjusted = [route.copy() for route in routes]
    for route in adjusted:
        route['weather_coverage_ok'] = route.get('weather_coverage_percent', 100) >= 80
        route['has_confirmed_no_travel'] = route.get('no_travel_checkpoints', 0) > 0 or route.get('no_travel_miles', 0) > 0
    adjusted, _ = evaluate_route_eligibility(adjusted)

    def sort_key(route: dict[str, Any]):
        return (
            route.get('severe_miles', 0),
            route.get('high_miles', 0),
            route.get('average_risk_score', 0),
            route.get('estimated_travel_time_minutes', 0),
        )

    ranked = sorted(adjusted, key=sort_key)
    for index, route in enumerate(ranked, start=1):
        route['rank'] = index
        route['recommended'] = bool(route.get('eligible_for_recommendation') and index == 1)
    return ranked
