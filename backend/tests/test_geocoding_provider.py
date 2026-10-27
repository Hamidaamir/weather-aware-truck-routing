from unittest.mock import Mock, patch

import requests
from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from services.providers import ProviderRateLimitError, ProviderTimeoutError, search_locations


class GeocodingProviderTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    @override_settings(ORS_API_KEY='test-key', ORS_TIMEOUT_SECONDS=5)
    @patch('services.providers._http_session')
    def test_search_parses_place_suggestions_and_uses_us_boundary(self, session_mock):
        get_mock = session_mock.return_value.get
        response = Mock()
        response.status_code = 200
        response.ok = True
        response.json.return_value = {
            'features': [
                {
                    'geometry': {'coordinates': [-96.797, 32.7767]},
                    'properties': {
                        'gid': 'whosonfirst:locality:123',
                        'name': 'Dallas',
                        'region': 'Texas',
                        'country': 'United States',
                        'label': 'Dallas, Texas, United States',
                    },
                },
                {
                    'geometry': {'coordinates': ['invalid', 32]},
                    'properties': {'name': 'Invalid location', 'label': 'Invalid location'},
                },
            ],
        }
        get_mock.return_value = response

        suggestions = search_locations('Dallas')

        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0]['primary'], 'Dallas')
        self.assertEqual(suggestions[0]['secondary'], 'Texas, United States')
        self.assertEqual(suggestions[0]['lat'], 32.7767)
        self.assertEqual(suggestions[0]['lon'], -96.797)
        self.assertEqual(get_mock.call_args.kwargs['params']['boundary.country'], 'USA')
        self.assertEqual(get_mock.call_args.kwargs['timeout'], (3, 5))

    @override_settings(ORS_API_KEY='test-key')
    @patch('services.providers._http_session')
    def test_search_filters_foreign_results_and_deduplicates_places(self, session_mock):
        get_mock = session_mock.return_value.get
        response = Mock()
        response.status_code = 200
        response.ok = True
        dallas_feature = {
            'geometry': {'coordinates': [-96.797, 32.7767]},
            'properties': {
                'gid': 'whosonfirst:locality:123',
                'name': 'Dallas',
                'region': 'Texas',
                'country': 'United States',
                'country_a': 'USA',
                'label': 'Dallas, Texas, United States',
            },
        }
        response.json.return_value = {
            'features': [
                dallas_feature,
                {**dallas_feature, 'properties': {**dallas_feature['properties'], 'gid': 'duplicate'}},
                {
                    'geometry': {'coordinates': [-3.1883, 55.9533]},
                    'properties': {
                        'name': 'Edinburgh',
                        'country': 'United Kingdom',
                        'country_a': 'GBR',
                        'label': 'Edinburgh, Scotland, United Kingdom',
                    },
                },
            ],
        }
        get_mock.return_value = response

        suggestions = search_locations('Dallas')

        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0]['primary'], 'Dallas')

    @override_settings(ORS_API_KEY='test-key')
    @patch('services.providers._http_session')
    def test_search_caches_normalized_queries(self, session_mock):
        get_mock = session_mock.return_value.get
        response = Mock()
        response.status_code = 200
        response.ok = True
        response.json.return_value = {'features': []}
        get_mock.return_value = response

        first = search_locations('Dallas')
        second = search_locations(' dAlLaS ')

        self.assertEqual(first, second)
        get_mock.assert_called_once()

    @override_settings(ORS_API_KEY='test-key')
    @patch('services.providers._http_session')
    def test_search_translates_timeouts(self, session_mock):
        get_mock = session_mock.return_value.get
        get_mock.side_effect = requests.Timeout()
        with self.assertRaises(ProviderTimeoutError):
            search_locations('Dallas')

    @override_settings(ORS_API_KEY='test-key')
    @patch('services.providers._http_session')
    def test_search_translates_rate_limits(self, session_mock):
        get_mock = session_mock.return_value.get
        response = Mock()
        response.status_code = 429
        response.ok = False
        get_mock.return_value = response
        with self.assertRaises(ProviderRateLimitError):
            search_locations('Dallas')
