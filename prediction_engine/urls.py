from django.urls import path
from .views import predict, history, stats

urlpatterns = [
    path('predict', predict, name='predict'),
    path('history/<str:patient_id>', history, name='history'),
    path('stats', stats, name='stats'),
]
