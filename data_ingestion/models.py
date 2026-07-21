from django.db import models


class DataSource(models.Model):
    SOURCE_TYPES = [
        ('csv', 'CSV File'),
        ('excel', 'Excel File'),
        ('api', 'External API'),
        ('hl7', 'HL7 FHIR'),
        ('database', 'Direct Database'),
    ]
    
    name = models.CharField(max_length=200)
    source_type = models.CharField(max_length=20, choices=SOURCE_TYPES)
    description = models.TextField(blank=True)
    
    # Connection details (encrypted in production)
    connection_string = models.TextField(blank=True)
    api_endpoint = models.URLField(blank=True)
    api_key = models.CharField(max_length=500, blank=True)
    
    schedule = models.CharField(
        max_length=50,
        choices=[
            ('manual', 'Manual Only'),
            ('hourly', 'Hourly'),
            ('daily', 'Daily'),
            ('weekly', 'Weekly'),
        ],
        default='manual'
    )
    
    is_active = models.BooleanField(default=True)
    last_ingested_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.name} ({self.source_type})"


class IngestionJob(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('partial', 'Partial Success'),
    ]
    
    source = models.ForeignKey(DataSource, on_delete=models.CASCADE, related_name='jobs')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # File upload
    uploaded_file = models.FileField(upload_to='uploads/%Y/%m/%d/', blank=True, null=True)
    
    # Statistics
    total_records = models.PositiveIntegerField(default=0)
    processed_records = models.PositiveIntegerField(default=0)
    failed_records = models.PositiveIntegerField(default=0)
    error_log = models.TextField(blank=True)
    
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Ingestion {self.id} - {self.source.name} - {self.status}"