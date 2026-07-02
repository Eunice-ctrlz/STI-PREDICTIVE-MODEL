from django.db import models


class MLModel(models.Model):
    STATUS_CHOICES = [
        ('training', 'Training'),
        ('ready', 'Ready for Deployment'),
        ('deployed', 'Deployed'),
        ('deprecated', 'Deprecated'),
        ('failed', 'Failed'),
    ]
    
    MODEL_TYPES = [
        ('logistic_regression', 'Logistic Regression'),
        ('random_forest', 'Random Forest'),
        ('xgboost', 'XGBoost'),
        ('lightgbm', 'LightGBM'),
        ('neural_network', 'Neural Network'),
        ('svm', 'Support Vector Machine'),
    ]
    
    name = models.CharField(max_length=100)
    version = models.CharField(max_length=50, db_index=True)
    model_type = models.CharField(max_length=30, choices=MODEL_TYPES)
    description = models.TextField(blank=True)
    
    # File paths (relative to MEDIA_ROOT/models/)
    model_file = models.FileField(upload_to='models/%Y/%m/%d/')
    scaler_file = models.FileField(upload_to='models/%Y/%m/%d/', blank=True, null=True)
    metadata_file = models.FileField(upload_to='models/%Y/%m/%d/', blank=True, null=True)
    
    # Hyperparameters
    hyperparameters = models.JSONField(default=dict, blank=True)
    
    # Performance metrics
    training_accuracy = models.FloatField(null=True, blank=True)
    validation_accuracy = models.FloatField(null=True, blank=True)
    test_auc_roc = models.FloatField(null=True, blank=True)
    test_f1 = models.FloatField(null=True, blank=True)
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='training')
    is_default = models.BooleanField(default=False)
    
    # Training metadata
    training_data_size = models.PositiveIntegerField(null=True, blank=True)
    training_started_at = models.DateTimeField(null=True, blank=True)
    training_completed_at = models.DateTimeField(null=True, blank=True)
    training_duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    
    created_by = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        unique_together = ['name', 'version']
    
    def __str__(self):
        return f"{self.name} v{self.version} ({self.model_type})"


class TrainingJob(models.Model):
    STATUS_CHOICES = [
        ('queued', 'Queued'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    model = models.ForeignKey(MLModel, on_delete=models.CASCADE, related_name='training_jobs')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='queued')
    
    # Configuration
    dataset_path = models.CharField(max_length=500, blank=True)
    test_size = models.FloatField(default=0.2)
    random_state = models.IntegerField(default=42)
    cross_validation_folds = models.PositiveIntegerField(default=5)
    
    # Progress
    current_epoch = models.PositiveIntegerField(default=0)
    total_epochs = models.PositiveIntegerField(default=100)
    current_fold = models.PositiveIntegerField(default=0)
    
    # Logs
    logs = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Training {self.model.name} v{self.model.version} - {self.status}"