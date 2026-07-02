from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from ninja import NinjaAPI

# Import routers from each app
from prediction_engine.api import router as prediction_router
from patients.api import router as patients_router
from clinicians.api import router as clinicians_router
from geospatial.api import router as geo_router
from moh_reporting.api import router as reporting_router
from compliance.api import router as compliance_router
from data_ingestion.api import router as ingestion_router
from ml_pipeline.api import router as ml_router

api = NinjaAPI(
    title="STI Predictor API",
    version="1.0.0",
    description="Backend API for STI Risk Prediction Platform",
    docs_url="/docs",
)

api.add_router("/predictions/", prediction_router)
api.add_router("/patients/", patients_router)
api.add_router("/clinicians/", clinicians_router)
api.add_router("/geospatial/", geo_router)
api.add_router("/reporting/", reporting_router)
api.add_router("/compliance/", compliance_router)
api.add_router("/ingestion/", ingestion_router)
api.add_router("/ml/", ml_router)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', api.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)