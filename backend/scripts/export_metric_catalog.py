"""Export the backend-owned metric catalog for the frontend fallback."""

import json
from pathlib import Path

from app.services.metric_catalog_service import MetricCatalogService


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_PATH = REPOSITORY_ROOT / "frontend" / "src" / "generated" / "metricCatalogFallback.json"


def main() -> None:
    catalog = MetricCatalogService().get_catalog().model_dump(mode="json")
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(catalog, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
