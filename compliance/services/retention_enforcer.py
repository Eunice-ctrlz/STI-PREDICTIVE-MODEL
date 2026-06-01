from datetime import datetime, timedelta, date
from typing import Dict, List

from django.utils import timezone

from ..models import DataRetentionPolicy, ImmutableAuditLog

class RetentionEnforcer:
    """
    Data retention policy enforcement.
    Spec Section 5.2: Patient inputs deleted after 90 days. Aggregated model training data 5 years.
    """
    
    def __init__(self):
        self.policies = {
            "patient_input": 90,
            "processed_record": 90,
            "audit_log": 2555,  # 7 years for regulatory compliance
            "model_training_data": 1825,  # 5 years
            "geospatial_grid": 730  # 2 years for grid cells
        }
    
    def initialize_policies(self):
        """Create default retention policies if they don't exist"""
        for data_type, days in self.policies.items():
            DataRetentionPolicy.objects.get_or_create(
                policy_name=f"{data_type}_retention",
                defaults={
                    "data_type": data_type,
                    "retention_days": days,
                    "auto_delete_enabled": True
                }
            )
    
    def execute_policy(self, policy_name: str, dry_run: bool = True) -> Dict:
        """Execute a single retention policy"""
        try:
            policy = DataRetentionPolicy.objects.get(policy_name=policy_name)
        except DataRetentionPolicy.DoesNotExist:
            return {"error": f"Policy {policy_name} not found"}
        
        cutoff_date = timezone.now() - timedelta(days=policy.retention_days)
        
        # Identify records to delete (customize per data type)
        records_to_delete = self._identify_records(policy.data_type, cutoff_date)
        count = records_to_delete.count()
        
        result = {
            "policy_name": policy_name,
            "data_type": policy.data_type,
            "retention_days": policy.retention_days,
            "cutoff_date": cutoff_date.isoformat(),
            "records_identified": count,
            "dry_run": dry_run,
            "records_deleted": 0
        }
        
        if not dry_run and count > 0:
            # Log deletion in audit trail
            ImmutableAuditLog.objects.create(
                action_type="data_deleted",
                actor_type="system",
                action_timestamp=timezone.now(),
                payload_summary={
                    "policy_name": policy_name,
                    "records_deleted": count,
                    "cutoff_date": cutoff_date.isoformat()
                }
            )
            
            # Execute deletion
            records_to_delete.delete()
            result["records_deleted"] = count
            
            # Update policy tracking
            policy.last_execution = timezone.now()
            policy.records_deleted_last_run = count
            policy.execution_log = f"Deleted {count} records on {timezone.now().isoformat()}"
            policy.save()
        
        return result
    
    def _identify_records(self, data_type: str, cutoff_date: datetime):
        """Identify records past retention period"""
        if data_type == "patient_input":
            from patients.models import PatientAssessment
            return PatientAssessment.objects.filter(created_at__lt=cutoff_date)
        
        elif data_type == "processed_record":
            from preprocessing.models import ProcessedRecord
            return ProcessedRecord.objects.filter(created_at__lt=cutoff_date)
        
        elif data_type == "audit_log":
            # Audit logs kept longer — only delete after 7 years
            return ImmutableAuditLog.objects.filter(action_timestamp__lt=cutoff_date)
        
        elif data_type == "model_training_data":
            # Training data retention handled by ML pipeline
            from preprocessing.models import ProcessedRecord
            return ProcessedRecord.objects.filter(
                created_at__lt=cutoff_date,
                job__source__in=["moh_db", "who_api"]
            )
        
        # Default: empty queryset
        from django.db.models import QuerySet
        return ImmutableAuditLog.objects.none()
    
    def run_all_policies(self, dry_run: bool = True) -> List[Dict]:
        """Execute all active retention policies"""
        self.initialize_policies()
        results = []
        
        for policy in DataRetentionPolicy.objects.filter(auto_delete_enabled=True):
            result = self.execute_policy(policy.policy_name, dry_run)
            results.append(result)
        
        return results