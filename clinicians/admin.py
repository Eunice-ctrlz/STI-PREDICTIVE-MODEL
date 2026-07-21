from django.contrib import admin
from .models import Facility, Clinician


@admin.register(Facility)
class FacilityAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'county', 'facility_type', 'is_active')
    list_filter = ('county', 'facility_type', 'is_active')
    search_fields = ('name', 'code')


@admin.register(Clinician)
class ClinicianAdmin(admin.ModelAdmin):
    list_display = ('staff_id', 'user', 'role', 'facility', 'is_active')
    list_filter = ('role', 'is_active', 'facility__county')
    search_fields = ('staff_id', 'user__first_name', 'user__last_name', 'phone')