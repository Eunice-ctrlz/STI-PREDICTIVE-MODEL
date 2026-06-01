from django.apps import AppConfig


class CliniciansConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'clinicians'
    verbose_name = 'Clinician Management & Support'
    def ready(self):

        pass
