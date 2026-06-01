from ninja import Schema, Field
from typing import Annotated, List, Dict, Optional, Literal,Any
from uuid import UUID
from datetime import date, datetime

# --- Audit Log Schemas ---

class AuditQuery(Schema):
    """Query parameters for audit log retrieval"""
    anonymous_id: Optional[str] = None
    actor_id: Optional[str] = None
    action_type: Optional[str] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    model_version: Optional[str] = None
    limit: Annotated[int, Field(ge=1, le=10000)] = 1000

class AuditEntryOut(Schema):
    """Single audit log entry"""
    log_id: UUID
    action_type: str
    action_timestamp: datetime
    actor_type: str
    actor_id: Optional[str]
    anonymous_id: Optional[str]
    model_version: Optional[str]
    risk_score: Optional[float]
    risk_level: Optional[str]
    current_log_hash: str
    payload_summary: Dict

class AuditSummary(Schema):
    """Summary statistics for audit period"""
    total_entries: int
    entries_by_type: Dict[str, int]
    entries_by_actor: Dict[str, int]
    unique_patients: int
    unique_clinicians: int
    date_range: str

# --- Bias Audit Schemas ---

class SubgroupMetric(Schema):
    """Performance metric for a demographic subgroup"""
    subgroup_name: str
    sample_count: int
    auc_roc: Annotated[float, Field(ge=0.0, le=1.0)]
    f1_score: Annotated[float, Field(ge=0.0, le=1.0)]
    precision: Annotated[float, Field(ge=0.0, le=1.0)]
    recall: Annotated[float, Field(ge=0.0, le=1.0)]
    passes_threshold: bool

class BiasAuditRequest(Schema):
    """Request quarterly bias audit"""
    model_version: str
    model_type: Literal["classifier", "forecaster"]
    period_start: date
    period_end: date

class BiasAuditOut(Schema):
    """Bias audit report output"""
    report_id: UUID
    period: str
    model_version: str
    overall_passes: bool
    subgroup_results: List[SubgroupMetric]
    violations: List[Dict[str, Any]]
    recommended_actions: List[str]
    generated_at: datetime

# --- Drift Detection Schemas ---

class DriftCheckRequest(Schema):
    """Request drift detection for a model"""
    model_version: str
    feature_names: List[str]

    psi_threshold: Annotated[float, Field(ge=0.0, le=1.0)] = 0.2
class DriftResultOut(Schema):
    """Single feature drift result"""
    feature_name: str
    psi_score: float
    threshold: float
    is_drift_detected: bool
    severity: str
    training_distribution: Dict
    current_distribution: Dict

class DriftSummary(Schema):
    """Summary of drift detection run"""
    run_timestamp: datetime
    model_version: str
    features_checked: int
    features_drifted: int
    critical_drifts: int
    retraining_triggered: bool

# --- Validation Gate Schemas ---

class ValidationStage(Schema):
    """Single validation stage"""
    stage_name: str
    completed: bool
    completed_at: Optional[datetime]
    completed_by: Optional[str]
    credentials: Optional[str]

class ValidationGateOut(Schema):
    """Validation gate status"""
    gate_id: UUID
    content_type: str
    content_id: UUID
    current_status: str
    stages: List[ValidationStage]
    deployment_blocked: bool
    block_reason: Optional[str]
    version: int
    annual_review_due: date

class ValidationSubmit(Schema):
    """Submit validation for a stage"""
    gate_id: UUID
    stage: Literal["clinician_1", "clinician_2", "id_specialist", "moh"]
    reviewer_name: str
    reviewer_credentials: str
    decision: Literal["approve", "reject", "request_changes"]
    comments: Optional[str] = None

# --- Retention Policy Schemas ---

class RetentionPolicyOut(Schema):
    """Data retention policy status"""
    policy_name: str
    data_type: str
    retention_days: int
    auto_delete_enabled: bool
    last_execution: Optional[datetime]
    records_deleted_last_run: int

class RetentionExecution(Schema):
    """Execute retention policy"""
    policy_name: str
    dry_run: bool = True  # Preview without deleting

class RetentionResult(Schema):
    """Retention execution result"""
    policy_name: str
    dry_run: bool
    records_identified: int
    records_deleted: int
    execution_time_seconds: float
    next_scheduled_run: datetime

# --- Compliance Violation Schemas ---

class ViolationCreate(Schema):
    """Create compliance violation record"""
    severity: Literal["low", "moderate", "high", "critical"]
    category: Literal["privacy", "bias", "validation", "data_retention", "security", "audit_gap"]
    description: str
    affected_component: str
    remediation_deadline: date

class ViolationOut(Schema):
    """Compliance violation output"""
    violation_id: UUID
    severity: str
    category: str
    description: str
    status: str
    detected_at: datetime
    remediation_deadline: date
    remediation_completed: bool

class ComplianceDashboard(Schema):
    """Executive compliance dashboard"""
    generated_at: datetime
    overall_status: Literal["compliant", "at_risk", "non_compliant"]
    
    # Metrics
    total_audit_entries_30d: int
    active_violations: int
    critical_violations: int
    pending_remediation: int
    
    # Model governance
    active_model_version: Optional[str]
    last_bias_audit_date: Optional[date]
    next_bias_audit_due: Optional[date]
    drift_checks_30d: int
    drifts_detected_30d: int
    
    # Validation gate
    guidance_pending_validation: int
    guidance_deployed: int
    guidance_deprecated: int
    
    # Data retention
    retention_policies_active: int
    retention_runs_30d: int
    records_deleted_30d: int
    
    # Alerts
    requires_immediate_action: List[str]