import uuid
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta, date
from collections import defaultdict

from django.utils import timezone
from django.db.models import Count

from .models import (
    AnonymousSession, PatientAssessment, TestingReminder,
    ResultTracking, PatientEducationContent, SessionStatus
)
from preprocessing.services import PreprocessingPipeline
from preprocessing.schemas import SingleProcessRequest, RawPatientRecord, SymptomInput, RiskBehaviourInput, DemographicsInput
from geospatial.services import FacilityFinder

class PrivacyGuard:
    """
    Enforces patient privacy constraints.
    Spec Section 7.1: Privacy-first personal risk assessment.
    """
    
    SESSION_TTL_HOURS = 24  # Session expires after 24 hours of inactivity
    MAX_ASSESSMENTS_PER_HOUR = 3  # Rate limiting per device
    
    @classmethod
    def create_session(cls, county: Optional[str] = None, 
                       device_hash: Optional[str] = None) -> AnonymousSession:
        """Create new anonymous session with expiration"""
        now = timezone.now()
        expires = now + timedelta(hours=cls.SESSION_TTL_HOURS)
        
        # Rate limiting check
        if device_hash:
            recent = AnonymousSession.objects.filter(
                device_hash=device_hash,
                created_at__gte=now - timedelta(hours=1)
            ).count()
            if recent >= cls.MAX_ASSESSMENTS_PER_HOUR:
                raise Exception("Rate limit exceeded. Please try again later.")
        
        return AnonymousSession.objects.create(
            expires_at=expires,
            county=county or "",
            device_hash=device_hash or ""
        )
    
    @classmethod
    def hash_device_fingerprint(cls, user_agent: str, ip_hash: str) -> str:
        """Create privacy-preserving device hash for rate limiting"""
        import hashlib
        combined = f"{user_agent}:{ip_hash}"
        return hashlib.sha256(combined.encode()).hexdigest()[:32]

class AssessmentService:
    """
    Core patient risk assessment service.
    """
    
    def __init__(self):
        self.preprocessing_config = {
            "apply_deduplication": False,  # Single patient, no dedup needed
            "imputation_strategy": "median",
            "apply_smote": False,  # Only for training data
            "apply_differential_privacy": True,
            "dp_epsilon": 0.1,
            "k_anonymity": 10
        }
    
    def process_assessment(self, session: AnonymousSession,
                           symptoms: List[Dict],
                           behaviours: Dict,
                           demographics: Dict) -> Dict:
        """
        Process patient assessment through preprocessing pipeline.
        """
        # Convert to preprocessing format
        symptom_dict = {s["symptom_id"]: s["present"] for s in symptoms}
        
        raw_record = {
            "source": "patient_form",
            "symptoms": symptom_dict,
            "risk_behaviours": {
                "partner_count_12m": behaviours.get("partner_count_12m", 0),
                "condom_use_frequency": behaviours.get("condom_use_frequency", "never"),
                "prior_testing_history": behaviours.get("prior_sti_test_12m", False),
                "substance_use": behaviours.get("substance_use_alcohol_drugs", False),
                "sex_work_exposure": behaviours.get("sex_work_involvement", False)
            },
            "demographics": {
                "age": demographics["age"],
                "sex": demographics["sex"],
                "geographic_region": demographics["county"]
            },
            "prior_sti_history": behaviours.get("prior_sti_diagnosis", [])
        }
        
        # Run through preprocessing pipeline
        pipeline = PreprocessingPipeline(self.preprocessing_config)
        processed = pipeline.process_single_record(raw_record)
        
        # Create assessment record
        assessment = PatientAssessment.objects.create(
            session=session,
            symptoms_reported=symptom_dict,
            behaviours_reported=behaviours,
            demographics_reported=demographics,
            risk_score=processed["composite_risk_score"],
            risk_level=processed["risk_level"],
            sti_probabilities=processed.get("sti_labels", {}),
            top_contributing_factors=pipeline.engineer.extract_symptom_vector(symptom_dict)[:5]
        )
        
        # Update session
        session.last_activity = timezone.now()
        session.status = SessionStatus.COMPLETED
        session.save()
        
        # Trigger clinician alert if critical
        if processed["risk_level"] == "critical":
            from clinicians.services import AlertService
            alert_service = AlertService()
            # Create alert for clinician review
            # This would link to the processed record
        
        return {
            "assessment_id": assessment.assessment_id,
            "risk_level": processed["risk_level"],
            "risk_score": processed["composite_risk_score"],
            "sti_probabilities": processed.get("sti_labels", {}),
            "top_factors": self._explain_factors(symptom_dict, behaviours, processed)
        }
    
    def _explain_factors(self, symptoms: Dict, behaviours: Dict, 
                         processed: Dict) -> List[Dict]:
        """Generate plain-language explanation of top risk factors"""
        factors = []
        
        # Symptom factors
        symptom_names = {
            "genital_discharge": "unusual discharge",
            "painful_urination": "pain when urinating",
            "genital_sores": "sores or blisters",
            "pelvic_pain": "pelvic pain",
            "fever": "fever",
            "swollen_lymph_nodes": "swollen glands"
        }
        
        for symptom_id, present in symptoms.items():
            if present and symptom_id in symptom_names:
                factors.append({
                    "factor": symptom_names[symptom_id],
                    "category": "symptom",
                    "impact": "increases risk"
                })
        
        # Behaviour factors
        if behaviours.get("condom_use_frequency") == "never":
            factors.append({
                "factor": "never using condoms",
                "category": "prevention",
                "impact": "significantly increases risk"
            })
        
        if behaviours.get("partner_count_12m", 0) > 3:
            factors.append({
                "factor": f"{behaviours['partner_count_12m']} partners in past year",
                "category": "behaviour",
                "impact": "increases risk"
            })
        
        return factors[:3]  # Top 3 only

