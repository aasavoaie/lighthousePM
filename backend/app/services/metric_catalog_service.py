from app.metric_catalog import (
    CATALOG_VERSION,
    MetricDefinition,
    MetricScope,
    metrics_for_scope,
)
from app.schemas.metric_metadata import (
    MetricAvailabilityMetadataResponse,
    MetricCatalogResponse,
    MetricDefinitionResponse,
    MetricThresholdMetadataResponse,
)
from app.utils.constants import RULESET_VERSION


class MetricCatalogService:
    """Serialize the immutable metric catalog for public API consumers."""

    def get_catalog(self) -> MetricCatalogResponse:
        return MetricCatalogResponse(
            catalog_version=CATALOG_VERSION,
            ruleset_version=RULESET_VERSION,
            release=self._serialize_scope("release"),
            sprint=self._serialize_scope("sprint"),
        )

    def _serialize_scope(self, scope: MetricScope) -> list[MetricDefinitionResponse]:
        return [
            self._serialize_definition(definition)
            for definition in metrics_for_scope(scope)
        ]

    def _serialize_definition(
        self,
        definition: MetricDefinition,
    ) -> MetricDefinitionResponse:
        return MetricDefinitionResponse(
            key=definition.key,
            scope=definition.scope,
            api_field=definition.api_field,
            api_location=definition.api_location,
            label=definition.label,
            description=definition.description,
            category=definition.category,
            unit=definition.unit,
            formatting=definition.formatting,
            display_order=definition.display_order,
            thresholds=[
                MetricThresholdMetadataResponse(
                    severity=threshold.severity,
                    comparison=threshold.comparison,
                    value=threshold.value,
                    meaning=threshold.meaning,
                )
                for threshold in definition.thresholds
            ],
            severity_meaning=definition.severity_meaning,
            availability=MetricAvailabilityMetadataResponse(
                dependencies=list(definition.availability.dependencies),
                partial_value_policy=definition.availability.partial_value_policy,
                supports_not_applicable=(
                    definition.availability.supports_not_applicable
                ),
                evidence_fields=list(definition.availability.evidence_fields),
                minimum_coverage_pct=definition.availability.minimum_coverage_pct,
            ),
            historical_series=definition.historical_series,
            signal_participation=definition.signal_participation,
            confidence_participation=definition.confidence_participation,
            chart_participation=definition.chart_participation,
            report_participation=definition.report_participation,
            ruleset_version=definition.ruleset_version,
        )
