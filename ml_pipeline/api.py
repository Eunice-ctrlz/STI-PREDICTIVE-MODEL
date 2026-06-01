from ninja import NinjaAPI, Router

api = NinjaAPI(
    title="STI ML Pipeline API",
    version="1.0",
    urls_namespace="ml_pipeline"
)
router = Router()

# Add placeholder endpoint
@router.get("/health", tags=["Health"])
def health_check(request):
    return {"status": "ML Pipeline API placeholder"}

api.add_router("/ml/", router)