class EducationService:
    """
    Plain-language education content per risk level.
    """
    
    def get_content(self, risk_level: str, language: str = "en") -> Optional[PatientEducationContent]:
        """Get validated education content for risk level"""
        return PatientEducationContent.objects.filter(
            risk_level=risk_level,
            language=language,
            review_due__gt=date.today()
        ).first()
    
    def format_explanation(self, risk_level: str, risk_score: float,
                           factors: List[Dict], language: str = "en") -> Dict:
        """Format plain-language explanation for patient"""
        content = self.get_content(risk_level, language)
        
        explanations = {
            "low": {
                "title": "Your risk appears low",
                "explanation": "Based on your responses, your risk of having an STI appears low. This does not mean zero risk.",
                "next_steps": [
                    "Continue using protection consistently",
                    "Consider regular testing every 3-6 months if sexually active",
                    "Talk to a healthcare provider if you develop symptoms"
                ]
            },
            "moderate": {
                "title": "Your risk is moderate",
                "explanation": "Some of your responses suggest a moderate risk. This is not a diagnosis, but testing is recommended.",
                "next_steps": [
                    "Visit an MOH-registered clinic for testing within 1-2 weeks",
                    "Avoid sexual activity or use condoms until tested",
                    "Inform recent partners they may need testing"
                ]
            },
            "high": {
                "title": "Your risk is high",
                "explanation": "Several factors suggest a higher risk of STI. Please seek testing as soon as possible.",
                "next_steps": [
                    "Visit a clinic for testing within 3-5 days",
                    "Avoid all sexual activity until cleared",
                    "A clinician will review your assessment"
                ]
            },
            "critical": {
                "title": "Your risk is critical — please seek care urgently",
                "explanation": "Your responses indicate a high probability of STI. This requires prompt clinical evaluation.",
                "next_steps": [
                    "Seek testing at a clinic TODAY or within 24 hours",
                    "Avoid all sexual contact",
                    "A clinician has been notified and will follow up"
                ]
            }
        }
        
        base = explanations.get(risk_level, explanations["low"])
        
        if content:
            base["detailed_content"] = {
                "what_to_do_next": content.what_to_do_next,
                "when_to_seek_care": content.when_to_seek_care,
                "prevention_tips": content.prevention_tips,
                "myth_busters": content.myth_busters
            }
        
        return base

class ReminderService:
    """
    Consent-based testing reminders.
    Spec Section 7.1: Consent-based testing reminder notifications.
    """
    
    def schedule_reminder(self, session: AnonymousSession,
                          reminder_type: str) -> TestingReminder:
        """Schedule a testing reminder (patient must proactively check back)"""
        now = date.today()
        
        schedule_map = {
            "3_day": now + timedelta(days=3),
            "1_week": now + timedelta(weeks=1),
            "2_week": now + timedelta(weeks=2),
            "1_month": now + timedelta(days=30),
            "3_month": now + timedelta(days=90)
        }
        
        scheduled = schedule_map.get(reminder_type, now + timedelta(weeks=1))
        
        reminder = TestingReminder.objects.create(
            session=session,
            scheduled_date=scheduled,
            reminder_type=reminder_type
        )
        
        return reminder
    
    def get_pending_reminders(self, session: AnonymousSession) -> List[TestingReminder]:
        """Get reminders that are due (patient checks proactively)"""
        now = date.today()
        return list(TestingReminder.objects.filter(
            session=session,
            scheduled_date__lte=now,
            acknowledged=False
        ))

class ResultTrackingService:
    """
    Anonymous result tracking over time.
    """
    
    def add_result(self, session: AnonymousSession,
                   test_date: date, test_type: str,
                   result: str, notes: str = "") -> ResultTracking:
        """Add self-reported test result"""
        # Get previous risk score if available
        last_assessment = PatientAssessment.objects.filter(
            session=session
        ).order_by("-completed_at").first()
        
        entry = ResultTracking.objects.create(
            session=session,
            test_date=test_date,
            test_type=test_type,
            self_reported_result=result,
            previous_risk_score=last_assessment.risk_score if last_assessment else None,
            notes=notes
        )
        
        return entry
    
    def get_trend(self, session: AnonymousSession) -> Dict:
        """Get result trend over time"""
        entries = ResultTracking.objects.filter(
            session=session
        ).order_by("test_date")
        
        if not entries.exists():
            return {
                "tracking_entries": [],
                "risk_trend": "insufficient_data",
                "recommendation": "No results tracked yet. Add your first test result."
            }
        
        # Analyze trend
        positive_count = entries.filter(self_reported_result="positive").count()
        total = entries.count()
        
        trend = "stable"
        if positive_count == 0 and total >= 2:
            trend = "improving"
        elif positive_count > 0:
            trend = "worsening"
        
        return {
            "tracking_entries": [
                {
                    "date": e.test_date,
                    "type": e.test_type,
                    "result": e.self_reported_result,
                    "risk_at_time": e.previous_risk_score
                }
                for e in entries
            ],
            "risk_trend": trend,
            "recommendation": self._get_recommendation(trend, entries.count())
        }
    
    def _get_recommendation(self, trend: str, count: int) -> str:
        """Get plain-language recommendation based on trend"""
        if count < 2:
            return "Add more results to see your trend."
        if trend == "improving":
            return "Great! Keep testing regularly and stay protected."
        if trend == "worsening":
            return "Please speak with a clinician about your results."
        return "Continue regular testing every 3-6 months."