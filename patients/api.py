from ninja import Router, NinjaAPI
from django.shortcuts import get_object_or_404
from typing import List, Optional
from datetime import date, datetime
from uuid import UUID
import uuid

from .schemas import (
    SessionCreate, SessionOut, SessionResume,
    AssessmentRequest, AssessmentResponse,
    SymptomQuestion, ClinicFinderRequest, ClinicOut,
    ReminderSchedule, ReminderOut,
    ResultEntry, ResultTrendOut
)
from .services import (
    PrivacyGuard, AssessmentService, EducationService,
    ReminderService, ResultTrackingService
)
from .models import AnonymousSession, PatientAssessment, SessionStatus, PatientEducationContent
from django.utils import timezone

api = NinjaAPI(
    title="STI Patient Dashboard API",
    version="1.0",
    urls_namespace="patients"
)
router = Router()

# --- Session Management ---

@router.post("/session/create", response=SessionOut, tags=["Session"])
def create_session(request, payload: SessionCreate):
    """
    Create new anonymous session.
    No personal information collected — ever.
    """
    # Hash device fingerprint for rate limiting (privacy-preserving)
    user_agent = request.META.get("HTTP_USER_AGENT", "")
    ip_hash = str(hash(request.META.get("REMOTE_ADDR", "")))
    device_hash = PrivacyGuard.hash_device_fingerprint(user_agent, ip_hash)
    
    session = PrivacyGuard.create_session(
        county=payload.county,
        device_hash=device_hash
    )
    
    return SessionOut(
        session_id=session.session_id,
        created_at=session.created_at,
        expires_at=session.expires_at,
        status=session.status,
        assessment_count=0
    )

@router.post("/session/resume", response=SessionOut, tags=["Session"])
def resume_session(request, payload: SessionResume):
    """Resume existing anonymous session"""
    try:
        session = AnonymousSession.objects.get(
            session_id=payload.session_id,
            status__in=[SessionStatus.ACTIVE, SessionStatus.COMPLETED]
        )
        
        if session.is_expired():
            session.status = SessionStatus.EXPIRED
            session.save()
            raise Exception("Session has expired. Please start a new assessment.")
        
        # Update activity
        session.last_activity = timezone.now()
        session.save()
        
        return SessionOut(
            session_id=session.session_id,
            created_at=session.created_at,
            expires_at=session.expires_at,
            status=session.status,
            assessment_count=session.assessments.count()
        )
        
    except AnonymousSession.DoesNotExist:
        raise Exception("Session not found")

# --- Symptom Checklist ---

@router.get("/symptoms/questions", response=List[SymptomQuestion], tags=["Assessment"])
def get_symptom_questions(request, language: str = "en"):
    """
    Get the 32-item symptom checklist questions.
    Mobile-optimized, plain language.
    """
    # In production, these would come from a translated database
    questions = [
        SymptomQuestion(
            symptom_id="genital_discharge",
            question_text="Do you have any unusual discharge from your penis or vagina?",
            category="genital",
            help_text="Unusual color, smell, or amount"
        ),
        SymptomQuestion(
            symptom_id="painful_urination",
            question_text="Does it hurt or burn when you urinate?",
            category="urinary"
        ),
        SymptomQuestion(
            symptom_id="genital_sores",
            question_text="Do you have any sores, blisters, or lumps on your genitals?",
            category="genital"
        ),
        SymptomQuestion(
            symptom_id="pelvic_pain",
            question_text="Do you have pain in your lower abdomen or pelvis?",
            category="genital"
        ),
        SymptomQuestion(
            symptom_id="testicular_pain",
            question_text="Do you have pain or swelling in your testicles?",
            category="genital"
        ),
        # ... remaining 27 symptoms
        SymptomQuestion(
            symptom_id="fever",
            question_text="Have you had a fever in the past 2 weeks?",
            category="systemic"
        ),
        SymptomQuestion(
            symptom_id="rash",
            question_text="Do you have a rash on your body, palms, or soles of feet?",
            category="systemic"
        ),
        SymptomQuestion(
            symptom_id="swollen_lymph_nodes",
            question_text="Do you have swollen glands in your neck, armpits, or groin?",
            category="systemic"
        ),
    ]
    
    return questions

# --- Risk Assessment ---

