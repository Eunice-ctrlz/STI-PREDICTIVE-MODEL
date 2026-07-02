from ninja import Router, File
from ninja.files import UploadedFile
from django.shortcuts import get_object_or_404
from typing import List
import csv
import io
from .models import DataSource, IngestionJob
from patients.models import Patient

router = Router(tags=["Data Ingestion"])


@router.post("/upload-csv")
def upload_patient_csv(request, file: UploadedFile = File(...)):
    """
    Upload a CSV file of patient data.
    Expected columns: patient_id, first_name, last_name, date_of_birth, gender, etc.
    """
    job = IngestionJob.objects.create(
        source=DataSource.objects.get_or_create(
            name='CSV Upload',
            defaults={'source_type': 'csv'}
        )[0],
        uploaded_file=file,
        status='processing'
    )
    
    try:
        decoded = file.read().decode('utf-8')
        reader = csv.DictReader(io.StringIO(decoded))
        
        total = 0
        processed = 0
        failed = 0
        errors = []
        
        for row in reader:
            total += 1
            try:
                Patient.objects.update_or_create(
                    patient_id=row.get('patient_id', f'AUTO_{total}'),
                    defaults={
                        'first_name': row.get('first_name', ''),
                        'last_name': row.get('last_name', ''),
                        'date_of_birth': row.get('date_of_birth', '2000-01-01'),
                        'gender': row.get('gender', 'U')[:1].upper(),
                        'phone': row.get('phone', ''),
                        'email': row.get('email', ''),
                        'county': row.get('county', ''),
                        'sub_county': row.get('sub_county', ''),
                    }
                )
                processed += 1
            except Exception as e:
                failed += 1
                errors.append(f"Row {total}: {str(e)}")
        
        job.total_records = total
        job.processed_records = processed
        job.failed_records = failed
        job.error_log = '\n'.join(errors[:50])  # Limit error log
        job.status = 'completed' if failed == 0 else 'partial'
        job.save()
        
        return {
            "success": True,
            "job_id": job.id,
            "total": total,
            "processed": processed,
            "failed": failed,
        }
        
    except Exception as e:
        job.status = 'failed'
        job.error_log = str(e)
        job.save()
        return {"success": False, "error": str(e)}


@router.get("/jobs")
def list_ingestion_jobs(request, status: str = None):
    qs = IngestionJob.objects.all()
    if status:
        qs = qs.filter(status=status)
    return list(qs.values().order_by('-created_at')[:20])