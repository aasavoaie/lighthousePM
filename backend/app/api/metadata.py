from fastapi import APIRouter

from app.schemas.metric_metadata import MetricCatalogResponse
from app.services.metric_catalog_service import MetricCatalogService

router = APIRouter(prefix="/metadata", tags=["metadata"])


@router.get(
    "/metrics",
    response_model=MetricCatalogResponse,
    operation_id="get_metric_catalog",
    summary="Get metric catalog",
)
def get_metric_catalog() -> MetricCatalogResponse:
    return MetricCatalogService().get_catalog()
