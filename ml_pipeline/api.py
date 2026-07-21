from ninja import Router
from django.shortcuts import get_object_or_404
from typing import List
from .models import MLModel, TrainingJob

router = Router(tags=["ML Pipeline"])


@router.get("/models")
def list_models(request, status: str = None):
    qs = MLModel.objects.all()
    if status:
        qs = qs.filter(status=status)
    return list(qs.values().order_by('-created_at'))


@router.get("/models/{model_id}")
def get_model(request, model_id: int):
    return get_object_or_404(MLModel, id=model_id)


@router.post("/models/{model_id}/deploy")
def deploy_model(request, model_id: int):
    model = get_object_or_404(MLModel, id=model_id, status='ready')
    # Undeploy current default
    MLModel.objects.filter(name=model.name, is_default=True).update(is_default=False, status='deprecated')
    model.is_default = True
    model.status = 'deployed'
    model.save()
    return {"success": True, "message": f"Model {model.name} v{model.version} deployed"}


@router.get("/jobs")
def list_training_jobs(request, status: str = None):
    qs = TrainingJob.objects.all()
    if status:
        qs = qs.filter(status=status)
    return list(qs.values().order_by('-created_at')[:20])


@router.get("/jobs/{job_id}")
def get_training_job(request, job_id: int):
    return get_object_or_404(TrainingJob, id=job_id)