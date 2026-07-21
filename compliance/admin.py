from django.contrib import admin
from .models import AuditLog

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('user_name', 'action', 'resource_type', 'created_at')
    list_filter = ('action', 'resource_type')
    search_fields = ('user_name', 'description')
