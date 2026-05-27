from ninja import Router, NinjaAPI
from ninja.security import HttpBearer
from django.shortcuts import get_object_or_404
from typing import List, Optional
from datetime import date

from .schemas import (
    ClinicianRegistration, ClinicianProfileOut, ClinicianVerification,
    GuidanceDraft, GuidanceReview, GuidanceOut,
    RiskAlertOut, AlertAction, AlertSummary,
    PopulationSummaryOut, SymptomDifferentialRequest, SymptomDifferentialOut,
    AuditEntryOut, WeeklyReportOut
)
from .services import GuidanceService, AlertService, PopulationDashboardService, AuditService
from .permissions import ClinicianAuth, RoleBasedAccess, require_verified_clinician
from .models import ClinicianProfile, ClinicalGuidance, PatientRiskAlert, VerificationStatus

api = NinjaAPI(title="STI Clinician API", version="1.0", urls_namespace="clinicians-api")
router = Router()

# Authentication instance
auth = ClinicianAuth()

@router.post("/register", tags=["Authentication"])
def register_clinician(request, payload: ClinicianRegistration):
    """
    Register new clinician. Requires manual verification by MOH.
    """
    from django.contrib.auth.models import User
    
    user = User.objects.create_user(
        username=payload.username,
        email=payload.email,
        password=payload.password,
        first_name=payload.first_name,
        last_name=payload.last_name
    )
    
    profile = ClinicianProfile.objects.create(
        user=user,
        role=payload.role,
        license_number=payload.license_number,
        license_issuing_body=payload.license_issuing_body,
        license_expiry_date=payload.license_expiry_date,
        specialization=payload.specialization or "",
        facility_name=payload.facility_name,
        facility_county=payload.facility_county,
        facility_sub_county=payload.facility_sub_county,
        verification_status=VerificationStatus.PENDING
    )
    
    return {
        "clinician_id": str(profile.clinician_id),
        "status": "pending_verification",
        "message": "Your account is pending MOH verification. You will be notified once approved."
    }

@router.get("/profile", response=ClinicianProfileOut, auth=auth, tags=["Profile"])
def get_profile(request):
    """Get current clinician profile"""
    profile = require_verified_clinician(request)
    
    return ClinicianProfileOut(
        clinician_id=profile.clinician_id,
        full_name=f"{profile.user.first_name} {profile.user.last_name}",
        role=profile.role,
        role_display=profile.get_role_display(),
        license_number=profile.license_number,
        verification_status=profile.verification_status,
        facility_name=profile.facility_name,
        facility_county=profile.facility_county,
        can_view_population_data=RoleBasedAccess.can_view_population_data(profile),
        can_approve_guidance=RoleBasedAccess.can_approve_guidance(profile),
        can_override_threshold=RoleBasedAccess.can_override_threshold(profile)
    )

@router.get("/alerts", response=AlertSummary, auth=auth, tags=["Alerts"])
def get_alerts(request, status: Optional[str] = None):
    """
    Get patient risk alerts for clinician dashboard.
    Score > 0.7 triggers mandatory review per Section 3.2.
    """
    profile = require_verified_clinician(request)
    
    service = AlertService()
    result = service.get_clinician_alerts(profile, status)
    
    alerts_out = [
        RiskAlertOut(
            alert_id=a.alert_id,
            anonymous_id=a.anonymous_id,
            risk_score=a.risk_score,
            risk_level=a.risk_level,
            sti_probabilities=a.sti_probabilities,
            top_features=a.top_features,
            status=a.status,
            triggered_at=a.triggered_at,
            clinician_notes=a.clinician_notes or None,
            recommended_action=a.recommended_action or None
        )
        for a in result["alerts"]
    ]
    
    return AlertSummary(
        total_new=result["total_new"],
        total_acknowledged=result["total_acknowledged"],
        total_under_review=result["total_under_review"],
        total_critical_unacknowledged=result["total_critical_unacknowledged"],
        avg_risk_score=result["avg_risk_score"],
        alerts=alerts_out
    )

