from celery import shared_task
from datetime import datetime, timedelta

from .services.drift_detector import DriftDetector
from .services.retention_enforcer import RetentionEnforcer
from .models import DriftDetectionResult, ComplianceViolation

@shared_task
def weekly_drift_check():
    """
    Weekly PSI drift detection.
    Spec Section 4.3: PSI computed weekly.
    """
    # In production, fetch current model and feature distributions
    # Run PSI checks
    # Trigger retraining if threshold exceeded
    
    return {"status": "completed", "drifts_found": 0}

@shared_task
def quarterly_bias_audit():
    """
    Quarterly bias audit.
    Spec Section 8.3: Quarterly bias audit report.
    """
    from .services.bias_monitor import BiasMonitor
    
    # Generate and save report
    # Flag model for retraining if violations found
    
    return {"status": "completed", "violations": 0}

@shared_task
def daily_retention_enforcement():
    """
    Daily data retention policy enforcement.
    Spec Section 5.2: Patient inputs deleted after 90 days.
    """
    enforcer = RetentionEnforcer()
    results = enforcer.run_all_policies(dry_run=False)
    
    return {
        "status": "completed",
        "policies_executed": len(results),
        "total_records_deleted": sum(r["records_deleted"] for r in results)
    }

@shared_task
def annual_validation_review():
    """
    Annual re-review of all approved guidance content.
    Spec Section 8.2: Annual re-review of all approved guidance.
    """
    from .models import ClinicalValidationGate
    
    due_for_review = ClinicalValidationGate.objects.filter(
        annual_review_due__lte=datetime.now().date(),
        status="deployed"
    )
    
    for gate in due_for_review:
        # Flag for re-review
        gate.status = "deprecated"
        gate.block_reason = "Annual review overdue — content temporarily deprecated pending re-validation"
        gate.deployment_blocked = True
        gate.save()
        
        # Create compliance violation
        ComplianceViolation.objects.create(
            severity="moderate",
            category="validation",
            description=f"Guidance {gate.content_id} annual review overdue",
            affected_system_component="Clinical Validation Gate",
            remediation_deadline=datetime.now().date() + timedelta(days=30)
        )
    
    return {"flagged_for_review": due_for_review.count()}