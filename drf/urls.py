"""
URL configuration for drf project.
"""
from django.urls import path, include

urlpatterns = [
    path('', include('api.urls')),
]
