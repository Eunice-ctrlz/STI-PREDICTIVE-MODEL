from django.contrib import admin

from .models import PredictionExplanation


@admin.register(PredictionExplanation)
class PredictionExplanationAdmin(admin.ModelAdmin):
    list_display = ('prediction', 'provider', 'model_identifier', 'created_at')
    list_filter = ('provider', 'model_identifier', 'created_at')
    search_fields = ('prediction__patient__patient_id', 'summary')
    readonly_fields = ('created_at', 'updated_at')
