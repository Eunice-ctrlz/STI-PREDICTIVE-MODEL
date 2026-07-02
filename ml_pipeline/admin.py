from django.contrib import admin
from .models import MLModel, TrainingJob


@admin.register(MLModel)
class MLModelAdmin(admin.ModelAdmin):
    list_display = ('name', 'version', 'model_type', 'status', 'test_auc_roc', 'is_default', 'created_at')
    list_filter = ('model_type', 'status', 'is_default')
    search_fields = ('name', 'version')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(TrainingJob)
class TrainingJobAdmin(admin.ModelAdmin):
    list_display = ('model', 'status', 'current_epoch', 'total_epochs', 'started_at', 'completed_at')
    list_filter = ('status',)
    readonly_fields = ('created_at',)