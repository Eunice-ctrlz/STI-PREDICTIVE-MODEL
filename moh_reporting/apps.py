from django.apps import AppConfig


class MohReportingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'moh_reporting'
    verbose_name = 'MOH Reporting & Analytics'

    def ready(self):
        pass