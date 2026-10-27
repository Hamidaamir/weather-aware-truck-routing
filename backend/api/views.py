import logging
import time

from django.http import JsonResponse
from rest_framework import status
from rest_framework.decorators import api_view

from api.serializers import GeocodeSearchSerializer, RoutePlanRequestSerializer
from services.providers import (
    ProviderAuthenticationError,
    ProviderConfigError,
    ProviderError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    search_locations,
)
from services.route_service import generate_plan

logger = logging.getLogger(__name__)


@api_view(['GET'])
def health(request):
    return JsonResponse({'status': 'ok', 'service': 'weather-aware-truck-routing'})


@api_view(['GET'])
def geocode(request):
    serializer = GeocodeSearchSerializer(data=request.query_params)
    if not serializer.is_valid():
        return JsonResponse({'detail': 'Validation failed.', 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
    try:
        suggestions = search_locations(serializer.validated_data['q'])
    except ProviderConfigError as exc:
        logger.warning('Geocoding blocked because provider configuration is missing: %s', exc)
        return JsonResponse({'detail': 'Provider configuration missing.', 'message': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    except ProviderRateLimitError as exc:
        logger.warning('OpenRouteService geocoding rate limit reached.')
        return JsonResponse({'detail': 'Location search is temporarily rate limited.', 'message': str(exc)}, status=status.HTTP_429_TOO_MANY_REQUESTS)
    except ProviderTimeoutError as exc:
        logger.warning('OpenRouteService geocoding timed out.')
        return JsonResponse({'detail': 'Location search timed out.', 'message': str(exc)}, status=status.HTTP_504_GATEWAY_TIMEOUT)
    except ProviderAuthenticationError as exc:
        logger.warning('OpenRouteService rejected the geocoding credentials.')
        return JsonResponse({'detail': 'Location search configuration is invalid.', 'message': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    except ProviderError as exc:
        logger.warning('OpenRouteService geocoding provider error: %s', exc)
        return JsonResponse({'detail': 'Location search failed.', 'message': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
    return JsonResponse({'suggestions': suggestions})


@api_view(['POST'])
def route_plan(request):
    request_started = time.perf_counter()
    serializer = RoutePlanRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return JsonResponse({'detail': 'Validation failed.', 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    payload = serializer.validated_data
    try:
        plan = generate_plan(
            origin=payload['origin'],
            destination=payload['destination'],
            departure_datetime=payload['departure_datetime'],
            load_weight_lbs=float(payload['load_weight_lbs']),
            checkpoint_interval_miles=int(payload['checkpoint_interval_miles']),
            forecast_offset_hours=int(payload['forecast_offset_hours']),
        )
    except ProviderConfigError as exc:
        logger.warning('API route plan blocked: %s', exc)
        return JsonResponse({'detail': 'Provider configuration missing.', 'message': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    except ProviderAuthenticationError as exc:
        logger.warning('OpenRouteService rejected the routing credentials.')
        return JsonResponse({'detail': 'Routing provider configuration is invalid.', 'message': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    except ProviderRateLimitError as exc:
        logger.warning('OpenRouteService route generation rate limit reached.')
        return JsonResponse({'detail': 'Routing provider rate limit reached.', 'message': str(exc)}, status=status.HTTP_429_TOO_MANY_REQUESTS)
    except ProviderTimeoutError as exc:
        logger.warning('OpenRouteService route generation timed out.')
        return JsonResponse({'detail': 'Routing provider timed out.', 'message': str(exc)}, status=status.HTTP_504_GATEWAY_TIMEOUT)
    except ProviderError as exc:
        logger.warning('External provider error raised while planning route: %s', exc)
        return JsonResponse({'detail': 'Provider error while generating route.', 'message': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
    except ValueError as exc:
        logger.warning('Input validation error in route planning: %s', exc)
        return JsonResponse({'detail': 'Invalid route request.', 'message': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.exception('Unexpected error generating route plan: %s', exc)
        return JsonResponse({'detail': 'Unable to generate route plan.', 'message': 'The server could not complete the request.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    serialization_started = time.perf_counter()
    response = JsonResponse(plan, status=status.HTTP_200_OK)
    logger.info(
        'route_plan_request outcome=success serialization_ms=%.1f view_total_ms=%.1f',
        (time.perf_counter() - serialization_started) * 1000,
        (time.perf_counter() - request_started) * 1000,
    )
    return response
