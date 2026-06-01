from django.apps import AppConfig


class ComplianceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'compliance'
verbose_name = 'STI Compliance & Audit'

def ready(self):
    # Initialize retention policies on startup
    from .services.retention_enforcer import RetentionEnforcer
    enforcer = RetentionEnforcer()
    enforcer.initialize_policies()