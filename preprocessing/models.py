from django.db import models


class DataCleaningRule(models.Model):
    name = models.CharField(max_length=100)
    field_name = models.CharField(max_length=100)
    rule_type = models.CharField(max_length=50, choices=[
        ('missing', 'Handle Missing Values'),
        ('outlier', 'Outlier Detection'),
        ('format', 'Format Validation'),
        ('duplicate', 'Duplicate Detection'),
    ])
    condition = models.TextField(help_text="JSON condition logic")
    action = models.CharField(max_length=50, choices=[
        ('fill_mean', 'Fill with Mean'),
        ('fill_median', 'Fill with Median'),
        ('fill_mode', 'Fill with Mode'),
        ('drop', 'Drop Record'),
        ('flag', 'Flag for Review'),
        ('transform', 'Apply Transformation'),
    ])
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.name} ({self.field_name})"


class FeatureTransformation(models.Model):
    name = models.CharField(max_length=100)
    source_field = models.CharField(max_length=100)
    transform_type = models.CharField(max_length=50, choices=[
        ('log', 'Log Transform'),
        ('sqrt', 'Square Root'),
        ('scale', 'Min-Max Scale'),
        ('standardize', 'Z-Score Standardize'),
        ('onehot', 'One-Hot Encode'),
        ('binning', 'Binning/Categorization'),
        ('interaction', 'Feature Interaction'),
    ])
    parameters = models.JSONField(default=dict, blank=True)
    output_field = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return f"{self.source_field} -> {self.transform_type} -> {self.output_field}"