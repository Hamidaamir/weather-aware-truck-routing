from django.urls import path

from api.views import geocode, health, route_plan

urlpatterns = [
    path('health/', health, name='health'),
    path('geocode/', geocode, name='geocode'),
    path('route-plan/', route_plan, name='route_plan'),
]
