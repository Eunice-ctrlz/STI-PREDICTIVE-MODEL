from django.contrib import admin
from .models import GeographicRiskZone, FacilityLocation


@admin.register(GeographicRiskZone)
class GeographicRiskZoneAdmin(admin.ModelAdmin):
    list_display = ('name', 'county', 'risk_level', 'risk_score', 'population_at_risk', 'total_screenings')
    list_filter = ('risk_level', 'county')
    search_fields = ('name', 'county', 'sub_county', 'ward')


@admin.register(FacilityLocation)
class FacilityLocationAdmin(admin.ModelAdmin):
    list_display = ('facility', 'service_radius_km')