@router.post("/assess", response=AssessmentResponse, tags=["Assessment"])
def submit_assessment(request, payload: AssessmentRequest):
    """
    Submit complete assessment and get risk score.
    This is the core patient-facing endpoint.
    """
    # Validate session
    session = AnonymousSession.objects.filter(
        session_id=payload.session_id or uuid.uuid4()  # Create implicit if needed
    ).first()
    
    if not session:
        # Create new session implicitly
        session = PrivacyGuard.create_session(
            county=payload.demographics.county
        )
    
    if session.is_expired():
        raise Exception("Session expired. Please start new assessment.")
    
    # Process assessment
    service = AssessmentService()
    result = service.process_assessment(
        session=session,
        symptoms=[r.dict() for r in payload.symptoms.responses],
        behaviours=payload.behaviours.dict(),
        demographics=payload.demographics.dict()
    )
    
    # Get education content
    edu_service = EducationService()
    explanation = edu_service.format_explanation(
        risk_level=result["risk_level"],
        risk_score=result["risk_score"],
        factors=result["top_factors"],
        language=payload.language
    )
    
    # Find nearest clinics
    from geospatial.services import FacilityFinder
    facility_finder = FacilityFinder()
    clinics = facility_finder.find_nearest(
        lat=-1.2921,  # Would use county centroid in production
        lon=36.8219,
        sti_type=None,
        max_distance_km=50.0,
        limit=5
    )
    
    # Schedule reminders if consented
    if payload.consent_reminders:
        reminder_service = ReminderService()
        reminder_service.schedule_reminder(session, "1_week")
    
    return AssessmentResponse(
        assessment_id=result["assessment_id"],
        session_id=session.session_id,
        overall_risk_level=result["risk_level"],
        overall_risk_score=result["risk_score"],
        sti_risks=[
            {"sti_type": sti, "probability": prob, "level": "elevated" if prob > 0.5 else "low"}
            for sti, prob in result["sti_probabilities"].items()
        ],
        top_factors=result["top_factors"],
        explanation=explanation["explanation"],
        what_this_means=explanation["title"],
        what_to_do_next=explanation["next_steps"],
        mandatory_clinical_review=result["risk_level"] == "critical",
        nearest_clinics=[
            {
                "name": c["name"],
                "distance_km": c["distance_km"],
                "services": c["services"],
                "walk_in": c.get("walk_in_accepted", True)
            }
            for c in clinics
        ],
        disclaimer="This is a risk assessment, not a diagnosis. Only a licensed clinician can diagnose STIs."
    )

# --- Clinic Finder ---

@router.post("/clinics/nearby", response=List[ClinicOut], tags=["Clinic Finder"])
def find_clinics(request, payload: ClinicFinderRequest):
    """
    Find nearest MOH-registered testing clinics.
    Spec Section 7.1: Testing location finder.
    """
    from geospatial.services import FacilityFinder
    
    # Use county centroid for privacy (no exact GPS from patient)
    county_centroids = {
        "Nairobi": (-1.2921, 36.8219),
        "Mombasa": (-4.0435, 39.6682),
        "Kisumu": (-0.1022, 34.7617),
        # ... add all 47 counties
    }
    
    lat, lon = county_centroids.get(payload.county, (-1.2921, 36.8219))
    
    finder = FacilityFinder()
    results = finder.find_nearest(
        lat=lat,
        lon=lon,
        sti_type=payload.sti_concern,
        max_distance_km=payload.max_distance_km,
        limit=10
    )
    
    return [
        ClinicOut(
            facility_id=r["facility_id"],
            name=r["name"],
            county=r["county"],
            sub_county=r["sub_county"],
            services=r["services"],
            distance_km=r["distance_km"],
            operating_hours=r.get("operating_hours", {}),
            contact_phone=r.get("contact_phone"),
            walk_in_accepted=True,
            appointment_required=False
        )
        for r in results
    ]

# --- Result Tracking ---

@router.post("/results/track", tags=["Result Tracking"])
def add_test_result(request, session_id: str, payload: ResultEntry):
    """
    Add self-reported test result for anonymous tracking.
    Spec Section 7.1: Anonymised result tracking over time.
    """
    session = AnonymousSession.objects.get(session_id=session_id)
    
    if not session.consent_result_tracking:
        raise Exception("Result tracking not consented. Please enable in session settings.")
    
    service = ResultTrackingService()
    entry = service.add_result(
        session=session,
        test_date=payload.test_date,
        test_type=payload.test_type,
        result=payload.result,
        notes=payload.notes or ""
    )
    
    return {
        "tracking_id": str(entry.tracking_id),
        "status": "recorded",
        "message": "Your result has been recorded anonymously."
    }

@router.get("/results/trend", response=ResultTrendOut, tags=["Result Tracking"])
def get_result_trend(request, session_id: str):
    """Get anonymous result trend over time"""
    session = AnonymousSession.objects.get(session_id=session_id)
    
    service = ResultTrackingService()
    trend = service.get_trend(session)
    
    return ResultTrendOut(**trend)

# --- Reminders ---

@router.post("/reminders/schedule", response=ReminderOut, tags=["Reminders"])
def schedule_reminder(request, session_id: str, payload: ReminderSchedule):
    """
    Schedule consent-based testing reminder.
    Patient must proactively check back — no SMS/email stored.
    """
    session = AnonymousSession.objects.get(session_id=session_id)
    
    if not session.consent_testing_reminder:
        raise Exception("Testing reminders not consented.")
    
    service = ReminderService()
    reminder = service.schedule_reminder(session, payload.reminder_type)
    
    return ReminderOut(
        reminder_id=reminder.reminder_id,
        scheduled_date=reminder.scheduled_date,
        reminder_type=reminder.reminder_type,
        status="scheduled"
    )

@router.get("/reminders/pending", response=List[ReminderOut], tags=["Reminders"])
def get_pending_reminders(request, session_id: str):
    """Get pending reminders (patient proactively checks)"""
    session = AnonymousSession.objects.get(session_id=session_id)
    
    service = ReminderService()
    reminders = service.get_pending_reminders(session)
    
    return [
        ReminderOut(
            reminder_id=r.reminder_id,
            scheduled_date=r.scheduled_date,
            reminder_type=r.reminder_type,
            status="due" if not r.sent else "sent"
        )
        for r in reminders
    ]

# Register router
api.add_router("/", router)