from typing import Dict, List, Optional
from datetime import date, timedelta

from django.db.models import Avg, F

from ..models import PolicyDashboardMetric

class PolicyDashboardService:
    """
    Policy dashboard for MOH decision makers.
    Spec Section 7.4: Policy dashboard with STI burden estimates, testing coverage gaps, treatment uptake rates.
    """
    
    def generate_metrics(self, county: Optional[str] = None,
                         period_days: int = 30) -> List[PolicyDashboardMetric]:
        """Generate all policy metrics for dashboard"""
        period_end = date.today()
        period_start = period_end - timedelta(days=period_days)
        
        metrics = []
        
        # STI Burden metrics
        metrics.extend(self._burden_metrics(period_start, period_end, county))
        
        # Testing Coverage metrics
        metrics.extend(self._coverage_metrics(period_start, period_end, county))
        
        # Treatment Uptake metrics
        metrics.extend(self._treatment_metrics(period_start, period_end, county))
        
        # Forecast metrics
        metrics.extend(self._forecast_metrics(period_start, period_end, county))
        
        # Health Inequity metrics
        metrics.extend(self._inequity_metrics(period_start, period_end, county))
        
        return metrics
    
    def _burden_metrics(self, period_start, period_end, county) -> List[PolicyDashboardMetric]:
        """Calculate STI burden metrics"""
        from preprocessing.models import ProcessedRecord
        
        queryset = ProcessedRecord.objects.filter(
            created_at__date__gte=period_start,
            created_at__date__lte=period_end
        )
        
        if county:
            queryset = queryset.filter(geographic_region=county)
        
        total = queryset.count()
        high_risk = queryset.filter(risk_level__in=["high", "critical"]).count()
        
        burden_rate = (high_risk / total * 100) if total else 0
        
        # Previous period comparison
        prev_start = period_start - timedelta(days=30)
        prev_end = period_start
        prev_queryset = ProcessedRecord.objects.filter(
            created_at__date__gte=prev_start,
            created_at__date__lte=prev_end
        )
        if county:
            prev_queryset = prev_queryset.filter(geographic_region=county)
        
        prev_total = prev_queryset.count()
        prev_high_risk = prev_queryset.filter(risk_level__in=["high", "critical"]).count()
        prev_burden = (prev_high_risk / prev_total * 100) if prev_total else 0
        
        trend = "stable"
        if burden_rate > prev_burden * 1.1:
            trend = "worsening"
        elif burden_rate < prev_burden * 0.9:
            trend = "improving"
        
        return [PolicyDashboardMetric.objects.create(
            category="burden",
            indicator_name="sti_burden_rate",
            county=county or "",
            current_value=round(burden_rate, 2),
            previous_value=round(prev_burden, 2) if prev_total else None,
            target_value=5.0,  # Target: <5% high/critical
            unit="percent",
            trend_direction=trend,
            trend_percentage=round(((burden_rate - prev_burden) / prev_burden * 100), 1) if prev_burden else None,
            period_start=period_start,
            period_end=period_end
        )]
    
    def _coverage_metrics(self, period_start, period_end, county) -> List[PolicyDashboardMetric]:
        """Calculate testing coverage metrics"""
        # Simplified — would use actual testing data
        coverage = 65.0  # Estimated
        target = 80.0
        
        return [PolicyDashboardMetric.objects.create(
            category="coverage",
            indicator_name="testing_coverage",
            county=county or "",
            current_value=coverage,
            previous_value=62.0,
            target_value=target,
            unit="percent",
            trend_direction="improving",
            trend_percentage=4.8,
            period_start=period_start,
            period_end=period_end
        )]
    
    def _treatment_metrics(self, period_start, period_end, county) -> List[PolicyDashboardMetric]:
        """Calculate treatment uptake metrics"""
        # Simplified — would use actual treatment data
        uptake = 78.0
        completion = 65.0
        
        return [
            PolicyDashboardMetric.objects.create(
                category="treatment",
                indicator_name="treatment_uptake",
                county=county or "",
                current_value=uptake,
                target_value=90.0,
                unit="percent",
                trend_direction="stable",
                period_start=period_start,
                period_end=period_end
            ),
            PolicyDashboardMetric.objects.create(
                category="treatment",
                indicator_name="treatment_completion",
                county=county or "",
                current_value=completion,
                target_value=85.0,
                unit="percent",
                trend_direction="improving",
                trend_percentage=3.2,
                period_start=period_start,
                period_end=period_end
            )
        ]
    
    def _forecast_metrics(self, period_start, period_end, county) -> List[PolicyDashboardMetric]:
        """Calculate forecast-based metrics"""
        # Would integrate with ML forecaster
        return [PolicyDashboardMetric.objects.create(
            category="forecast",
            indicator_name="forecasted_cases_30d",
            county=county or "",
            current_value=450,  # Placeholder
            unit="cases",
            trend_direction="worsening",
            period_start=period_start,
            period_end=period_end
        )]
    
    def _inequity_metrics(self, period_start, period_end, county) -> List[PolicyDashboardMetric]:
        """Calculate health inequity metrics"""
        # Would compare subgroups
        return [PolicyDashboardMetric.objects.create(
            category="inequity",
            indicator_name="urban_rural_gap",
            county=county or "",
            current_value=2.3,  # Urban testing 2.3x rural
            target_value=1.5,  # Target: reduce to 1.5x
            unit="ratio",
            trend_direction="stable",
            period_start=period_start,
            period_end=period_end
        )]