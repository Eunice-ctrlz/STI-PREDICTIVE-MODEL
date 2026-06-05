
from django.contrib import admin
from django.urls import include, path
from preprocessing.api import api as preprocessing_api
from geospatial.api import api as geospatial_api
from patients.api import api as patients_api
from compliance.api import api as compliance_api
from moh_reporting.api import api as reporting_api
from clinicians.api import api as clinicians_api
urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/preprocessing/', preprocessing_api.urls),
    path('api/v1/geospatial/', geospatial_api.urls),
    path('api/v1/patients/', patients_api.urls),
    path('api/v1/compliance/', compliance_api.urls),
    path('api/v1/reporting/', reporting_api.urls),
    path('api/v1/clinicians/', clinicians_api.urls),
]   
