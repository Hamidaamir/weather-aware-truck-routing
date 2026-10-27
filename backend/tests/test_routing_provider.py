from unittest.mock import Mock, patch

import requests
from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from services.providers import (
    ProviderAuthenticationError,
    ProviderError,
    ProviderMalformedResponseError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    build_route_geometry,
)


ORS_DIRECTIONS_URL = 'https://api.openrouteservice.org/v2/directions/driving-car/geojson'


def response(status_code, payload=None, text=''):
    result = Mock()
    result.status_code = status_code
    result.ok = 200 <= status_code < 300
    result.text = text
    result.json.return_value = payload
    return result


def geojson_route(distance=100000, duration=3600, coordinates=None):
    return {
        'type': 'Feature',
        'geometry': {
            'type': 'LineString',
            'coordinates': coordinates or [[-96.8, 32.7], [-98.0, 32.0]],
        },
        'properties': {'summary': {'distance': distance, 'duration': duration}},
    }


class RoutingProviderTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    @override_settings(ORS_API_KEY='server-only-test-key', ORS_TIMEOUT_SECONDS=7)
    @patch('services.providers._http_session')
    def test_correct_directions_endpoint_auth_and_alternatives_body(self, session_mock):
        post_mock = session_mock.return_value.post
        post_mock.return_value = response(200, {
            'type': 'FeatureCollection',
            'features': [
                geojson_route(100000),
                geojson_route(105000, 3700, [[-96.8, 32.7], [-97.0, 32.5]]),
                geojson_route(110000, 3900, [[-96.8, 32.7], [-97.1, 32.4]]),
            ],
        })

        result = build_route_geometry((32.7, -96.8), (32.8, -96.6))

        self.assertEqual(len(result['routes']), 3)
        self.assertEqual(result['routes'][0]['geometry'][0], {'lat': 32.7, 'lon': -96.8})
        args = post_mock.call_args
        self.assertEqual(args.args[0], ORS_DIRECTIONS_URL)
        self.assertEqual(args.kwargs['headers'], {'Authorization': 'server-only-test-key'})
        self.assertNotIn('Accept', args.kwargs['headers'])
        self.assertEqual(args.kwargs['timeout'], (3, 7))
        self.assertEqual(args.kwargs['json']['alternative_routes']['target_count'], 3)
        self.assertNotIn('alternative', args.kwargs['json'].get('options', {}))

    @override_settings(ORS_API_KEY='test-key')
    @patch('services.providers._http_session')
    def test_falls_back_to_real_standard_route_when_alternatives_are_rejected(self, session_mock):
        post_mock = session_mock.return_value.post
        post_mock.side_effect = [
            response(400, text='Alternative routes exceed allowed distance.'),
            response(200, {
                'type': 'FeatureCollection',
                'features': [geojson_route()],
            }),
        ]

        result = build_route_geometry((32.7, -96.8), (32.8, -96.6))

        self.assertEqual(len(result['routes']), 1)
        self.assertIn('standard route', result['warnings'][0])
        self.assertIn('alternative_routes', post_mock.call_args_list[0].kwargs['json'])
        self.assertNotIn('alternative_routes', post_mock.call_args_list[1].kwargs['json'])

    @override_settings(ORS_API_KEY='test-key')
    @patch('services.providers._http_session')
    def test_falls_back_when_alternatives_return_no_valid_geometry(self, session_mock):
        post_mock = session_mock.return_value.post
        post_mock.side_effect = [
            response(200, {'type': 'FeatureCollection', 'features': []}),
            response(200, {
                'type': 'FeatureCollection',
                'features': [geojson_route()],
            }),
        ]

        result = build_route_geometry((32.7, -96.8), (32.8, -96.6))

        self.assertEqual(len(result['routes']), 1)
        self.assertEqual(post_mock.call_count, 2)

    @override_settings(ORS_API_KEY='test-key')
    @patch('services.providers._http_session')
    def test_skips_long_distance_alternatives_and_retries_with_larger_snap_radius(self, session_mock):
        post_mock = session_mock.return_value.post
        post_mock.side_effect = [
            response(404, text='No routable point within 350 meters.'),
            response(200, {
                'type': 'FeatureCollection',
                'features': [geojson_route()],
            }),
        ]

        result = build_route_geometry((32.7, -96.8), (31.8, -106.49))

        self.assertEqual(len(result['routes']), 1)
        self.assertEqual(post_mock.call_count, 2)
        self.assertNotIn('alternative_routes', post_mock.call_args_list[0].kwargs['json'])
        self.assertEqual(post_mock.call_args_list[1].kwargs['json']['radiuses'], [2000, 2000])

    @override_settings(ORS_API_KEY='test-key')
    @patch('services.providers._http_session')
    def test_does_not_request_alternatives_when_straight_line_exceeds_provider_limit(self, session_mock):
        post_mock = session_mock.return_value.post
        post_mock.return_value = response(200, {
            'type': 'FeatureCollection',
            'features': [geojson_route()],
        })

        result = build_route_geometry((32.7, -96.8), (31.7, -106.4))

        self.assertEqual(len(result['routes']), 1)
        self.assertEqual(post_mock.call_count, 1)
        self.assertNotIn('alternative_routes', post_mock.call_args.kwargs['json'])

    @override_settings(ORS_API_KEY='test-key')
    @patch('services.providers._http_session')
    def test_caches_successful_route_provider_results(self, session_mock):
        post_mock = session_mock.return_value.post
        post_mock.return_value = response(200, {
            'type': 'FeatureCollection',
            'features': [geojson_route()],
        })

        first = build_route_geometry((32.7, -96.8), (31.7, -106.4))
        second = build_route_geometry((32.7, -96.8), (31.7, -106.4))

        self.assertEqual(first, second)
        post_mock.assert_called_once()

    @override_settings(ORS_API_KEY='test-key')
    @patch('services.providers._http_session')
    def test_authentication_error_is_not_retried(self, session_mock):
        post_mock = session_mock.return_value.post
        post_mock.return_value = response(401, text='unauthorized')
        with self.assertRaises(ProviderAuthenticationError):
            build_route_geometry((32.7, -96.8), (32.8, -96.6))
        post_mock.assert_called_once()

    @override_settings(ORS_API_KEY='test-key')
    @patch('services.providers._http_session')
    def test_rate_limit_is_not_retried(self, session_mock):
        post_mock = session_mock.return_value.post
        post_mock.return_value = response(429, text='rate limit')
        with self.assertRaises(ProviderRateLimitError):
            build_route_geometry((32.7, -96.8), (32.8, -96.6))
        post_mock.assert_called_once()

    @override_settings(ORS_API_KEY='test-key')
    @patch('services.providers._http_session')
    def test_timeout_is_reported_without_retry(self, session_mock):
        post_mock = session_mock.return_value.post
        post_mock.side_effect = requests.Timeout()
        with self.assertRaises(ProviderTimeoutError):
            build_route_geometry((32.7, -96.8), (32.8, -96.6))
        post_mock.assert_called_once()

    @override_settings(ORS_API_KEY='test-key')
    @patch('services.providers._http_session')
    def test_malformed_standard_route_response_is_reported(self, session_mock):
        post_mock = session_mock.return_value.post
        post_mock.side_effect = [
            response(400, text='Alternatives unavailable.'),
            response(200, {'type': 'FeatureCollection', 'features': [{'geometry': {}}]}),
        ]
        with self.assertRaises(ProviderMalformedResponseError):
            build_route_geometry((32.7, -96.8), (32.8, -96.6))

    @override_settings(ORS_API_KEY='test-key')
    @patch('services.providers._http_session')
    def test_provider_failure_has_sanitized_client_error(self, session_mock):
        post_mock = session_mock.return_value.post
        post_mock.return_value = response(503, text='provider failed')
        with self.assertRaisesRegex(ProviderError, 'currently unavailable'):
            build_route_geometry((32.7, -96.8), (31.7, -106.4))
        post_mock.assert_called_once()

    @override_settings(ORS_API_KEY='secret-test-token')
    @patch('services.providers._http_session')
    def test_upstream_error_logs_bounded_redacted_excerpt(self, session_mock):
        post_mock = session_mock.return_value.post
        post_mock.return_value = response(406, text=f'Error {("x" * 700)} secret-test-token')
        with self.assertLogs('services.providers', level='WARNING') as logs:
            post_mock.side_effect = [
                response(406, text=f'Error {("x" * 700)} secret-test-token'),
                response(200, {'type': 'FeatureCollection', 'features': [geojson_route()]}),
            ]
            build_route_geometry((32.7, -96.8), (32.8, -96.6))
        self.assertIn('upstream_status=406', logs.output[0])
        self.assertNotIn('secret-test-token', logs.output[0])
        self.assertLess(len(logs.output[0]), 700)
