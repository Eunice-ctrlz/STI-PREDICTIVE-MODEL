from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import CountyRiskData
from .serializers import CountyRiskDataSerializer

@api_view(['GET'])
def heatmap(request):
    # Mock geospatial data if none exists
    if CountyRiskData.objects.count() == 0:
        return Response([
            {"county": "Nairobi", "latitude": -1.2921, "longitude": 36.8219, "avg_risk_score": 0.45},
            {"county": "Mombasa", "latitude": -4.0435, "longitude": 39.6682, "avg_risk_score": 0.38},
            {"county": "Kisumu", "latitude": -0.0917, "longitude": 34.7680, "avg_risk_score": 0.42},
        ])
    data = CountyRiskData.objects.all()
    serializer = CountyRiskDataSerializer(data, many=True)
    return Response(serializer.data)

@api_view(['GET'])
def county_summary(request):
    if CountyRiskData.objects.count() == 0:
        return Response({
            "total_counties": 47,
            "high_risk_counties": ["Nairobi", "Kisumu"],
        })
    return Response({"total_counties": CountyRiskData.objects.count()})
