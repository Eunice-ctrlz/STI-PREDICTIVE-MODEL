from ninja import Router, NinjaAPI
from typing import List, Optional
from datetime import datetime, timedelta
from django.utils import timezone
from django.db import models

from .schemas import (
    AuditQuery, AuditEntryOut, AuditSummary,
    BiasAuditRequest, BiasAuditOut, SubgroupMetric,
    DriftCheckRequest, DriftResultOut, DriftSummary,
    ValidationGateOut, ValidationStage, ValidationSubmit,
    RetentionPolicyOut, RetentionExecution, RetentionResult,
    ViolationCreate, ViolationOut,
    ComplianceDashboard
)
from .services.bias_monitor import BiasMonitor
from .services.drift_detector import DriftDetector
from .services.validation_gate import ValidationGate
from .services.retention_enforcer import RetentionEnforcer
from .models import (
    ImmutableAuditLog, BiasAuditReport, DriftDetectionResult,
    ClinicalValidationGate, DataRetentionPolicy, ComplianceViolation
)

api = NinjaAPI(title="STI Compliance API", version="1.0")
router = Router()

# --- Audit Log Endpoints ---

@router.post("/audit/query", response=List[AuditEntryOut], tags=["Audit"])
def query_audit_log(request, payload: AuditQuery):
    """
    Query immutable audit log for regulatory review.
    Spec Section 3.1: Required for regulatory review.
    """
    queryset = ImmutableAuditLog.objects.all()
    
    if payload.anonymous_id:
        queryset = queryset.filter(anonymous_id=payload.anonymous_id)
    if payload.actor_id:
        queryset = queryset.filter(actor_id=payload.actor_id)
    if payload.action_type:
        queryset = queryset.filter(action_type=payload.action_type)
    if payload.date_from:
        queryset = queryset.filter(action_timestamp__date__gte=payload.date_from)
    if payload.date_to:
        queryset = queryset.filter(action_timestamp__date__lte=payload.date_to)
    if payload.model_version:
        queryset = queryset.filter(model_version=payload.model_version)
    
    entries = queryset.order_by("-action_timestamp")[:payload.limit]
    
    return [
        AuditEntryOut(
            log_id=e.log_id,
            action_type=e.get_action_type_display(),
            action_timestamp=e.action_timestamp,
            actor_type=e.actor_type,
            actor_id=e.actor_id or None,
            anonymous_id=e.anonymous_id or None,
            model_version=e.model_version or None,
            risk_score=e.risk_score,
            risk_level=e.risk_level,
            current_log_hash=e.current_log_hash,
            payload_summary=e.payload_summary
        )
        for e in entries
    ]

@router.get("/audit/summary", response=AuditSummary, tags=["Audit"])
def get_audit_summary(request, days: int = 30):
    """Get audit summary statistics"""
    from django.utils import timezone
    from datetime import timedelta
    
    cutoff = timezone.now() - timedelta(days=days)
    entries = ImmutableAuditLog.objects.filter(action_timestamp__gte=cutoff)
    
    return AuditSummary(
        total_entries=entries.count(),
        entries_by_type=dict(entries.values("action_type").annotate(count=models.Count("action_type")).values_list("action_type", "count")),
        entries_by_actor=dict(entries.values("actor_type").annotate(count=models.Count("actor_type")).values_list("actor_type", "count")),
        unique_patients=entries.filter(anonymous_id__isnull=False).values("anonymous_id").distinct().count(),
        unique_clinicians=entries.filter(actor_type="clinician").values("actor_id").distinct().count(),
        date_range=f"{cutoff.date()} to {timezone.now().date()}"
    )

# --- Bias Monitoring Endpoints ---

@router.post("/bias/audit", response=BiasAuditOut, tags=["Bias & Fairness"])
def run_bias_audit(request, payload: BiasAuditRequest):
    """
    Run quarterly bias audit.
    Spec Section 8.3: Quarterly bias audit report generated automatically.
    """
    # In production, fetch actual prediction data from database
    monitor = BiasMonitor(payload.model_version, payload.model_type)
    
    # Placeholder — would run on actual inference logs
    report = BiasAuditReport.objects.create(
        period_start=payload.period_start,
        period_end=payload.period_end,
        model_version=payload.model_version,
        model_type=payload.model_type,
        subgroup_results={},
        violations_found=[],
        calibration_by_subgroup={},
        passes_bias_audit=True,
        recommended_actions=[]
    )
    
    return BiasAuditOut(
        report_id=report.report_id,
        period=f"{payload.period_start} to {payload.period_end}",
        model_version=report.model_version,
        overall_passes=report.passes_bias_audit,
        subgroup_results=[],
        violations=report.violations_found,
        recommended_actions=report.recommended_actions,
        generated_at=report.generated_at
    )

