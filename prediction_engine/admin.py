from django.contrib import admin
from .models import RiskPrediction, ModelPerformanceMetric


@admin.register(RiskPrediction)
class RiskPredictionAdmin(admin.ModelAdmin):
    list_display = ('patient', 'sti_type', 'risk_level', 'risk_score', 'model_version', 'created_at')
    list_filter = ('risk_level', 'sti_type', 'model_version', 'validated_by_clinician')
    search_fields = ('patient__patient_id', 'patient__first_name')
    readonly_fields = ('created_at',)
    fieldsets = (
        ('Prediction', {
            'fields': ('patient', 'clinician', 'sti_type', 'risk_score', 'risk_level')
        }),
        ('Model Info', {
            'fields': ('model_version', 'model_name', 'input_features', 'top_risk_factors')
        }),
        ('Recommendations', {
            'fields': ('recommended_tests', 'recommended_actions')
        }),
        ('Validation', {
            'fields': ('validated_by_clinician', 'clinician_notes', 'actual_outcome')
        }),
    )


@admin.register(ModelPerformanceMetric)
class ModelPerformanceMetricAdmin(admin.ModelAdmin):
    list_display = ('model_version', 'sti_type', 'auc_roc', 'f1_score', 'evaluated_on', 'sample_size')
    list_filter = ('sti_type', 'evaluated_on')