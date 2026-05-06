from celery import shared_task
from datetime import datetime
from django.db import transaction

from .models import PreprocessingJob, ProcessingStatus, ProcessedRecord
from .services import PreprocessingPipeline

@shared_task(bind=True, max_retries=3)
def run_batch_preprocessing_task(self, job_id: str, records_data: list, config: dict):
    """
    Celery task for batch preprocessing.
    Updates job status through each pipeline stage.
    """
    try:
        job = PreprocessingJob.objects.get(job_id=job_id)
        job.status = ProcessingStatus.PROCESSING
        job.save()
        
        pipeline = PreprocessingPipeline(config)
        
        # Stage 1: Deduplication
        unique_records, dup_count = pipeline.deduplicate(records_data)
        job.duplicate_count = dup_count
        job.deduplication_completed = datetime.now()
        job.save()
        
        # Stage 2: Process records
        processed_records = []
        for record_data in unique_records:
            try:
                processed = pipeline.process_single_record(record_data)
                processed_records.append(processed)
            except Exception as e:
                continue
        
        job.imputation_completed = datetime.now()
        job.encoding_completed = datetime.now()
        job.save()
        
        # Stage 3: Save to database
        with transaction.atomic():
            for proc in processed_records:
                ProcessedRecord.objects.create(
                    anonymous_id=proc["anonymous_id"],
                    job=job,
                    symptoms={"vector": proc["symptom_vector"]},
                    risk_behaviours=record_data.get("risk_behaviours", {}),
                    demographics={
                        "age_encoded": proc["age_encoded"],
                        "sex_encoded": proc["sex_encoded"]
                    },
                    geographic_region=proc["geographic_region"],
                    composite_risk_score=proc["composite_risk_score"],
                    temporal_features=proc["temporal_features"],
                    risk_level=proc["risk_level"],
                    differential_privacy_applied=proc["privacy_applied"]
                )
        
        # Stage 4: k-anonymity grouping
        saved_records = list(job.records.all())
        pipeline.apply_k_anonymity(saved_records, k=config.get("k_anonymity", 10))
        for record in saved_records:
            record.save()
        
        job.anonymisation_completed = datetime.now()
        job.processed_record_count = len(processed_records)
        job.status = ProcessingStatus.COMPLETED
        job.completed_at = datetime.now()
        job.save()
        
        return {"job_id": job_id, "processed": len(processed_records)}
        
    except Exception as exc:
        job.status = ProcessingStatus.FAILED
        job.error_log = str(exc)
        job.save()
        raise self.retry(exc=exc, countdown=60)