from typing import Dict, Optional
from datetime import date, timedelta
from uuid import UUID
from django.utils import timezone

from ..models import ClinicalValidationGate

class ValidationGate:
    """
    Hard clinical validation gate.
    Spec Section 8.2: No ML-generated advice surfaced without completing this gate.
    This is a hard system constraint, not a process recommendation.
    """
    
    REQUIRED_STAGES = [
        "clinician_1_review",
        "clinician_2_review", 
        "id_specialist_review",
        "moh_review"
    ]
    
    def __init__(self, gate_id: Optional[UUID] = None):
        self.gate = None
        if gate_id:
            self.gate = ClinicalValidationGate.objects.get(gate_id=gate_id)
    
    def create_gate(self, content_type: str, content_id: UUID) -> ClinicalValidationGate:
        """Create new validation gate for content"""
        self.gate = ClinicalValidationGate.objects.create(
            content_type=content_type,
            content_id=content_id,
            annual_review_due=date.today() + timedelta(days=365),
            deployment_blocked=True,
            block_reason="Awaiting clinical validation per Kenya MOH requirements"
        )
        return self.gate
    
    def submit_review(self, stage: str, reviewer_name: str,
                      reviewer_credentials: str,
                      decision: str = "approve",
                      comments: str = "") -> Dict:
        """Submit review for a validation stage"""
        if not self.gate:
            raise Exception("No active validation gate")
        
        if self.gate.status == "deployed":
            raise Exception("Content already deployed — cannot modify validation")
        
        # Update stage
        now = timezone.now()
        if stage == "clinician_1":
            self.gate.stage_clinician_1_review = now
            self.gate.clinician_1_name = reviewer_name
            self.gate.clinician_1_credentials = reviewer_credentials
            self.gate.status = "under_clinical_review"
            
        elif stage == "clinician_2":
            self.gate.stage_clinician_2_review = now
            self.gate.clinician_2_name = reviewer_name
            self.gate.clinician_2_credentials = reviewer_credentials
            self.gate.status = "clinician_approved"
            
        elif stage == "id_specialist":
            self.gate.stage_id_specialist_review = now
            self.gate.id_specialist_name = reviewer_name
            self.gate.id_specialist_credentials = reviewer_credentials
            self.gate.status = "id_specialist_approved"
            
        elif stage == "moh":
            self.gate.stage_moh_review = now
            self.gate.moh_signatory_name = reviewer_name
            self.gate.moh_signatory_credentials = reviewer_credentials
            self.gate.status = "moh_approved"
        
        self.gate.save()
        
        # Check if all stages complete
        self._evaluate_deployment_block()
        
        return {
            "gate_id": self.gate.gate_id,
            "stage": stage,
            "status": self.gate.status,
            "deployment_blocked": self.gate.deployment_blocked,
            "next_required_stage": self._next_required_stage()
        }
    
    def _evaluate_deployment_block(self):
        """Evaluate if deployment block can be lifted"""
        required_complete = all([
            self.gate.stage_clinician_1_review is not None,
            self.gate.stage_clinician_2_review is not None,
            self.gate.id_specialist_name is not None,
            self.gate.moh_signatory_name is not None
        ])
        
        if required_complete:
            self.gate.deployment_blocked = False
            self.gate.block_reason = ""
            self.gate.status = "deployed"
            self.gate.save()
    
    def _next_required_stage(self) -> Optional[str]:
        """Determine next required validation stage"""
        if self.gate.stage_clinician_1_review is None:
            return "clinician_1"
        elif self.gate.stage_clinician_2_review is None:
            return "clinician_2"
        elif self.gate.id_specialist_name is None:
            return "id_specialist"
        elif self.gate.moh_signatory_name is None:
            return "moh"
        return None
    
    def is_deployable(self) -> bool:
        """Check if content can be deployed"""
        return not self.gate.deployment_blocked if self.gate else False
    
    def get_status(self) -> Dict:
        """Get full validation gate status"""
        if not self.gate:
            return {"error": "No active gate"}
        
        stages = [
            {
                "stage_name": "Draft Created",
                "completed": True,
                "completed_at": self.gate.stage_drafted,
                "completed_by": "System"
            },
            {
                "stage_name": "Clinician 1 Review",
                "completed": self.gate.stage_clinician_1_review is not None,
                "completed_at": self.gate.stage_clinician_1_review,
                "completed_by": self.gate.clinician_1_name
            },
            {
                "stage_name": "Clinician 2 Review",
                "completed": self.gate.stage_clinician_2_review is not None,
                "completed_at": self.gate.stage_clinician_2_review,
                "completed_by": self.gate.clinician_2_name
            },
            {
                "stage_name": "ID Specialist Review",
                "completed": self.gate.id_specialist_name is not None,
                "completed_at": self.gate.stage_id_specialist_review,
                "completed_by": self.gate.id_specialist_name
            },
            {
                "stage_name": "MOH Sign-off",
                "completed": self.gate.moh_signatory_name is not None,
                "completed_at": self.gate.stage_moh_review,
                "completed_by": self.gate.moh_signatory_name
            }
        ]
        
        return {
            "gate_id": self.gate.gate_id,
            "content_type": self.gate.content_type,
            "content_id": self.gate.content_id,
            "current_status": self.gate.status,
            "stages": stages,
            "deployment_blocked": self.gate.deployment_blocked,
            "block_reason": self.gate.block_reason,
            "version": self.gate.version,
            "annual_review_due": self.gate.annual_review_due
        }