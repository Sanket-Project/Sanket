from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models.enums import IndustryCode


@dataclass(frozen=True, slots=True)
class IndustryContext:
    code: str
    display_name: str
    default_horizon_weeks: int
    granularity_dimensions: list[str]
    required_signal_types: list[str]
    sku_attribute_schema: dict[str, Any]
    forecast_models: list[str]
    optimization_models: list[str]
    audit_level: str  # "standard" | "gxp"

    @property
    def is_gxp(self) -> bool:
        return self.audit_level == "gxp"

    def effective_horizon(self, tenant_override: int | None) -> int:
        return tenant_override if tenant_override is not None else self.default_horizon_weeks

    def validate_sku_attributes(self, attributes: dict[str, Any]) -> list[str]:
        """Return a list of validation errors for industry-specific SKU attributes."""
        errors: list[str] = []
        schema = self.sku_attribute_schema
        for field, rules in schema.items():
            value = attributes.get(field)
            if rules.get("required") and value is None:
                errors.append(f"Missing required attribute: {field}")
                continue
            if value is None:
                continue
            expected_type = rules.get("type")
            if expected_type == "string" and not isinstance(value, str):
                errors.append(f"Attribute '{field}' must be a string")
            elif expected_type == "integer" and not isinstance(value, int):
                errors.append(f"Attribute '{field}' must be an integer")
            elif expected_type == "boolean" and not isinstance(value, bool):
                errors.append(f"Attribute '{field}' must be a boolean")
            allowed = rules.get("enum")
            if allowed is not None and value not in allowed:
                errors.append(f"Attribute '{field}' must be one of {allowed}, got '{value}'")
        return errors


FASHION = IndustryContext(
    code=IndustryCode.fashion.value,
    display_name="Apparel & Fashion",
    default_horizon_weeks=26,
    granularity_dimensions=["size", "color", "channel", "region"],
    required_signal_types=[
        "trend_search",
        "social_sentiment",
        "weather",
        "competitor_price",
    ],
    sku_attribute_schema={
        "size": {"type": "string", "enum": ["XS", "S", "M", "L", "XL", "XXL", "XXXL"]},
        "color": {"type": "string"},
        "material": {"type": "string"},
        "season": {"type": "string", "enum": ["SS", "FW", "AW", "Cruise", "Resort"]},
        "gender": {"type": "string", "enum": ["mens", "womens", "unisex", "kids"]},
        "care_label": {"type": "string"},
        "country_of_origin": {"type": "string"},
    },
    forecast_models=["TimesFM", "TFT", "N-HiTS", "LightGBM", "Croston"],
    optimization_models=["OR-Tools", "RLlib-replenishment"],
    audit_level="standard",
)

ELECTRONICS = IndustryContext(
    code=IndustryCode.electronics.value,
    display_name="Consumer Electronics",
    default_horizon_weeks=12,
    granularity_dimensions=["model_year", "channel", "region", "warranty_tier"],
    required_signal_types=[
        "trend_search",
        "competitor_price",
        "logistics_disruption",
        "macro_economic",
    ],
    sku_attribute_schema={
        "model_year": {"type": "integer"},
        "specs": {"type": "object"},
        "warranty_months": {"type": "integer"},
        "component_ids": {"type": "array"},
        "energy_class": {"type": "string"},
        "connectivity": {"type": "array"},
        "color_finish": {"type": "string"},
    },
    forecast_models=["TimesFM", "DeepAR", "TFT", "LightGBM", "Chronos"],
    optimization_models=["OR-Tools", "RLlib-replenishment", "causal-DoWhy"],
    audit_level="standard",
)

PHARMA = IndustryContext(
    code=IndustryCode.pharma.value,
    display_name="Pharmaceuticals",
    default_horizon_weeks=52,
    granularity_dimensions=["ndc", "channel", "region", "cold_chain"],
    required_signal_types=[
        "regulatory",
        "macro_economic",
        "logistics_disruption",
        "supplier_lead",
    ],
    sku_attribute_schema={
        "ndc_code": {"type": "string"},
        "dosage_form": {"type": "string"},
        "strength": {"type": "string"},
        "route_of_admin": {"type": "string"},
        "controlled_substance": {"type": "boolean"},
        "therapeutic_class": {"type": "string"},
        "requires_rx": {"type": "boolean"},
        "storage_class": {
            "type": "string",
            "enum": ["ambient", "refrigerated", "frozen", "controlled_room"],
        },
    },
    forecast_models=["TFT", "Croston", "N-HiTS", "LightGBM", "Chronos"],
    optimization_models=["OR-Tools", "safety-stock-optimizer"],
    audit_level="gxp",
)

AGROCENTER = IndustryContext(
    code=IndustryCode.agrocenter.value,
    display_name="Agrocenter & Farm Inputs",
    default_horizon_weeks=26,
    granularity_dimensions=["crop_type", "region", "channel", "season"],
    required_signal_types=[
        "weather",
        "macro_economic",
        "regulatory",
        "supplier_lead",
    ],
    sku_attribute_schema={
        "product_type": {
            "type": "string",
            "enum": ["pesticide", "feed", "fertilizer", "seed", "equipment"],
        },
        "active_ingredient": {"type": "string"},
        "application_method": {
            "type": "string",
            "enum": ["foliar", "soil", "broadcast", "drip", "manual"],
        },
        "crop_type": {"type": "string"},
        "storage_class": {
            "type": "string",
            "enum": ["ambient", "cool_dry", "flammable", "refrigerated"],
        },
        "regulatory_registration": {"type": "string"},
        "pack_size_kg": {"type": "integer"},
    },
    forecast_models=["TimesFM", "TFT", "N-HiTS", "LightGBM", "Chronos"],
    optimization_models=["OR-Tools", "safety-stock-optimizer", "seasonal-replenishment"],
    audit_level="standard",
)

HARDWARE = IndustryContext(
    code=IndustryCode.hardware.value,
    display_name="Hardware & Industrial Supply",
    default_horizon_weeks=16,
    granularity_dimensions=["category", "region", "channel", "brand"],
    required_signal_types=[
        "competitor_price",
        "macro_economic",
        "supplier_lead",
        "logistics_disruption",
    ],
    sku_attribute_schema={
        "product_type": {
            "type": "string",
            "enum": [
                "tool",
                "fastener",
                "building_material",
                "electrical",
                "plumbing",
                "paint",
                "safety",
            ],
        },
        "material": {"type": "string"},
        "finish": {"type": "string"},
        "dimensions": {"type": "string"},
        "grade": {"type": "string"},
        "voltage": {"type": "string"},
        "power_rating_w": {"type": "integer"},
        "certification": {"type": "string"},
        "pack_size": {"type": "integer"},
    },
    forecast_models=["TimesFM", "TFT", "N-HiTS", "LightGBM", "Chronos"],
    optimization_models=["OR-Tools", "safety-stock-optimizer", "RLlib-replenishment"],
    audit_level="standard",
)

INDUSTRY_REGISTRY: dict[str, IndustryContext] = {
    IndustryCode.fashion.value: FASHION,
    IndustryCode.electronics.value: ELECTRONICS,
    IndustryCode.pharma.value: PHARMA,
    IndustryCode.agrocenter.value: AGROCENTER,
    IndustryCode.hardware.value: HARDWARE,
}


def get_industry_context(code: str) -> IndustryContext:
    ctx = INDUSTRY_REGISTRY.get(code)
    if ctx is None:
        raise ValueError(f"Unknown industry code: '{code}'. Valid: {list(INDUSTRY_REGISTRY)}")
    return ctx
