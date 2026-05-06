from ninja import Router, NinjaAPI
from django.shortcuts import get_object_or_404
from typing import List
import uuid
import asyncio

from .schemas import (
    BatchProcessRequest, SingleProcessRequest, ProcessedRecordOut,
    PreprocessingJobOut, PreprocessingConfig, HealthCheckOut
)
from .services import PreprocessingPipeline
from .models import PreprocessingJob, ProcessingStatus, ProcessedRecord
from .tasks import run_batch_preprocessing_task

api = NinjaAPI(title="STI Preprocessing API", version="1.0")
router = Router()

@router.post("/process/single", response=ProcessedRecordOut, tags=["Real-time Processing"])
async def process_single(request, payload: SingleProcessRequest):
    """
    Process a single patient record in real-time.
    Used by patient dashboard for immediate risk assessment.
    """
    pipeline = PreprocessingPipeline(payload.config.dict() if payload.config else {})
    
    result = pipeline.process_single_record(payload.record.dict())
    
    return ProcessedRecordOut(
        anonymous_id=result["anonymous_id"],
        features={
            "symptom_vector": result["symptom_vector"],
            "composite_risk_score": result["composite_risk_score"],
            "age_encoded": result["age_encoded"],
            "sex_encoded": result["sex_encoded"],
            "region_encoded": result["age_encoded"],  # Placeholder
            "temporal_features": result["temporal_features"],
            "behavioural_embedding": [result["composite_risk_score"]]
        },
        risk_level=result["risk_level"],
        geographic_region=result["geographic_region"],
        privacy_applied=result["privacy_applied"]
    )

@router.post("/process/batch", response=PreprocessingJobOut, tags=["Batch Processing"])
async def start_batch_job(request, payload: BatchProcessRequest):
    """
    Start an asynchronous batch preprocessing job.
    Used for MOH/WHO data ingestion and model training data preparation.
    """
    # Create job record
    job = PreprocessingJob.objects.create(
        job_id=uuid.uuid4(),
        source=payload.source,
        raw_record_count=len(payload.records),
        config=payload.config.dict(),
        status=ProcessingStatus.PENDING
    )
    
    # Queue Celery task
    records_data = [r.dict() for r in payload.records]
    run_batch_preprocessing_task.delay(str(job.job_id), records_data, payload.config.dict())
    
    return PreprocessingJobOut(
        job_id=job.job_id,
        source=job.source,
        status=job.status,
        raw_record_count=job.raw_record_count,
        processed_record_count=0,
        duplicate_count=0,
        stages={
            "deduplication": None,
            "imputation": None,
            "encoding": None,
            "smote": None,
            "anonymisation": None
        },
        created_at=job.created_at,
        completed_at=None
    )

@router.get("/jobs/{job_id}", response=PreprocessingJobOut, tags=["Job Management"])
async def get_job_status(request, job_id: UUID):
    """Get status of a preprocessing job"""
    job = get_object_or_404(PreprocessingJob, job_id=job_id)
    
    return PreprocessingJobOut(
        job_id=job.job_id,
        source=job.source,
        status=job.status,
        raw_record_count=job.raw_record_count,
        processed_record_count=job.processed_record_count,
        duplicate_count=job.duplicate_count,
        stages={
            "deduplication": job.deduplication_completed,
            "imputation": job.imputation_completed,
            "encoding": job.encoding_completed,
            "smote": job.smote_completed,
            "anonymisation": job.anonymisation_completed
        },
        created_at=job.created_at,
        completed_at=job.completed_at,
        error_log=job.error_log or None
    )

@router.get("/jobs/{job_id}/records", response=List[ProcessedRecordOut], tags=["Job Management"])
async def get_job_records(request, job_id: UUID, limit: int = 100, offset: int = 0):
    """Retrieve processed records from a completed job"""
    job = get_object_or_404(PreprocessingJob, job_id=job_id)
    
    records = job.records.all()[offset:offset + limit]
    
    return [
        ProcessedRecordOut(
            anonymous_id=r.anonymous_id,
            features={
                "symptom_vector": r.symptoms.get("vector", []),
                "composite_risk_score": r.composite_risk_score or 0.0,
                "age_encoded": r.demographics.get("age_encoded", 0),
                "sex_encoded": r.demographics.get("sex_encoded", 0),
                "region_encoded": 0,
                "temporal_features": r.temporal_features,
                "behavioural_embedding": [r.composite_risk_score or 0.0]
            },
            risk_level=r.risk_level or "low",
            geographic_region=r.geographic_region,
            k_anonymity_group=r.k_anonymity_group,
            privacy_applied=r.differential_privacy_applied
        )
        for r in records
    ]

@router.get("/health", response=HealthCheckOut, tags=["System Health"])
async def health_check(request):
    """Check preprocessing pipeline health"""
    active_jobs = PreprocessingJob.objects.filter(
        status__in=[ProcessingStatus.PENDING, ProcessingStatus.PROCESSING]
    ).count()
    
    last_completed = PreprocessingJob.objects.filter(
        status=ProcessingStatus.COMPLETED
    ).order_by("-completed_at").first()
    
    return HealthCheckOut(
        status="healthy",
        pipeline_ready=True,
        active_jobs=active_jobs,
        last_completion=last_completed.completed_at if last_completed else None
    )

# Register router
api.add_router("/preprocessing/", router)