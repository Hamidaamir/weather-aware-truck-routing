import argparse
import os
import statistics
import time
from datetime import datetime
from unittest.mock import patch

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from services.checkpoints import route_distance_meters
from services.route_service import generate_plan


def run_benchmark(runs: int) -> None:
    latitude = 32.7
    geometry = [
        {'lat': latitude, 'lon': -96.8 + index * 5.7 / 9999}
        for index in range(10_000)
    ]
    distance_meters = route_distance_meters(geometry)[-1]
    route = {
        'distance_meters': distance_meters,
        'duration_seconds': 6 * 60 * 60,
        'geometry': geometry,
    }
    durations_ms = []
    checkpoint_count = 0
    weather_batch_calls = 0

    def fake_weather_batch(checkpoints, departure, forecast_offset):
        nonlocal checkpoint_count, weather_batch_calls
        time.sleep(0.02)
        checkpoint_count = len(checkpoints)
        weather_batch_calls += 1
        return [
            {
                'missing': False,
                'wind_mph': 10.0,
                'rain_in_hr': 0.0,
                'snow_in_hr': 0.0,
            }
            for _ in checkpoints
        ]

    for _ in range(runs):
        start = time.perf_counter()
        with (
            patch('services.route_service.geocode_location', side_effect=lambda query: {
                'name': query,
                'lat': 32.7 if query == 'Origin' else 31.8,
                'lon': -96.8 if query == 'Origin' else -106.4,
            }),
            patch('services.route_service.build_route_geometry', return_value={'routes': [route], 'warnings': []}),
            patch('services.route_service.determine_weather_for_checkpoints', side_effect=fake_weather_batch),
        ):
            generate_plan(
                'Origin',
                'Destination',
                datetime.fromisoformat('2026-10-28T08:00:00-05:00'),
                35000,
                25,
                0,
            )
        durations_ms.append((time.perf_counter() - start) * 1000)

    print(f'runs={runs}')
    print(f'median_plan_processing_ms={statistics.median(durations_ms):.1f}')
    print(f'checkpoint_count={checkpoint_count}')
    print(f'mocked_weather_batch_calls_per_run={weather_batch_calls / runs:.1f}')
    print('mocked_external_weather_latency_ms_per_run=20.0')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Benchmark route planning with mocked providers.')
    parser.add_argument('--runs', type=int, default=5)
    arguments = parser.parse_args()
    run_benchmark(max(1, arguments.runs))
