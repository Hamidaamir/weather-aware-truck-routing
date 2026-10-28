from unittest.mock import patch

from django.test import SimpleTestCase
from rest_framework.test import APIClient


class ApiTests(SimpleTestCase):
    def setUp(self):
        self.client = APIClient()

    def test_health_endpoint(self):
        response = self.client.get('/api/health/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'ok')

    @patch('api.views.search_locations')
    def test_geocode_success_returns_structured_suggestions(self, search_locations_mock):
        suggestions = [{
            'id': 'place.123',
            'primary': 'Dallas',
            'secondary': 'Texas, United States',
            'label': 'Dallas, Texas, United States',
            'lat': 32.7767,
            'lon': -96.797,
        }]
        search_locations_mock.return_value = suggestions
        response = self.client.get('/api/geocode/', {'q': 'Dallas'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['suggestions'], suggestions)
        search_locations_mock.assert_called_once_with('Dallas')

    def test_geocode_rejects_short_queries(self):
        response = self.client.get('/api/geocode/', {'q': 'ab'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('errors', response.json())

    @patch('api.views.search_locations')
    def test_geocode_rate_limit_is_recoverable(self, search_locations_mock):
        from services.providers import ProviderRateLimitError
        search_locations_mock.side_effect = ProviderRateLimitError('Rate limited.')
        response = self.client.get('/api/geocode/', {'q': 'Dallas'})
        self.assertEqual(response.status_code, 429)
        self.assertIn('message', response.json())

    @patch('api.views.search_locations')
    def test_geocode_missing_configuration_is_reported(self, search_locations_mock):
        from services.providers import ProviderConfigError
        search_locations_mock.side_effect = ProviderConfigError('API key missing.')
        response = self.client.get('/api/geocode/', {'q': 'Dallas'})
        self.assertEqual(response.status_code, 503)

    @patch('api.views.search_locations')
    def test_geocode_timeout_is_reported(self, search_locations_mock):
        from services.providers import ProviderTimeoutError
        search_locations_mock.side_effect = ProviderTimeoutError('Timed out.')
        response = self.client.get('/api/geocode/', {'q': 'Dallas'})
        self.assertEqual(response.status_code, 504)

    @patch('api.views.generate_plan')
    def test_route_plan_success(self, generate_plan_mock):
        generate_plan_mock.return_value = {
            'origin': {'name': 'Dallas, TX', 'lat': 32.7767, 'lon': -96.7970},
            'destination': {'name': 'El Paso, TX', 'lat': 31.7619, 'lon': -106.4850},
            'routes': [],
            'recommended_route': None,
            'warnings': [],
            'metadata': {},
        }
        response = self.client.post('/api/route-plan/', {
            'origin': 'Dallas, TX',
            'destination': 'El Paso, TX',
            'departure_datetime': '2026-10-28T08:00:00-05:00',
            'load_weight_lbs': 35000,
            'checkpoint_interval_miles': 25,
            'forecast_offset_hours': 0,
        }, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertIn('routes', response.json())

    def test_route_plan_validation_error(self):
        response = self.client.post('/api/route-plan/', {
            'origin': 'Dallas, TX',
            'destination': 'Dallas, TX',
            'departure_datetime': '2026-10-28T08:00:00-05:00',
            'load_weight_lbs': 0,
            'checkpoint_interval_miles': 5,
            'forecast_offset_hours': -1,
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('errors', response.json())

    @patch('api.views.generate_plan')
    def test_route_plan_provider_missing(self, generate_plan_mock):
        from services.providers import ProviderConfigError
        generate_plan_mock.side_effect = ProviderConfigError('API key missing')
        response = self.client.post('/api/route-plan/', {
            'origin': 'Dallas, TX',
            'destination': 'El Paso, TX',
            'departure_datetime': '2026-10-28T08:00:00-05:00',
            'load_weight_lbs': 35000,
            'checkpoint_interval_miles': 25,
            'forecast_offset_hours': 0,
        }, format='json')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['message'], 'API key missing')

    def test_route_plan_provider_failures_have_recoverable_statuses(self):
        from services.providers import (
            ProviderAuthenticationError,
            ProviderRateLimitError,
            ProviderTimeoutError,
        )

        payload = {
            'origin': 'Dallas, TX',
            'destination': 'El Paso, TX',
            'departure_datetime': '2026-10-28T08:00:00-05:00',
            'load_weight_lbs': 35000,
            'checkpoint_interval_miles': 25,
            'forecast_offset_hours': 0,
        }
        cases = (
            (ProviderAuthenticationError('Credentials rejected.'), 503),
            (ProviderRateLimitError('Rate limited.'), 429),
            (ProviderTimeoutError('Timed out.'), 504),
        )
        for error, expected_status in cases:
            with self.subTest(expected_status=expected_status):
                with patch('api.views.generate_plan', side_effect=error):
                    response = self.client.post('/api/route-plan/', payload, format='json')
                self.assertEqual(response.status_code, expected_status)
                self.assertIn('message', response.json())
