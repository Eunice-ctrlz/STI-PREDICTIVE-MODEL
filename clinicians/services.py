import uuid
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta, date
from collections import defaultdict

from django.db.models import Count, Avg, Q, F
from django.utils import timezone

from .models import (
    ClinicianProfile, ClinicalGuidance, PatientRiskAlert,
    PopulationRiskSummary, AuditLog, VerificationStatus
)
from preprocessing.models import ProcessedRecord

class GuidanceService:
    """
    Clinical guidance management with validation gate.
    Spec Section 8.2: Hard system constraint — no ML advice without validation.
    """
    
    def __init__(self):
        self.validation_requirements = {
            "draft": ["reviewed_by_clinician_1", "reviewed_by_clinician_2"],
            "clinician_approved": ["infectious_disease_specialist", "moh_signatory"],
            "moh_approved": ["deployed_at"]
        }
    
    def get_active_guidance(self, sti_type: str, risk_level: str) -> Optional[ClinicalGuidance]:
        """
        Retrieve deployed guidance for STI type and risk level.
        Only returns MOH-approved, deployed guidance.
        """
        return ClinicalGuidance.objects.filter(
            sti_type=sti_type,
            risk_level=risk_level,
            validation_status="deployed",
            annual_review_due__gt=date.today()
        ).order_by("-version").first()
    
    def match_guidance_to_symptoms(self, symptoms: List[str], risk_level: str) -> List[ClinicalGuidance]:
        """
        Find guidance matching symptom patterns.
        Returns ordered by relevance score.
        """
        all_guidance = ClinicalGuidance.objects.filter(
            validation_status="deployed",
            risk_level=risk_level
        )
        
        scored_guidance = []
        for guidance in all_guidance:
            pattern = guidance.symptom_pattern
            score = self._calculate_symptom_match(symptoms, pattern)
            if score > 0.3:  # Minimum relevance threshold
                scored_guidance.append((score, guidance))
        
        scored_guidance.sort(reverse=True)
        return [g for _, g in scored_guidance[:3]]  # Top 3
    
    def _calculate_symptom_match(self, symptoms: List[str], pattern: Dict) -> float:
        """Calculate Jaccard-like similarity between symptoms and pattern"""
        required = set(pattern.get("required", []))
        optional = set(pattern.get("optional", []))
        excluded = set(pattern.get("excluded", []))
        
        symptom_set = set(symptoms)
        
        # Check excluded symptoms (hard filter)
        if symptom_set & excluded:
            return 0.0
        
        # Required match
        if required and not required.issubset(symptom_set):
            return 0.0
        
        # Score based on coverage
        total_relevant = required | optional
        if not total_relevant:
            return 0.0
        
        matched = len(symptom_set & total_relevant)
        return matched / len(total_relevant)
    
    def submit_for_review(self, guidance_id: uuid.UUID, reviewer_name: str, 
                          reviewer_credentials: str, comments: str = "") -> Dict:
        """
        Submit guidance for clinical review.
        Enforces two-clinician minimum per Section 8.2.
        """
        guidance = ClinicalGuidance.objects.get(guidance_id=guidance_id)
        
        # Track reviewer
        if not guidance.reviewed_by_clinician_1:
            guidance.reviewed_by_clinician_1 = f"{reviewer_name} ({reviewer_credentials})"
            guidance.validation_status = "under_review"
        elif not guidance.reviewed_by_clinician_2:
            guidance.reviewed_by_clinician_2 = f"{reviewer_name} ({reviewer_credentials})"
            guidance.validation_status = "clinician_approved"
        else:
            # Check for infectious disease specialist
            if "infectious disease" in reviewer_credentials.lower() or \
               "ID specialist" in reviewer_credentials:
                guidance.infectious_disease_specialist = f"{reviewer_name} ({reviewer_credentials})"
        
        guidance.save()
        
        return {
            "guidance_id": guidance_id,
            "status": guidance.validation_status,
            "reviewers": [
                guidance.reviewed_by_clinician_1,
                guidance.reviewed_by_clinician_2
            ],
            "next_step": self._get_next_validation_step(guidance)
        }
    
    def _get_next_validation_step(self, guidance: ClinicalGuidance) -> str:
        """Determine next validation step based on current status"""
        if guidance.validation_status == "draft":
            return "Requires review by two licensed clinicians"
        elif guidance.validation_status == "under_review":
            return "Requires second clinician review"
        elif guidance.validation_status == "clinician_approved":
            if not guidance.infectious_disease_specialist:
                return "Requires infectious disease specialist review"
            return "Requires MOH sign-off"
        elif guidance.validation_status == "moh_approved":
            return "Ready for deployment"
        return "Unknown"