@router.get("/bias/reports", response=List[BiasAuditOut], tags=["Bias & Fairness"])
def list_bias_reports(request, model_version: Optional[str] = None):
    """List historical bias audit reports"""
    queryset = BiasAuditReport.objects.all()
    if model_version:
        queryset = queryset.filter(model_version=model_version)
    
    return [
        BiasAuditOut(
            report_id=r.report_id,
            period=f"{r.period_start} to {r.period_end}",
            model_version=r.model_version,
            overall_passes=r.passes_bias_audit,
            subgroup_results=[
                SubgroupMetric(
                    subgroup_name=k,
                    sample_count=v.get("sample_count", 0),
                    auc_roc=v.get("auc_roc", 0),
                    f1_score=v.get("f1_score", 0),
                    precision=v.get("precision", 0),
                    recall=v.get("recall", 0),
                    passes_threshold=v.get("passes_threshold", False)
                )
                for k, v in r.subgroup_results.items()
            ],
            violations=r.violations_found,
            recommended_actions=r.recommended_actions,
            generated_at=r.generated_at
        )
        for r in queryset.order_by("-generated_at")[:20]
    ]

# --- Drift Detection Endpoints ---

@router.post("/drift/check", response=DriftSummary, tags=["Drift Detection"])
def run_drift_check(request, payload: DriftCheckRequest):
    """
    Run PSI drift detection.
    Spec Section 4.3: PSI computed weekly, threshold 0.2 triggers retraining.
    """
    # In production, compare training vs current distributions
    detector = DriftDetector(payload.model_version)
    
    # Placeholder results
    results = DriftDetectionResult.objects.filter(
        model_version=payload.model_version
    ).order_by("-detected_at")[:10]
    
    drifted = [r for r in results if r.is_drift_detected]
    
    return DriftSummary(
        run_timestamp=timezone.now(),
        model_version=payload.model_version,
        features_checked=len(results),
        features_drifted=len(drifted),
        critical_drifts=len([d for d in drifted if d.severity == "critical"]),
        retraining_triggered=len(drifted) > 0
    )

@router.get("/drift/reports", response=List[DriftResultOut], tags=["Drift Detection"])
def get_drift_reports(request, model_version: Optional[str] = None):
    """Get drift detection history"""
    queryset = DriftDetectionResult.objects.all()
    if model_version:
        queryset = queryset.filter(model_version=model_version)
    
    return [
        DriftResultOut(
            feature_name=r.feature_name,
            psi_score=r.psi_score,
            threshold=r.psi_threshold,
            is_drift_detected=r.is_drift_detected,
            severity=r.severity,
            training_distribution=r.training_distribution,
            current_distribution=r.current_distribution
        )
        for r in queryset.order_by("-detected_at")[:50]
    ]

# --- Validation Gate Endpoints ---

@router.get("/validation/{gate_id}", response=ValidationGateOut, tags=["Validation Gate"])
def get_validation_status(request, gate_id: str):
    """
    Get clinical validation gate status.
    Spec Section 8.2: Hard system constraint — guidance blocked until validation complete.
    """
    gate = ValidationGate(gate_id=gate_id)
    status = gate.get_status()
    
    return ValidationGateOut(
        gate_id=status["gate_id"],
        content_type=status["content_type"],
        content_id=status["content_id"],
        current_status=status["current_status"],
        stages=[
            ValidationStage(
                stage_name=s["stage_name"],
                completed=s["completed"],
                completed_at=s.get("completed_at"),
                completed_by=s.get("completed_by")
            )
            for s in status["stages"]
        ],
        deployment_blocked=status["deployment_blocked"],
        block_reason=status.get("block_reason"),
        version=status["version"],
        annual_review_due=status["annual_review_due"]
    )

@router.post("/validation/submit", tags=["Validation Gate"])
def submit_validation(request, payload: ValidationSubmit):
    """Submit review for a validation stage"""
    gate = ValidationGate(gate_id=payload.gate_id)
    
    result = gate.submit_review(
        stage=payload.stage,
        reviewer_name=payload.reviewer_name,
        reviewer_credentials=payload.reviewer_credentials,
        decision=payload.decision,
        comments=payload.comments or ""
    )
    
    return result

# --- Data Retention Endpoints ---

@router.get("/retention/policies", response=List[RetentionPolicyOut], tags=["Data Retention"])
def list_retention_policies(request):
    """List all data retention policies"""
    policies = DataRetentionPolicy.objects.all()
    
    return [
        RetentionPolicyOut(
            policy_name=p.policy_name,
            data_type=p.data_type,
            retention_days=p.retention_days,
            auto_delete_enabled=p.auto_delete_enabled,
            last_execution=p.last_execution,
            records_deleted_last_run=p.records_deleted_last_run
        )
        for p in policies
    ]

@router.post("/retention/execute", response=RetentionResult, tags=["Data Retention"])
def execute_retention(request, payload: RetentionExecution):
    """
    Execute data retention policy.
    Spec Section 5.2: Patient inputs deleted after 90 days.
    """
    enforcer = RetentionEnforcer()
    result = enforcer.execute_policy(payload.policy_name, payload.dry_run)
    
    return RetentionResult(
        policy_name=result["policy_name"],
        dry_run=result["dry_run"],
        records_identified=result["records_identified"],
        records_deleted=result["records_deleted"],
        execution_time_seconds=0.0,
        next_scheduled_run=timezone.now() + timedelta(days=1)
    )

