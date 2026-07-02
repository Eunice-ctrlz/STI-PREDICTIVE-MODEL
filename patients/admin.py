from django.contrib import admin
from .models import Patient, PatientVisit


class PatientVisitInline(admin.TabularInline):
    model = PatientVisit
    extra = 0
    readonly_fields = ('visit_date',)


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ('patient_id', 'full_name', 'gender', 'age', 'county', 'is_active', 'created_at')
    list_filter = ('gender', 'is_active', 'county', 'hiv_status', 'prior_sti_history')
    search_fields = ('patient_id', 'first_name', 'last_name', 'phone')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [PatientVisitInline]
    fieldsets = (
        ('Basic Info', {
            'fields': ('patient_id', 'first_name', 'last_name', 'date_of_birth', 'gender', 'phone', 'email')
        }),
        ('Location', {
            'fields': ('address', 'county', 'sub_county', 'ward')
        }),
        ('Risk Factors', {
            'fields': (
                'marital_status', 'number_of_partners_12m', 'number_of_partners_lifetime',
                'condom_use_frequency', 'substance_use', 'substance_type',
                'prior_sti_history', 'prior_sti_types', 'hiv_status_known', 'hiv_status',
                'symptoms_present', 'symptom_description'
            )
        }),
        ('Status', {
            'fields': ('is_active', 'user', 'created_at', 'updated_at')
        }),
    )


@admin.register(PatientVisit)
class PatientVisitAdmin(admin.ModelAdmin):
    list_display = ('patient', 'visit_type', 'facility', 'visit_date')
    list_filter = ('visit_type', 'visit_date')
    search_fields = ('patient__patient_id', 'patient__first_name', 'facility')