from datetime import datetime
import threading
import time
from unittest.mock import Mock, patch

import requests
from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from services.weather_service import determine_weather_for_checkpoint


class WeatherServiceTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    @patch('services.weather_service.fetch_weather')
    def test_naive_utc_forecast_times_compare_to_aware_departure(self, fetch_mock):
        fetch_mock.return_value = {
            'payload': {
                'hourly': {
                    'time': ['2026-10-28T12:00', '2026-10-28T13:00', '2026-10-28T14:00'],
                    'wind_speed_10m': [1, 10, 20],
                    'rain': [0, 2, 4],
                    'snowfall': [0, 1, 2],
                },
            },
            'forecast_times': [],
        }
        departure = datetime.fromisoformat('2026-10-28T08:00:00-05:00')
        checkpoint = {
            'lat': 32.7,
            'lon': -96.8,
            'arrival': departure,
        }

        result = determine_weather_for_checkpoint(checkpoint, departure, 0)

        self.assertFalse(result['missing'])
        self.assertEqual(result['forecast_time'], '2026-10-28T13:00:00+00:00')
        self.assertAlmostEqual(result['wind_mph'], 10 * 0.621371)

    @override_settings(WEATHER_TIMEOUT_SECONDS=5)
    @patch('services.providers._http_session')
    def test_weather_requests_use_utc_and_batched_coordinates(self, session_mock):
        get_mock = session_mock.return_value.get
        response = Mock()
        response.status_code = 200
        response.ok = True
        response.json.return_value = [
            {'hourly': {'time': ['2026-10-28T13:00']}},
            {'hourly': {'time': ['2026-10-28T13:00']}},
        ]
        get_mock.return_value = response

        from services.providers import fetch_weather_batch
        fetched = fetch_weather_batch([(32.7, -96.8), (31.8, -106.4)], 0)

        self.assertEqual(len(fetched), 2)
        self.assertEqual(get_mock.call_args.kwargs['params']['latitude'], '32.70000,31.80000')
        self.assertEqual(get_mock.call_args.kwargs['params']['longitude'], '-96.80000,-106.40000')
        self.assertEqual(get_mock.call_args.kwargs['params']['timezone'], 'UTC')
        self.assertEqual(get_mock.call_args.kwargs['timeout'], (3, 5))

    @override_settings(ORS_API_KEY='test-key')
    @patch('services.providers._http_session')
    def test_weather_batch_deduplicates_coordinates_and_caches_forecasts(self, session_mock):
        get_mock = session_mock.return_value.get
        response = Mock()
        response.status_code = 200
        response.ok = True
        response.json.return_value = {'hourly': {
            'time': ['2026-10-28T13:00'],
            'wind_speed_10m': [0],
            'rain': [0],
            'snowfall': [0],
        }}
        get_mock.return_value = response
        from services.providers import fetch_weather_batch

        first = fetch_weather_batch([(32.7, -96.8), (32.7, -96.8)], 0)
        second = fetch_weather_batch([(32.7, -96.8)], 0)

        self.assertEqual(len(first), 1)
        self.assertEqual(first, second)
        get_mock.assert_called_once()

    @patch('services.weather_service.fetch_weather_batch')
    def test_batched_weather_maps_each_checkpoint_to_its_own_forecast(self, batch_mock):
        from services.weather_service import determine_weather_for_checkpoints

        departure = datetime.fromisoformat('2026-10-28T08:00:00-05:00')
        checkpoints = [
            {'lat': 32.7, 'lon': -96.8, 'arrival': departure, 'distance_miles': 0},
            {'lat': 31.8, 'lon': -106.4, 'arrival': departure.replace(hour=10), 'distance_miles': 100},
        ]
        batch_mock.return_value = {
            '32.70000,-96.80000': {'payload': {'hourly': {
                'time': ['2026-10-28T13:00', '2026-10-28T14:00', '2026-10-28T15:00', '2026-10-28T16:00', '2026-10-28T17:00', '2026-10-28T18:00'],
                'wind_speed_10m': [10, 20, 30, 40, 50, 60], 'rain': [1, 2, 3, 4, 5, 6], 'snowfall': [3, 4, 5, 6, 7, 8],
            }}},
            '31.80000,-106.40000': {'payload': {'hourly': {
                'time': ['2026-10-28T13:00', '2026-10-28T14:00', '2026-10-28T15:00', '2026-10-28T16:00', '2026-10-28T17:00', '2026-10-28T18:00'],
                'wind_speed_10m': [30, 40, 50, 60, 70, 80], 'rain': [5, 6, 7, 8, 9, 10], 'snowfall': [7, 8, 9, 10, 11, 12],
            }}},
        }

        results = determine_weather_for_checkpoints(checkpoints, departure, 3)

        self.assertEqual(len(results), 2)
        self.assertAlmostEqual(results[0]['wind_mph'], 40 * 0.621371)
        self.assertAlmostEqual(results[1]['wind_mph'], 80 * 0.621371)

    @patch('services.weather_service.fetch_weather')
    def test_zero_wind_is_valid_data_and_missing_values_are_unknown(self, fetch_mock):
        departure = datetime.fromisoformat('2026-10-28T13:00:00+00:00')
        checkpoint = {'lat': 32.7, 'lon': -96.8, 'arrival': departure}
        fetch_mock.return_value = {'payload': {'hourly': {
            'time': ['2026-10-28T13:00'],
            'wind_speed_10m': [0], 'rain': [0], 'snowfall': [0],
        }}}

        zero_forecast = determine_weather_for_checkpoint(checkpoint, departure, 0)

        self.assertFalse(zero_forecast['missing'])
        self.assertEqual(zero_forecast['wind_mph'], 0)
        fetch_mock.return_value = {'payload': {'hourly': {
            'time': ['2026-10-28T13:00'],
            'wind_speed_10m': [None], 'rain': [None], 'snowfall': [None],
        }}}

        missing_forecast = determine_weather_for_checkpoint(checkpoint, departure, 0)

        self.assertTrue(missing_forecast['missing'])
        self.assertIsNone(missing_forecast['wind_mph'])

    @patch('services.providers._WEATHER_BATCH_SIZE', 1)
    @patch('services.providers._http_session')
    def test_weather_chunks_run_with_bounded_concurrency_and_keep_coordinate_mapping(self, session_mock):
        from services.providers import fetch_weather_batch

        get_mock = session_mock.return_value.get
        active = 0
        maximum_active = 0
        completion_order = []
        lock = threading.Lock()

        def delayed_location_response(*args, **kwargs):
            nonlocal active, maximum_active
            with lock:
                active += 1
                maximum_active = max(maximum_active, active)
            latitude = float(kwargs['params']['latitude'])
            time.sleep(0.08 if latitude == 32.7 else 0.001)
            response = Mock()
            response.status_code = 200
            response.ok = True
            response.json.return_value = {'hourly': {
                'time': ['2026-10-28T13:00'],
                'wind_speed_10m': [latitude],
                'rain': [0],
                'snowfall': [0],
            }}
            with lock:
                active -= 1
                completion_order.append(latitude)
            return response

        get_mock.side_effect = delayed_location_response
        coordinates = [(32.7, -96.8), (31.8, -106.4), (29.7, -95.3), (30.3, -97.7), (39.7, -86.2)]

        result = fetch_weather_batch(coordinates, 0)

        self.assertEqual(get_mock.call_count, 5)
        self.assertGreaterEqual(maximum_active, 2)
        self.assertLessEqual(maximum_active, 3)
        self.assertNotEqual(completion_order[0], coordinates[0][0])
        self.assertEqual(result['32.70000,-96.80000']['payload']['hourly']['wind_speed_10m'], [32.7])
        self.assertEqual(result['31.80000,-106.40000']['payload']['hourly']['wind_speed_10m'], [31.8])
        self.assertEqual(result['29.70000,-95.30000']['payload']['hourly']['wind_speed_10m'], [29.7])

    @patch('services.providers._WEATHER_CACHE_SECONDS', 0)
    @patch('services.providers._http_session')
    def test_expired_weather_cache_entries_are_fetched_again(self, session_mock):
        get_mock = session_mock.return_value.get
        response = Mock()
        response.status_code = 200
        response.ok = True
        response.json.return_value = {'hourly': {
            'time': ['2026-10-28T13:00'],
            'wind_speed_10m': [10], 'rain': [0], 'snowfall': [0],
        }}
        get_mock.return_value = response
        from services.providers import fetch_weather_batch

        fetch_weather_batch([(32.7, -96.8)], 0)
        fetch_weather_batch([(32.7, -96.8)], 0)

        self.assertEqual(get_mock.call_count, 2)

    @patch('services.providers._http_session')
    def test_weather_timeout_and_rate_limits_are_reported(self, session_mock):
        from services.providers import ProviderRateLimitError, ProviderTimeoutError, fetch_weather_batch

        get_mock = session_mock.return_value.get
        get_mock.side_effect = requests.Timeout()
        with self.assertRaises(ProviderTimeoutError):
            fetch_weather_batch([(32.7, -96.8)], 0)

        response = Mock()
        response.status_code = 429
        response.ok = False
        get_mock.side_effect = None
        get_mock.return_value = response
        with self.assertRaises(ProviderRateLimitError):
            fetch_weather_batch([(32.7, -96.8)], 0)
