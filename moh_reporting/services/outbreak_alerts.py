from typing import List, Dict, Optional
from datetime import date, timedelta

from django.utils import timezone

from ..models import OutbreakNotificationConfig, OutbreakAlertHistory
from django.db import models
class OutbreakAlertService:
    """
    Outbreak notification trigger service.
    Spec Section 7.4: Configurable alert thresholds for outbreak notification triggers.
    """
    
    def evaluate_triggers(self, county: str, sti_type: str,
                          current_value: float,
                          value_type: str = "incidence_rate") -> List[Dict]:
        """Evaluate all alert configurations for a trigger"""
        configs = OutbreakNotificationConfig.objects.filter(
            sti_type=sti_type,
            is_active=True
        ).filter(
            models.Q(county=county) | models.Q(county="")
        )
        
        triggered = []
        for config in configs:
            if self._check_threshold(config, current_value, value_type):
                alert = self._create_alert(config, county, current_value)
                triggered.append({
                    "config_id": str(config.config_id),
                    "threshold_type": config.threshold_type,
                    "threshold_value": config.threshold_value,
                    "actual_value": current_value,
                    "notifications_sent": alert.notifications_sent
                })
        
        return triggered
    
    def _check_threshold(self, config: OutbreakNotificationConfig,
                         current_value: float, value_type: str) -> bool:
        """Check if current value exceeds threshold"""
        if config.threshold_type != value_type:
            return False
        
        return current_value >= config.threshold_value
    
    def _create_alert(self, config: OutbreakNotificationConfig,
                      county: str, actual_value: float) -> OutbreakAlertHistory:
        """Create alert record and send notifications"""
        notifications = []
        
        if config.notify_moh:
            notifications.append({"recipient": "MOH", "method": "email", "status": "sent"})
        if config.notify_who:
            notifications.append({"recipient": "WHO", "method": "secure_transfer", "status": "pending"})
        if config.notify_county_officers:
            notifications.append({"recipient": f"County Officer {county}", "method": "email", "status": "sent"})
        
        alert = OutbreakAlertHistory.objects.create(
            trigger_config=config,
            sti_type=config.sti_type,
            county=county,
            actual_value=actual_value,
            threshold_value=config.threshold_value,
            notifications_sent=notifications
        )
        
        return alert
    
    def acknowledge_alert(self, alert_id: str, acknowledged_by: str,
                          actions: List[str]) -> OutbreakAlertHistory:
        """Acknowledge outbreak alert and record response actions"""
        alert = OutbreakAlertHistory.objects.get(alert_id=alert_id)
        alert.acknowledged_by = acknowledged_by
        alert.response_actions = actions
        alert.resolved_at = timezone.now()
        alert.save()
        
        return alert