from __future__ import annotations

import pytest

from app.services.industry_context import (
    AGROCENTER,
    ELECTRONICS,
    FASHION,
    INDUSTRY_REGISTRY,
    PHARMA,
    get_industry_context,
)


def test_registry_contains_all_five() -> None:
    assert set(INDUSTRY_REGISTRY.keys()) == {"fashion", "electronics", "pharma", "agrocenter", "hardware"}


def test_pharma_is_gxp_level() -> None:
    assert PHARMA.is_gxp is True
    assert FASHION.is_gxp is False
    assert ELECTRONICS.is_gxp is False
    assert AGROCENTER.is_gxp is False


def test_agrocenter_sku_attribute_product_type_enum() -> None:
    errors = AGROCENTER.validate_sku_attributes({"product_type": "chemicals"})
    assert any("product_type" in e for e in errors)


def test_agrocenter_sku_attribute_valid() -> None:
    errors = AGROCENTER.validate_sku_attributes(
        {"product_type": "pesticide", "storage_class": "flammable"}
    )
    assert errors == []


def test_get_unknown_industry_raises() -> None:
    with pytest.raises(ValueError):
        get_industry_context("toys")


def test_validate_sku_attributes_fashion_size_enum() -> None:
    errors = FASHION.validate_sku_attributes({"size": "XXXXXL"})
    assert any("size" in e for e in errors)


def test_validate_sku_attributes_pharma_storage_class_enum_ok() -> None:
    errors = PHARMA.validate_sku_attributes(
        {"storage_class": "refrigerated", "controlled_substance": False}
    )
    assert errors == []


def test_validate_sku_attributes_type_mismatch() -> None:
    errors = ELECTRONICS.validate_sku_attributes({"model_year": "2024"})  # should be int
    assert any("model_year" in e for e in errors)


def test_effective_horizon_uses_override_when_provided() -> None:
    assert FASHION.effective_horizon(52) == 52
    assert FASHION.effective_horizon(None) == FASHION.default_horizon_weeks