@router.post("/alerts/{alert_id}/action", response=RiskAlertOut, auth=auth, tags=["Alerts"])
def process_alert_action(request, alert_id: str, payload: AlertAction):
    """Process clinician action on a patient risk alert"""
    profile = require_verified_clinician(request)
    
    service = AlertService()
    alert = service.process_alert_action(
        alert_id=alert_id,
        clinician=profile,
        action=payload.action,
        notes=payload.clinician_notes or "",
        test_orders=payload.test_orders,
        referral_destination=payload.referral_destination,
        override_reason=payload.override_reason
    )
    
    # Log the action
    audit = AuditService()
    audit.log_action(
        clinician=profile,
        action_type=f"alert_{payload.action}",
        anonymous_id=alert.anonymous_id,
        risk_score=alert.risk_score,
        request_meta={"ip": request.META.get("REMOTE_ADDR"), "user_agent": request.META.get("HTTP_USER_AGENT")}
    )
    
    return RiskAlertOut(
        alert_id=alert.alert_id,
        anonymous_id=alert.anonymous_id,
        risk_score=alert.risk_score,
        risk_level=alert.risk_level,
        sti_probabilities=alert.sti_probabilities,
        top_features=alert.top_features,
        status=alert.status,
        triggered_at=alert.triggered_at,
        clinician_notes=alert.clinician_notes or None,
        recommended_action=alert.recommended_action or None
    )

@router.get("/guidance/active", response=List[GuidanceOut], auth=auth, tags=["Clinical Guidance"])
def get_active_guidance(request, sti_type: Optional[str] = None, risk_level: Optional[str] = None):
    """
    Retrieve deployed, MOH-approved clinical guidance.
    Spec Section 8.2: Only validated guidance is surfaced.
    """
    profile = require_verified_clinician(request)
    
    service = GuidanceService()
    
    if sti_type and risk_level:
        guidance = [service.get_active_guidance(sti_type, risk_level)]
    else:
        guidance = ClinicalGuidance.objects.filter(
            validation_status="deployed",
            annual_review_due__gt=date.today()
        ).order_by("sti_type", "risk_level")
    
    return [
        GuidanceOut(
            guidance_id=g.guidance_id,
            title=g.title,
            sti_type=g.sti_type,
            risk_level=g.risk_level,
            differential_diagnosis=g.differential_diagnosis,
            recommended_tests=g.recommended_tests,
            treatment_protocol=g.treatment_protocol,
            referral_criteria=g.referral_criteria,
            patient_counseling_points=g.patient_counseling_points,
            validation_status=g.validation_status,
            version=g.version,
            moh_approved=bool(g.moh_signatory),
            deployed_at=g.deployed_at
        )
        for g in guidance if g
    ]

@router.post("/guidance/draft", auth=auth, tags=["Clinical Guidance"])
def draft_guidance(request, payload: GuidanceDraft):
    """
    Draft new clinical guidance. Requires validation gate before deployment.
    Spec Section 8.2: Hard constraint — no ML advice without validation.
    """
    profile = require_verified_clinician(request)
    
    if not RoleBasedAccess.can_approve_guidance(profile):
        raise Exception("Not authorized to draft clinical guidance")
    
    guidance = ClinicalGuidance.objects.create(
        title=payload.title,
        sti_type=payload.sti_type,
        risk_level=payload.risk_level,
        symptom_pattern=payload.symptom_pattern,
        differential_diagnosis=payload.differential_diagnosis,
        recommended_tests=payload.recommended_tests,
        treatment_protocol=payload.treatment_protocol,
        referral_criteria=payload.referral_criteria,
        patient_counseling_points=payload.patient_counseling_points,
        drafted_by=f"Dr. {profile.user.get_full_name()} ({profile.license_number})",
        validation_status="draft"
    )
    
    return {
        "guidance_id": str(guidance.guidance_id),
        "status": "draft",
        "next_step": "Requires review by two licensed clinicians"
    }

