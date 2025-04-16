from django.db import models

# Create your models here.

"""
Models for tracking MVSep job progress.
"""

from django.db import models
import uuid


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