import csv
import json
import io
from typing import Dict, List, Optional
from datetime import date, timedelta
from collections import defaultdict

from django.utils import timezone
from django.db.models import Count, Sum, Avg, F

from ..models import SurveillanceReport, ReportStatus, ReportFormat
from preprocessing.models import ProcessedRecord
from clinicians.models import PatientRiskAlert
from geospatial.models import AggregatedIncident

class WeeklyReportGenerator:
    """
    Generate weekly surveillance reports aligned to WHO standards.
    Spec Section 7.4: Weekly automated summary reports.
    """
    
    WHO_INDICATORS = {
        "hiv": "HIV_PREVALENCE",
        "chlamydia": "CT_INCIDENCE",
        "syphilis": "TP_INCIDENCE",
        "gonorrhoea": "NG_INCIDENCE",
        "hpv": "HPV_PREVALENCE",
        "hsv2": "HSV2_PREVALENCE"
    }
    
    def __init__(self, period_start: date, period_end: date):
        self.period_start = period_start
        self.period_end = period_end
    
    def generate(self, scope_national: bool = True,
                 counties: Optional[List[str]] = None) -> SurveillanceReport:
        """Generate complete weekly report"""
        
        # Create report record
        report = SurveillanceReport.objects.create(
            report_type="weekly",
            period_start=self.period_start,
            period_end=self.period_end,
            scope_national=scope_national,
            counties_included=counties or [],
            status=ReportStatus.GENERATING
        )
        
        try:
            # Gather data
            self._collect_assessment_data(report, counties)
            self._collect_alert_data(report, counties)
            self._collect_incident_data(report, counties)
            self._calculate_coverage_metrics(report, counties)
            self._map_who_indicators(report)
            
            # Generate export file
            self._generate_export_file(report)
            
            report.status = ReportStatus.READY
            report.save()
            
            return report
            
        except Exception as e:
            report.status = ReportStatus.FAILED
            report.save()
            raise
    
    def _collect_assessment_data(self, report: SurveillanceReport,
                                  counties: Optional[List[str]]):
        """Collect patient assessment statistics"""
        queryset = ProcessedRecord.objects.filter(
            created_at__date__gte=self.period_start,
            created_at__date__lte=self.period_end
        )
        
        if counties and not report.scope_national:
            queryset = queryset.filter(geographic_region__in=counties)
        
        report.total_assessments = queryset.count()
        
        # Risk distribution
        risk_counts = queryset.values('risk_level').annotate(count=Count('risk_level'))
        report.risk_distribution = {r['risk_level']: r['count'] for r in risk_counts}
        
        # STI breakdown from probabilities
        sti_counts = defaultdict(int)
        for record in queryset:
            for sti, prob in (record.sti_labels or {}).items():
                if prob > 0.5:
                    sti_counts[sti] += 1
        
        report.sti_breakdown = dict(sti_counts)
        
        # Demographics
        age_dist = defaultdict(int)
        sex_dist = defaultdict(int)
        geo_dist = defaultdict(int)
        
        for record in queryset:
            demo = record.demographics or {}
            age = demo.get('age', 0)
            age_group = self._age_to_group(age)
            age_dist[age_group] += 1
            
            sex = demo.get('sex', 'unknown')
            sex_dist[sex] += 1
            
            geo_dist[record.geographic_region] += 1
        
        report.age_distribution = dict(age_dist)
        report.sex_distribution = {k: round(v / report.total_assessments, 3) 
                                    for k, v in sex_dist.items()} if report.total_assessments else {}
        report.geographic_distribution = dict(geo_dist)
    
    def _collect_alert_data(self, report: SurveillanceReport,
                            counties: Optional[List[str]]):
        """Collect clinician alert resolution data"""
        queryset = PatientRiskAlert.objects.filter(
            triggered_at__date__gte=self.period_start,
            triggered_at__date__lte=self.period_end
        )
        
        if counties and not report.scope_national:
            queryset = queryset.filter(facility_county__in=counties)
        
        # Testing and treatment metrics (from resolved alerts)
        resolved = queryset.filter(status="resolved")
        
        # Estimate tests conducted from alert actions
        report.tests_conducted = sum(
            1 for a in resolved if a.test_orders
        ) * 2  # Approximate: avg 2 tests per patient
        
        report.tests_positive = int(report.tests_conducted * 0.3)  # Estimated positivity rate
        
        report.treatment_initiated = sum(
            1 for a in resolved if a.referral_made
        )
        
        report.treatment_completed = int(report.treatment_initiated * 0.7)  # Estimated completion
    
    def _collect_incident_data(self, report: SurveillanceReport,
                               counties: Optional[List[str]]):
        """Collect confirmed case data from MOH database"""
        queryset = AggregatedIncident.objects.filter(
            period_start__gte=self.period_start,
            period_end__lte=self.period_end
        )
        
        if counties and not report.scope_national:
            queryset = queryset.filter(grid_cell__county__in=counties)
        
        report.total_confirmed_cases = queryset.aggregate(
            total=Sum('incident_count')
        )['total'] or 0
    
    def _calculate_coverage_metrics(self, report: SurveillanceReport,
                                     counties: Optional[List[str]]):
        """Calculate testing coverage and gaps"""
        # Population estimates (simplified — would use actual census data)
        county_pops = {
            "Nairobi": 4500000,
            "Mombasa": 1200000,
            "Kisumu": 600000,
            # ... all 47 counties
        }
        
        target_counties = counties if counties else list(county_pops.keys())
        total_pop = sum(county_pops.get(c, 500000) for c in target_counties)
        
        # Testing coverage rate
        expected_tests = total_pop * 0.001  # 0.1% of population tested weekly
        report.testing_coverage_rate = round(
            report.tests_conducted / expected_tests, 3
        ) if expected_tests else 0
        
        # Untested high-risk estimate
        high_risk = report.risk_distribution.get('high', 0) + report.risk_distribution.get('critical', 0)
        report.untested_high_risk_estimate = max(0, high_risk - report.tests_conducted)
        
        # Facility gaps (simplified)
        report.facility_gaps = self._identify_facility_gaps(target_counties)
    
    def _identify_facility_gaps(self, counties: List[str]) -> List[Dict]:
        """Identify counties with insufficient testing facilities"""
        from geospatial.models import HealthcareFacility
        
        gaps = []
        for county in counties:
            facility_count = HealthcareFacility.objects.filter(
                county=county,
                is_active=True
            ).count()
            
            # Threshold: 1 facility per 100,000 population
            expected = 5  # Simplified
            if facility_count < expected:
                gaps.append({
                    "county": county,
                    "current_facilities": facility_count,
                    "required_facilities": expected,
                    "gap": expected - facility_count,
                    "population_per_facility": 100000  # Would be actual calc
                })
        
        return gaps
    
    def _map_who_indicators(self, report: SurveillanceReport):
        """Map STI types to WHO indicator codes"""
        indicators = []
        for sti, count in report.sti_breakdown.items():
            if sti in self.WHO_INDICATORS:
                indicators.append({
                    "who_code": self.WHO_INDICATORS[sti],
                    "sti_type": sti,
                    "case_count": count,
                    "incidence_rate": round(count / 100000, 2)  # Per 100k
                })
        
        report.who_indicator_codes = indicators
        report.who_submission_ready = len(indicators) > 0
    
    def _generate_export_file(self, report: SurveillanceReport):
        """Generate the actual report file"""
        if report.file_format == ReportFormat.CSV:
            self._generate_csv(report)
        elif report.file_format == ReportFormat.JSON:
            self._generate_json(report)
        elif report.file_format == ReportFormat.PDF:
            self._generate_pdf(report)
    
    def _generate_csv(self, report: SurveillanceReport):
        """Generate CSV export"""
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Header
        writer.writerow([
            "Reporting Period", "County", "STI Type", "Age Group", "Sex",
            "Case Count", "Incidence Rate", "Tests Conducted", "Tests Positive",
            "Treatment Initiated"
        ])
        
        # Data rows (aggregated, non-identifiable)
        for sti, count in report.sti_breakdown.items():
            for county in (report.counties_included or ["National"]):
                writer.writerow([
                    f"{self.period_start} to {self.period_end}",
                    county,
                    sti,
                    "All Ages",  # Would be age-stratified
                    "All",
                    count,
                    round(count / 100000, 2),
                    report.tests_conducted,
                    report.tests_positive,
                    report.treatment_initiated
                ])
        
        # Save to file
        file_path = f"reports/weekly_{report.report_id}.csv"
        # In production, save to S3 or file storage
        report.file_path = file_path
        report.file_size_bytes = len(output.getvalue().encode('utf-8'))
    
    def _generate_json(self, report: SurveillanceReport):
        """Generate JSON export"""
        data = {
            "metadata": {
                "report_id": str(report.report_id),
                "period": f"{self.period_start} to {self.period_end}",
                "generated_at": timezone.now().isoformat(),
                "who_aligned": report.who_submission_ready
            },
            "summary": {
                "total_assessments": report.total_assessments,
                "total_confirmed_cases": report.total_confirmed_cases,
                "sti_breakdown": report.sti_breakdown,
                "risk_distribution": report.risk_distribution
            },
            "demographics": {
                "age": report.age_distribution,
                "sex": report.sex_distribution,
                "geographic": report.geographic_distribution
            },
            "testing_and_treatment": {
                "tests_conducted": report.tests_conducted,
                "tests_positive": report.tests_positive,
                "treatment_initiated": report.treatment_initiated,
                "treatment_completed": report.treatment_completed,
                "coverage_rate": report.testing_coverage_rate
            },
            "who_indicators": report.who_indicator_codes
        }
        
        file_path = f"reports/weekly_{report.report_id}.json"
        report.file_path = file_path
        report.file_size_bytes = len(json.dumps(data).encode('utf-8'))
    
    def _generate_pdf(self, report: SurveillanceReport):
        """Generate PDF report (placeholder)"""
        # Would use ReportLab or WeasyPrint
        report.file_path = f"reports/weekly_{report.report_id}.pdf"
        report.file_size_bytes = 0
    
    def _age_to_group(self, age: int) -> str:
        """Convert age to WHO age group"""
        if age < 15:
            return "0-14"
        elif age < 20:
            return "15-19"
        elif age < 25:
            return "20-24"
        elif age < 35:
            return "25-34"
        elif age < 45:
            return "35-44"
        elif age < 55:
            return "45-54"
        else:
            return "55+"