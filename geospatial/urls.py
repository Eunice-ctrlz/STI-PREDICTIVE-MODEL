from django.urls import path
from .views import heatmap, county_summary

urlpatterns = [
    path('heatmap', heatmap, name='heatmap'),
    path('county-summary', county_summary, name='county_summary'),
]