class AlertService:
    """
    Patient risk alert management.
    Spec Section 3.2: Score > 0.7 triggers mandatory clinical review.
    """
    
    CRITICAL_THRESHOLD = 0.7
    
    def create_alert(self, processed_record: ProcessedRecord) -> Optional[PatientRiskAlert]:
        """
        Create alert if risk exceeds threshold.
        Routes to appropriate clinician based on region.
        """
        if processed_record.risk_score < self.CRITICAL_THRESHOLD:
            return None
        
        # Find available clinician in same county
        clinician = self._route_alert(processed_record.geographic_region)
        
        # Extract top features for explainability
        top_features = self._extract_top_features(processed_record)
        
        alert = PatientRiskAlert.objects.create(
            anonymous_id=processed_record.anonymous_id,
            risk_score=processed_record.risk_score,
            risk_level=processed_record.risk_level,
            sti_probabilities=processed_record.sti_labels,
            top_features=top_features,
            assigned_clinician=clinician,
            facility_county=processed_record.geographic_region
        )
        
        return alert
    
    def _route_alert(self, county: str) -> Optional[ClinicianProfile]:
        """Route alert to least-burdened verified clinician in county"""
        clinicians = ClinicianProfile.objects.filter(
            facility_county=county,
            verification_status=VerificationStatus.VERIFIED,
            can_view_patient_risk=True
        ).annotate(
            open_alerts=Count('assigned_alerts', filter=Q(assigned_alerts__status__in=["new", "acknowledged", "under_review"]))
        ).order_by('open_alerts')
        
        return clinicians.first()
    
    def _extract_top_features(self, record: ProcessedRecord) -> List[Dict]:
        """Extract top 3 contributing features for SHAP-like explainability"""
        # Simplified — in production this comes from actual SHAP values
        features = []
        
        symptoms = record.symptoms.get("vector", [])
        symptom_names = [
            "genital_discharge", "painful_urination", "genital_sores", 
            "pelvic_pain", "fever", "rash", "swollen_lymph_nodes"
        ]
        
        for i, val in enumerate(symptoms[:7]):
            if val == 1:
                features.append({
                    "feature": symptom_names[i],
                    "contribution": "positive",
                    "description": f"Patient reports {symptom_names[i].replace('_', ' ')}"
                })
        
        # Add risk behaviour features
        if record.composite_risk_score:
            features.append({
                "feature": "composite_risk_score",
                "contribution": "positive" if record.composite_risk_score > 0.5 else "neutral",
                "value": round(record.composite_risk_score, 3),
                "description": "Behavioural risk assessment"
            })
        
        return features[:3]
    
    def get_clinician_alerts(self, clinician: ClinicianProfile, 
                             status_filter: Optional[str] = None) -> Dict:
        """Get alerts for clinician dashboard"""
        alerts = PatientRiskAlert.objects.filter(
            assigned_clinician=clinician
        )
        
        if status_filter:
            alerts = alerts.filter(status=status_filter)
        
        # Calculate summary statistics
        summary = {
            "total_new": alerts.filter(status="new").count(),
            "total_acknowledged": alerts.filter(status="acknowledged").count(),
            "total_under_review": alerts.filter(status="under_review").count(),
            "total_critical_unacknowledged": alerts.filter(
                status="new", risk_level="critical"
            ).count(),
            "avg_risk_score": alerts.filter(status="new").aggregate(
                avg=Avg('risk_score')
            )['avg']
        }
        
        return {
            **summary,
            "alerts": list(alerts.order_by("-triggered_at")[:50])
        }
    
    def process_alert_action(self, alert_id: uuid.UUID, clinician: ClinicianProfile,
                            action: str, notes: str = "", **kwargs) -> PatientRiskAlert:
        """Process clinician action on alert"""
        alert = PatientRiskAlert.objects.get(alert_id=alert_id)
        
        # Verify clinician owns this alert or can override
        if alert.assigned_clinician != clinician and not clinician.can_override_threshold:
            raise PermissionError("Not authorized to act on this alert")
        
        now = timezone.now()
        
        if action == "acknowledge":
            alert.status = "acknowledged"
            alert.acknowledged_at = now
        elif action == "review":
            alert.status = "under_review"
            alert.reviewed_at = now
        elif action == "escalate":
            alert.status = "escalated"
            # Reassign to infectious disease specialist
            ids = ClinicianProfile.objects.filter(
                role="ids",
                verification_status=VerificationStatus.VERIFIED
            ).first()
            if ids:
                alert.assigned_clinician = ids
        elif action == "resolve":
            alert.status = "resolved"
            alert.resolved_at = now
        elif action == "override":
            if not clinician.can_override_threshold:
                raise PermissionError("Not authorized to override thresholds")
            alert.status = "resolved"
            alert.resolved_at = now
            alert.clinician_notes = f"THRESHOLD OVERRIDE: {kwargs.get('override_reason', '')}\n{notes}"
        
        if notes and action != "override":
            alert.clinician_notes = notes
        
        if kwargs.get("test_orders"):
            alert.test_orders = kwargs["test_orders"]
        
        if kwargs.get("referral_destination"):
            alert.referral_made = True
            alert.referral_destination = kwargs["referral_destination"]
        
        alert.save()
        return alert

