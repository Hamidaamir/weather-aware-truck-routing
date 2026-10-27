from datetime import datetime, timedelta
from unittest.mock import patch

from django.test import SimpleTestCase

from services.checkpoints import route_distance_meters
from services.route_service import generate_plan


class RouteServiceTests(SimpleTestCase):
    def test_batches_weather_for_all_alternatives_and_preserves_safety_ranking(self):
        departure = datetime.fromisoformat('2026-10-28T08:00:00-05:00')
        route_geometry = lambda latitude, endpoint_lon: [
            {'lat': latitude, 'lon': -96.8},
            {'lat': latitude, 'lon': endpoint_lon},
        ]
        route_payload = {
            'warnings': [],
            'routes': [
                {
                    'distance_meters': 321 * 1609.344,
                    'duration_seconds': 6 * 3600,
                    'geometry': route_geometry(32.0, -91.0),
                },
                {
                    'distance_meters': 330 * 1609.344,
                    'duration_seconds': 6.5 * 3600,
                    'geometry': route_geometry(34.0, -90.8),
                },
            ],
        }

        def weather_for_checkpoints(checkpoints, route_departure, offset):
            self.assertEqual(route_departure, departure)
            self.assertEqual(offset, 3)
            forecasts = []
            for checkpoint in checkpoints:
                wind = 50 if checkpoint['lat'] < 33 else 10
                forecasts.append({
                    'missing': False,
                    'wind_mph': wind,
                    'rain_in_hr': 0,
                    'snow_in_hr': 0,
                })
            return forecasts

        with (
            patch('services.route_service.geocode_location', side_effect=[
                {'name': 'Dallas', 'lat': 32.7, 'lon': -96.8},
                {'name': 'El Paso', 'lat': 31.8, 'lon': -106.4},
            ]),
            patch('services.route_service.build_route_geometry', return_value=route_payload) as route_mock,
            patch('services.route_service.determine_weather_for_checkpoints', side_effect=weather_for_checkpoints) as weather_mock,
        ):
            result = generate_plan('Dallas', 'El Paso', departure, 35000, 25, 3)

        route_mock.assert_called_once()
        weather_mock.assert_called_once()
        self.assertEqual(len(result['routes']), 2)
        unsafe = next(route for route in result['routes'] if route['name'] == 'Alternative 1')
        safe = next(route for route in result['routes'] if route['name'] == 'Alternative 2')
        self.assertTrue(unsafe['has_confirmed_no_travel'])
        self.assertFalse(unsafe['eligible_for_recommendation'])
        self.assertTrue(safe['recommended'])
        self.assertEqual(
            [round(checkpoint['distance_miles']) for checkpoint in safe['checkpoints'][:-1]],
            [0, 25, 50, 75, 100, 125, 150, 175, 200, 225, 250, 275, 300, 325],
        )
        safe_geometry_distance = route_distance_meters(route_geometry(34.0, -90.8))[-1]
        expected_checkpoint_eta = departure + timedelta(
            seconds=(25 * 1609.344 / safe_geometry_distance) * 6.5 * 3600,
        )
        self.assertEqual(safe['checkpoints'][1]['eta'], expected_checkpoint_eta.isoformat())
        self.assertEqual(safe['checkpoints'][0]['eta'], departure.isoformat())
        self.assertEqual(safe['checkpoints'][-1]['eta'], (departure.replace(hour=14, minute=30)).isoformat())

    def test_missing_weather_is_unknown_and_does_not_count_as_low_coverage(self):
        departure = datetime.fromisoformat('2026-10-28T08:00:00-05:00')
        route_payload = {
            'warnings': [],
            'routes': [{
                'distance_meters': 10 * 1609.344,
                'duration_seconds': 3600,
                'geometry': [{'lat': 32.7, 'lon': -96.8}, {'lat': 32.7, 'lon': -96.6}],
            }],
        }
        with (
            patch('services.route_service.geocode_location', side_effect=[
                {'name': 'A', 'lat': 32.7, 'lon': -96.8},
                {'name': 'B', 'lat': 32.7, 'lon': -96.6},
            ]),
            patch('services.route_service.build_route_geometry', return_value=route_payload),
            patch(
                'services.route_service.determine_weather_for_checkpoints',
                side_effect=lambda checkpoints, _departure, _offset: [
                    {'missing': True, 'wind_mph': None, 'rain_in_hr': None, 'snow_in_hr': None}
                    for _ in checkpoints
                ],
            ),
        ):
            result = generate_plan('A', 'B', departure, 35000, 10, 0)

        route = result['routes'][0]
        self.assertEqual(route['weather_coverage_percent'], 0)
        self.assertEqual(route['checkpoints'][0]['risk'], 'unknown')
        self.assertEqual(route['checkpoints'][0]['wind_risk'], 'unknown')
