from rest_framework import viewsets
from .models import Patient
from .serializers import PatientSerializer

class PatientViewSet(viewsets.ModelViewSet):
    queryset = Patient.objects.all().order_by('-created_at')
    serializer_class = PatientSerializer

    def get_queryset(self):
        queryset = Patient.objects.all().order_by('-created_at')
        county = self.request.query_params.get('county', None)
        if county is not None:
            queryset = queryset.filter(county=county)
        return queryset