class PopulationDashboardService:
    """
    Population-level risk intelligence for clinicians.
    Spec Section 7.2: Aggregate risk profile for patient population.
    """
    
    def generate_weekly_summary(self, county: str, 
                                 sub_county: Optional[str] = None) -> PopulationRiskSummary:
        """Generate weekly population risk summary"""
        week_start = date.today() - timedelta(days=7)
        week_end = date.today()
        
        # Get all processed records for this region in the past week
        records = ProcessedRecord.objects.filter(
            geographic_region=county,
            created_at__date__gte=week_start,
            created_at__date__lte=week_end
        )
        
        if sub_county:
            # Filter by sub_county if available in demographics
            records = records.filter(demographics__sub_county=sub_county)
        
        # Calculate risk distribution
        risk_counts = records.values('risk_level').annotate(count=Count('risk_level'))
        risk_distribution = {r['risk_level']: r['count'] for r in risk_counts}
        
        # STI distribution
        sti_counts = defaultdict(int)
        for record in records:
            for sti, prob in (record.sti_labels or {}).items():
                if prob > 0.5:
                    sti_counts[sti] += 1
        
        # Alert statistics
        alerts = PatientRiskAlert.objects.filter(
            facility_county=county,
            triggered_at__date__gte=week_start
        )
        
        new_alerts = alerts.filter(status="new").count()
        resolved = alerts.filter(status="resolved", resolved_at__date__gte=week_start).count()
        
        # Calculate week-over-week delta
        prev_week_start = week_start - timedelta(days=7)
        prev_critical = PatientRiskAlert.objects.filter(
            facility_county=county,
            triggered_at__date__gte=prev_week_start,
            triggered_at__date__lt=week_start,
            risk_level="critical"
        ).count()
        
        current_critical = risk_distribution.get("critical", 0)
        if prev_critical > 0:
            wow_delta = ((current_critical - prev_critical) / prev_critical) * 100
        else:
            wow_delta = None
        
        summary, created = PopulationRiskSummary.objects.update_or_create(
            facility_county=county,
            facility_sub_county=sub_county or "",
            reporting_period_end=week_end,
            defaults={
                "reporting_period_start": week_start,
                "total_patients_assessed": records.count(),
                "low_risk_count": risk_distribution.get("low", 0),
                "moderate_risk_count": risk_distribution.get("moderate", 0),
                "high_risk_count": risk_distribution.get("high", 0),
                "critical_risk_count": risk_distribution.get("critical", 0),
                "sti_distribution": dict(sti_counts),
                "new_alerts_this_period": new_alerts,
                "resolved_alerts_this_period": resolved,
                "week_over_week_delta": wow_delta
            }
        )
        
        return summary
    
    def get_differential_diagnosis(self, symptoms: List[str], 
                                   demographics: Dict,
                                   region: str) -> Dict:
        """
        Symptom-driven differential: ranked STI differentials with probability scores.
        Spec Section 7.2: Symptom-driven differential with probability scores.
        """
        # This would integrate with the ML model in production
        # For now, rule-based scoring from guidance engine
        
        guidance_service = GuidanceService()
        
        # Match symptoms to guidance patterns
        matched_guidance = guidance_service.match_guidance_to_symptoms(symptoms, "high")
        
        # Build ranked differentials
        differentials = []
        for guidance in matched_guidance[:5]:
            differentials.append({
                "sti_type": guidance.sti_type,
                "probability_estimate": 0.75,  # Would come from ML model
                "key_symptoms": guidance.symptom_pattern.get("required", []),
                "recommended_tests": guidance.recommended_tests,
                "guidance_id": str(guidance.guidance_id)
            })
        
        # Determine urgency
        critical_symptoms = ["genital_sores", "pelvic_pain", "fever", "swollen_lymph_nodes"]
        has_critical = any(s in critical_symptoms for s in symptoms)
        
        urgency = "emergency" if has_critical else "urgent" if len(symptoms) > 3 else "routine"
        
        # Get recommended guidance
        primary_guidance = matched_guidance[0] if matched_guidance else None
        
        return {
            "ranked_differentials": differentials,
            "recommended_guidance_id": primary_guidance.guidance_id if primary_guidance else None,
            "recommended_tests": primary_guidance.recommended_tests if primary_guidance else [],
            "urgency_level": urgency
        }

