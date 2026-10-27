from django.test import SimpleTestCase

from routing.risk import classify_rain, classify_snow, classify_wind, rank_routes


class RiskClassificationTests(SimpleTestCase):
    def test_wind_boundaries(self):
        self.assertEqual(classify_wind(24.9), 'low')
        self.assertEqual(classify_wind(25), 'moderate')
        self.assertEqual(classify_wind(34.9), 'moderate')
        self.assertEqual(classify_wind(35), 'high')
        self.assertEqual(classify_wind(44.9), 'high')
        self.assertEqual(classify_wind(45), 'severe')
        self.assertEqual(classify_wind(54.9), 'severe')
        self.assertEqual(classify_wind(55), 'no_travel')

    def test_rain_boundaries(self):
        self.assertEqual(classify_rain(0.099), 'low')
        self.assertEqual(classify_rain(0.10), 'moderate')
        self.assertEqual(classify_rain(0.249), 'moderate')
        self.assertEqual(classify_rain(0.25), 'high')
        self.assertEqual(classify_rain(0.499), 'high')
        self.assertEqual(classify_rain(0.50), 'severe')
        self.assertEqual(classify_rain(1.00), 'severe')
        self.assertEqual(classify_rain(1.01), 'no_travel')

    def test_snow_boundaries(self):
        self.assertEqual(classify_snow(0.499), 'low')
        self.assertEqual(classify_snow(0.5), 'moderate')
        self.assertEqual(classify_snow(0.999), 'moderate')
        self.assertEqual(classify_snow(1.0), 'high')
        self.assertEqual(classify_snow(1.999), 'high')
        self.assertEqual(classify_snow(2.0), 'severe')
        self.assertEqual(classify_snow(3.0), 'severe')
        self.assertEqual(classify_snow(3.01), 'no_travel')

    def test_load_dependent_wind_rules(self):
        self.assertEqual(classify_wind(45, 30000), 'severe')
        self.assertEqual(classify_wind(45, 30001), 'no_travel')
        self.assertEqual(classify_wind(35, 40000), 'high')
        self.assertEqual(classify_wind(35, 40001), 'severe')
        self.assertEqual(classify_wind(55, 1000), 'no_travel')

    def test_ranking_and_no_travel_rule(self):
        route_a = {'severe_miles': 0, 'high_miles': 0, 'average_risk_score': 1, 'estimated_travel_time_minutes': 120, 'no_travel_checkpoints': 0, 'weather_coverage_percent': 100}
        route_b = {'severe_miles': 10, 'high_miles': 0, 'average_risk_score': 1, 'estimated_travel_time_minutes': 100, 'no_travel_checkpoints': 0, 'weather_coverage_percent': 100}
        route_c = {'severe_miles': 0, 'high_miles': 5, 'average_risk_score': 3, 'estimated_travel_time_minutes': 80, 'no_travel_checkpoints': 1, 'weather_coverage_percent': 100}
        ranked = rank_routes([route_b, route_a, route_c])
        self.assertEqual(ranked[0]['severe_miles'], 0)
        self.assertEqual(ranked[0]['high_miles'], 0)
        self.assertTrue(ranked[0].get('recommended', False))
