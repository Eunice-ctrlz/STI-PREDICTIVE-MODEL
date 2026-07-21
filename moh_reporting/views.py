from rest_framework.decorators import api_view
from rest_framework.response import Response

@api_view(['GET'])
def dashboard(request):
    # Mock dashboard reporting data
    return Response({
        "summary": {
            "total_patients": 12450,
            "total_screenings": 8321,
            "high_risk_patients": 342,
            "avg_risk_score": 0.284
        },
        "risk_distribution": {
            "low": 5234,
            "moderate": 2103,
            "high": 784,
            "very_high": 200
        },
        "age_distribution": {
            "15-19": 1200,
            "20-24": 3400,
            "25-29": 2800,
            "30-34": 1500,
            "35-39": 800,
            "40-49": 621
        },
        "county_breakdown": [
            {"county": "Nairobi", "patients": 4521, "avg_risk": 0.32, "high_risk": 145},
            {"county": "Mombasa", "patients": 2103, "avg_risk": 0.28, "high_risk": 89},
            {"county": "Kisumu", "patients": 1800, "avg_risk": 0.35, "high_risk": 67},
        ],
        "daily_trend": [
            {"date": "2024-03-01", "count": 45, "avg_risk": 0.25},
            {"date": "2024-03-02", "count": 52, "avg_risk": 0.28},
            {"date": "2024-03-03", "count": 38, "avg_risk": 0.22},
        ]
    })
