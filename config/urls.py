
from django.contrib import admin
from django.urls import path
from preprocessing.api import api as preprocessing_api
from geospatial.api import api as geospatial_api
from patients.api import api as patients_api
urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/', preprocessing_api.urls),
    path('api/v1/', geospatial_api.urls),
    path('api/v1/', patients_api.urls),
]