class AuditService:
    """
    Immutable audit logging for regulatory compliance.
    Spec Section 3.1: Required for regulatory review.
    """
    
    def log_action(self, clinician: ClinicianProfile, action_type: str,
                   anonymous_id: Optional[str] = None,
                   risk_score: Optional[float] = None,
                   guidance_version: Optional[int] = None,
                   model_version: Optional[str] = None,
                   request_meta: Optional[Dict] = None):
        """Log clinician action for audit trail"""
        
        AuditLog.objects.create(
            clinician=clinician,
            action_type=action_type,
            anonymous_id=anonymous_id or "",
            risk_score=risk_score,
            guidance_version=guidance_version,
            model_version=model_version,
            ip_address=request_meta.get("ip") if request_meta else None,
            user_agent=request_meta.get("user_agent") if request_meta else None
        )
    
    def get_audit_trail(self, anonymous_id: Optional[str] = None,
                        clinician: Optional[ClinicianProfile] = None,
                        start_date: Optional[date] = None,
                        end_date: Optional[date] = None) -> List[AuditLog]:
        """Retrieve audit trail for regulatory review"""
        queryset = AuditLog.objects.all()
        
        if anonymous_id:
            queryset = queryset.filter(anonymous_id=anonymous_id)
        if clinician:
            queryset = queryset.filter(clinician=clinician)
        if start_date:
            queryset = queryset.filter(timestamp__date__gte=start_date)
        if end_date:
            queryset = queryset.filter(timestamp__date__lte=end_date)
        
        return list(queryset.order_by("-timestamp")[:1000])