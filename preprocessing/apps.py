from django.apps import AppConfig

class PreprocessingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'preprocessing'
    verbose_name = 'STI Preprocessing Pipeline'

    def ready(self):
        # Import signals if needed
        pass