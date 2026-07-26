from django.urls import path
from .views import predict, prediction_detail, history, stats

urlpatterns = [
    path('predict', predict, name='predict'),
    path('<int:prediction_id>', prediction_detail, name='prediction_detail'),
    path('history/<str:patient_id>', history, name='history'),
    path('stats', stats, name='stats'),
]
