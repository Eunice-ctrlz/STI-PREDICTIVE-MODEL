from django.apps import AppConfig


class GeospatialConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'geospatial'
    verbose_name = 'STI Geospatial Hotspot Engine'

    def ready(self):
        pass