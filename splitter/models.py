from django.db import models

# Create your models here.

"""
Models for tracking MVSep job progress.
"""

from django.db import models
import uuid
from django.utils import timezone


class MVSepJob(models.Model):
    """Model to track the progress of MVSep processing jobs"""

    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    )

    # Job identification
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # File information
    file_name = models.CharField(max_length=255)
    local_file_path = models.CharField(max_length=1024)

    # Processing status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    current_stage = models.CharField(max_length=255, blank=True, null=True)
    progress_percentage = models.IntegerField(default=0)
    error_message = models.TextField(blank=True, null=True)

    # Result information
    output_dir = models.CharField(max_length=1024, blank=True, null=True)
    stem_files_json = models.TextField(blank=True, null=True)

    # Timing information
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"MVSepJob {self.id} - {self.file_name} - {self.status}"

    class Meta:
        verbose_name = "MVSep Job"
        verbose_name_plural = "MVSep Jobs"
        ordering = ['-created_at']


class UserAccount(models.Model):
    """Model to track user accounts and their access permissions"""
    
    ACCESS_TYPE_CHOICES = (
        ('demo', 'Demo Access'),
        ('monthly', 'Monthly Subscription'),
        ('yearly', 'Yearly Subscription'),
        ('lifetime', 'Lifetime Access'),
    )
    
    email = models.EmailField(unique=True)
    email_hash = models.CharField(max_length=64, unique=True)
    ghl_contact_id = models.CharField(max_length=128, blank=True, null=True)
    
    # Access control
    access_type = models.CharField(max_length=20, choices=ACCESS_TYPE_CHOICES, default='demo')
    has_active_access = models.BooleanField(default=False)
    
    # GHL tag tracking
    current_tags = models.JSONField(default=list)
    
    # Limits
    monthly_limit = models.IntegerField(default=0)  # 0 means unlimited for paid plans
    demo_limit = models.IntegerField(default=3)     # Total limit for demo accounts
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_validated_at = models.DateTimeField(default=timezone.now)
    
    def __str__(self):
        return f"{self.email} ({self.access_type})"


class SplitUsage(models.Model):
    """Model to track usage of the splitting service"""
    
    user = models.ForeignKey(UserAccount, on_delete=models.CASCADE, related_name='usages')
    job = models.ForeignKey(MVSepJob, on_delete=models.SET_NULL, null=True, blank=True)
    
    file_name = models.CharField(max_length=255)
    file_duration_seconds = models.IntegerField(default=0)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    
    # For monthly tracking
    month = models.IntegerField()  # 1-12
    year = models.IntegerField()   # e.g., 2023
    
    def save(self, *args, **kwargs):
        # Set month and year if not explicitly provided
        if not self.month or not self.year:
            now = timezone.now()
            self.month = now.month
            self.year = now.year
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"Split by {self.user.email} on {self.created_at.strftime('%Y-%m-%d')}"
    
    class Meta:
        indexes = [
            models.Index(fields=['user', 'year', 'month']),
        ]