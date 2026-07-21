from django.db import models


class ReportTemplate(models.Model):
    REPORT_TYPES = [
        ('weekly', 'Weekly Summary'),
        ('monthly', 'Monthly Report'),
        ('quarterly', 'Quarterly Report'),
        ('annual', 'Annual Report'),
        ('custom', 'Custom Report'),
        ('outbreak', 'Outbreak Alert'),
    ]
    
    name = models.CharField(max_length=200)
    report_type = models.CharField(max_length=20, choices=REPORT_TYPES)
    description = models.TextField(blank=True)
    
    # Query configuration
    query_config = models.JSONField(default=dict, help_text="JSON configuration for data queries")
    
    # Output format
    output_formats = models.JSONField(default=list, help_text="['pdf', 'excel', 'csv', 'json']")
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.name} ({self.report_type})"


class GeneratedReport(models.Model):
    STATUS_CHOICES = [
        ('generating', 'Generating'),
        ('ready', 'Ready'),
        ('failed', 'Failed'),
    ]
    
    template = models.ForeignKey(ReportTemplate, on_delete=models.CASCADE)
    title = models.CharField(max_length=300)
    
    # Period
    period_start = models.DateField()
    period_end = models.DateField()
    
    # Filters
    county_filter = models.CharField(max_length=100, blank=True)
    facility_filter = models.CharField(max_length=100, blank=True)
    
    # Output
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='generating')
    file_path = models.CharField(max_length=500, blank=True)
    file_size_bytes = models.PositiveIntegerField(null=True, blank=True)
    
    # Statistics included in report
    total_screenings = models.PositiveIntegerField(default=0)
    total_positive = models.PositiveIntegerField(default=0)
    total_high_risk = models.PositiveIntegerField(default=0)
    
    generated_by = models.CharField(max_length=100, blank=True)
    generated_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-generated_at']
    
    def __str__(self):
        return f"{self.title} - {self.status}"