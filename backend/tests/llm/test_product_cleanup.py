import json

import pytest
from pydantic import ValidationError

from app.services.llm.errors import AIError


def input_data():
    return {"industry": "fashion", "products": [{"id": "sku_a", "name": "Cotton Blue Shirt XL", "revision": "v1"},
                                                 {"id": "sku_b", "name": "Cotton blue shirt XL", "revision": "v1"}],
            "categories": ["Shirts", "Accessories"]}


def test_cleanup_extracts_only_evidence_backed_supported_attributes_and_categories():
    from app.services.llm.tasks import request_for
    task = request_for("product_cleanup", input_data())
    output = task.validate(json.dumps({"suggestions": [
        {"product_id": "sku_a", "field": "size", "value": "XL", "evidence": "XL", "confidence": "high"},
        {"product_id": "sku_a", "field": "color", "value": "Blue", "evidence": "Blue", "confidence": "medium"},
        {"product_id": "sku_a", "field": "category", "value": "Shirts", "evidence": "Shirt", "confidence": "medium"}],
        "duplicate_pairs": [["sku_a", "sku_b"]]}))
    assert output.suggestions[0].value == "XL"
    assert task.spec.permission == "product_names"


@pytest.mark.parametrize("suggestion", [
    {"product_id": "foreign", "field": "size", "value": "XL", "evidence": "XL", "confidence": "high"},
    {"product_id": "sku_a", "field": "color", "value": "Red", "evidence": "Red", "confidence": "high"},
    {"product_id": "sku_a", "field": "unit_price", "value": "100", "evidence": "XL", "confidence": "high"},
    {"product_id": "sku_a", "field": "category", "value": "Medicine", "evidence": "Shirt", "confidence": "high"},
])
def test_cleanup_rejects_unbound_attributes_foreign_ids_and_unsupported_fields(suggestion):
    from app.services.llm.tasks import request_for
    with pytest.raises(AIError, match="invalid_output"):
        request_for("product_cleanup", input_data()).validate(json.dumps({"suggestions": [suggestion], "duplicate_pairs": []}))


def test_names_containing_contact_details_are_not_sent_to_provider():
    from app.services.llm.cleanup import CleanupInput
    body = input_data()
    body["products"][0]["name"] = "Contact jane@example.test for this shirt"
    with pytest.raises(ValidationError):
        CleanupInput.model_validate(body)