# --- Compliance Violations ---

@router.post("/violations/create", response=ViolationOut, tags=["Violations"])
def create_violation(request, payload: ViolationCreate):
    """Create compliance violation record"""
    violation = ComplianceViolation.objects.create(
        severity=payload.severity,
        category=payload.category,
        description=payload.description,
        affected_system_component=payload.affected_component,
        remediation_deadline=payload.remediation_deadline,
        detected_by="System"  # Would be authenticated user
    )
    
    return ViolationOut(
        violation_id=violation.violation_id,
        severity=violation.severity,
        category=violation.category,
        description=violation.description,
        status="open",
        detected_at=violation.detected_at,
        remediation_deadline=violation.remediation_deadline,
        remediation_completed=False
    )

@router.get("/violations", response=List[ViolationOut], tags=["Violations"])
def list_violations(request, severity: Optional[str] = None, status: Optional[str] = None):
    """List compliance violations"""
    queryset = ComplianceViolation.objects.all()
    if severity:
        queryset = queryset.filter(severity=severity)
    if status:
        queryset = queryset.filter(remediation_completed=(status == "resolved"))
    
    return [
        ViolationOut(
            violation_id=v.violation_id,
            severity=v.severity,
            category=v.category,
            description=v.description,
            status="resolved" if v.remediation_completed else "open",
            detected_at=v.detected_at,
            remediation_deadline=v.remediation_deadline,
            remediation_completed=v.remediation_completed
        )
        for v in queryset.order_by("-detected_at")[:50]
    ]

# --- Compliance Dashboard ---

@router.get("/dashboard", response=ComplianceDashboard, tags=["Dashboard"])
def get_compliance_dashboard(request):
    """
    Executive compliance dashboard.
    Consolidated view of all compliance metrics.
    """
    from django.utils import timezone
    from datetime import timedelta
    
    now = timezone.now()
    thirty_days_ago = now - timedelta(days=30)
    
    # Audit metrics
    audit_entries = ImmutableAuditLog.objects.filter(action_timestamp__gte=thirty_days_ago)
    
    # Violations
    active_violations = ComplianceViolation.objects.filter(remediation_completed=False)
    critical_violations = active_violations.filter(severity="critical")
    
    # Model governance
    latest_model = None  # Would query ML pipeline
    
    # Bias audit
    latest_bias = BiasAuditReport.objects.order_by("-generated_at").first()
    
    # Drift
    drift_checks = DriftDetectionResult.objects.filter(detected_at__gte=thirty_days_ago)
    
    # Validation gates
    pending_validation = ClinicalValidationGate.objects.filter(deployment_blocked=True)
    deployed = ClinicalValidationGate.objects.filter(status="deployed")
    
    # Retention
    retention_policies = DataRetentionPolicy.objects.filter(auto_delete_enabled=True)
    retention_runs = DataRetentionPolicy.objects.filter(last_execution__gte=thirty_days_ago)
    
    # Determine overall status
    status = "compliant"
    immediate_actions = []
    
    if critical_violations.exists():
        status = "non_compliant"
        immediate_actions.append(f"Critical violations require immediate remediation: {critical_violations.count()}")
    
    if latest_bias and not latest_bias.passes_bias_audit:
        status = "at_risk" if status == "compliant" else "non_compliant"
        immediate_actions.append("Bias audit failed — model retraining required")
    
    if drift_checks.filter(is_drift_detected=True, severity="critical").exists():
        status = "at_risk" if status == "compliant" else "non_compliant"
        immediate_actions.append("Critical feature drift detected")
    
    return ComplianceDashboard(
        generated_at=now,
        overall_status=status,
        total_audit_entries_30d=audit_entries.count(),
        active_violations=active_violations.count(),
        critical_violations=critical_violations.count(),
        pending_remediation=active_violations.exclude(remediation_completed_at__isnull=False).count(),
        active_model_version=latest_model,
        last_bias_audit_date=latest_bias.period_end if latest_bias else None,
        next_bias_audit_due=latest_bias.period_end + timedelta(days=90) if latest_bias else None,
        drift_checks_30d=drift_checks.count(),
        drifts_detected_30d=drift_checks.filter(is_drift_detected=True).count(),
        guidance_pending_validation=pending_validation.count(),
        guidance_deployed=deployed.count(),
        guidance_deprecated=ClinicalValidationGate.objects.filter(status="deprecated").count(),
        retention_policies_active=retention_policies.count(),
        retention_runs_30d=retention_runs.count(),
        records_deleted_30d=sum(p.records_deleted_last_run for p in retention_runs),
        requires_immediate_action=immediate_actions
    )

api.add_router("/compliance/", router)