@router.post("/guidance/review", auth=auth, tags=["Clinical Guidance"])
def review_guidance(request, payload: GuidanceReview):
    """
    Review clinical guidance. Enforces two-clinician + ID specialist + MOH sign-off.
    """
    profile = require_verified_clinician(request)
    
    service = GuidanceService()
    result = service.submit_for_review(
        guidance_id=payload.guidance_id,
        reviewer_name=profile.user.get_full_name(),
        reviewer_credentials=f"{profile.get_role_display()}, License: {profile.license_number}",
        comments=payload.comments or ""
    )
    
    # Log the review action
    audit = AuditService()
    audit.log_action(
        clinician=profile,
        action_type="guidance_reviewed",
        guidance_version=ClinicalGuidance.objects.get(guidance_id=payload.guidance_id).version
    )
    
    return result

@router.post("/differential", response=SymptomDifferentialOut, auth=auth, tags=["Decision Support"])
def get_differential(request, payload: SymptomDifferentialRequest):
    """
    Symptom-driven differential diagnosis with ranked STI probabilities.
    Spec Section 7.2: Ranked STI differentials with probability scores.
    """
    profile = require_verified_clinician(request)
    
    service = PopulationDashboardService()
    result = service.get_differential_diagnosis(
        symptoms=payload.symptoms,
        demographics=payload.demographics,
        region=payload.geographic_region
    )
    
    # Log access
    audit = AuditService()
    audit.log_action(
        clinician=profile,
        action_type="differential_accessed",
        request_meta={"ip": request.META.get("REMOTE_ADDR")}
    )
    
    return SymptomDifferentialOut(**result)

@router.get("/population/summary", response=PopulationSummaryOut, auth=auth, tags=["Population Dashboard"])
def get_population_summary(request, county: Optional[str] = None):
    """
    Aggregate risk profile for patient population.
    Spec Section 7.2: Population-level risk intelligence.
    """
    profile = require_verified_clinician(request)
    
    if not RoleBasedAccess.can_view_population_data(profile):
        raise Exception("Not authorized to view population-level data")
    
    target_county = county or profile.facility_county
    
    service = PopulationDashboardService()
    summary = service.generate_weekly_summary(target_county)
    
    # Determine trend
    trend = "stable"
    if summary.week_over_week_delta is not None:
        if summary.week_over_week_delta > 10:
            trend = "worsening"
        elif summary.week_over_week_delta < -10:
            trend = "improving"
    
    return PopulationSummaryOut(
        summary_id=summary.summary_id,
        reporting_period=f"{summary.reporting_period_start} to {summary.reporting_period_end}",
        total_patients_assessed=summary.total_patients_assessed,
        risk_distribution={
            "low": summary.low_risk_count,
            "moderate": summary.moderate_risk_count,
            "high": summary.high_risk_count,
            "critical": summary.critical_risk_count
        },
        sti_distribution=summary.sti_distribution,
        new_alerts=summary.new_alerts_this_period,
        resolved_alerts=summary.resolved_alerts_this_period,
        week_over_week_delta=summary.week_over_week_delta,
        trend_direction=trend
    )

@router.get("/audit/trail", response=List[AuditEntryOut], auth=auth, tags=["Audit & Compliance"])
def get_audit_trail(request, anonymous_id: Optional[str] = None, 
                    start_date: Optional[date] = None, end_date: Optional[date] = None):
    """
    Retrieve immutable audit log for regulatory review.
    Spec Section 3.1: Required for regulatory review.
    """
    profile = require_verified_clinician(request)
    
    # Only MOH admins can view full audit trails
    if anonymous_id is None and not RoleBasedAccess.is_moh_admin(profile):
        raise Exception("Not authorized to view full audit trail")
    
    service = AuditService()
    logs = service.get_audit_trail(
        anonymous_id=anonymous_id,
        clinician=profile if not RoleBasedAccess.is_moh_admin(profile) else None,
        start_date=start_date,
        end_date=end_date
    )
    
    return [
        AuditEntryOut(
            log_id=l.log_id,
            action_type=l.get_action_type_display(),
            timestamp=l.timestamp,
            anonymous_id=l.anonymous_id or None,
            risk_score=l.risk_score,
            model_version=l.model_version
        )
        for l in logs
    ]

# Register router
api.add_router("/clinicians/", router)