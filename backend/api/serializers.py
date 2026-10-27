from __future__ import annotations

from datetime import datetime

from django.utils import timezone
from rest_framework import serializers


class RoutePlanRequestSerializer(serializers.Serializer):
    origin = serializers.CharField(max_length=200, trim_whitespace=True)
    destination = serializers.CharField(max_length=200, trim_whitespace=True)
    departure_datetime = serializers.DateTimeField()
    load_weight_lbs = serializers.FloatField(min_value=1, max_value=150000)
    checkpoint_interval_miles = serializers.IntegerField(min_value=10, max_value=50)
    forecast_offset_hours = serializers.IntegerField(min_value=0, max_value=48)

    def validate(self, attrs):
        origin = attrs.get('origin', '').strip()
        destination = attrs.get('destination', '').strip()
        if origin.lower() == destination.lower():
            raise serializers.ValidationError({'origin': 'Origin and destination cannot be the same after normalization.'})
        departure = attrs.get('departure_datetime')
        if departure is not None and not timezone.is_aware(departure):
            raise serializers.ValidationError({'departure_datetime': 'Departure time must include timezone information.'})
        valid_intervals = {10, 25, 50}
        if attrs.get('checkpoint_interval_miles') not in valid_intervals:
            raise serializers.ValidationError({'checkpoint_interval_miles': 'Checkpoint interval must be one of 10, 25, or 50 miles.'})
        return attrs


class GeocodeSearchSerializer(serializers.Serializer):
    q = serializers.CharField(min_length=3, max_length=120, trim_whitespace=True)
