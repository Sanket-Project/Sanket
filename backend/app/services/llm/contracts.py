from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SerializeAsAny, ValidationError, model_validator

from app.services.llm.errors import AIError, Reason

CanonicalField = Literal[
    "sku", "name", "quantity", "timestamp", "price", "revenue", "discount", "channel",
    "region", "order_id", "line_id", "in_stock", "stockout", "returns", "warehouse",
    "available", "reserved", "inbound", "brand", "category", "description", "gtin",
    "size", "color", "currency",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class Column(StrictModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z][a-zA-Z0-9_-]*$")
    label: str = Field(min_length=1, max_length=512)
    kind: Literal["text", "integer", "decimal", "date", "boolean", "unknown"] = "unknown"


class TaskInput(StrictModel):
    columns: list[Column] = Field(min_length=1, max_length=200)
    allowed_fields: list[CanonicalField] = Field(max_length=30)

    @model_validator(mode="after")
    def unique_ids(self):
        if len({c.id for c in self.columns}) != len(self.columns):
            raise ValueError("Duplicate column ID")
        if len(set(self.allowed_fields)) != len(self.allowed_fields):
            raise ValueError("Duplicate allowed field")
        return self


class Selection(StrictModel):
    column_id: str = Field(min_length=1, max_length=64)
    field: CanonicalField | None
    confidence: Literal["high", "medium", "low", "unknown"]
    reason: Literal["header_meaning", "value_type", "ambiguous", "unsupported"] = "ambiguous"


class MappingOutput(StrictModel):
    selections: list[Selection] = Field(min_length=1, max_length=200)


class AIResult(StrictModel):
    state: Literal["success", "disabled", "policy_blocked", "unavailable", "rate_limited"]
    reason: Reason | None = None
    value: SerializeAsAny[StrictModel] | None = None
    cached: bool = False

    @model_validator(mode="after")
    def consistent_state(self):
        if (self.state == "success") != (self.value is not None):
            raise ValueError("Only success has a value")
        if self.state == "success" and self.reason is not None:
            raise ValueError("Success cannot have an error")
        return self


def validate_output(content: str, task: TaskInput) -> MappingOutput:
    """No values, explanations, SQL, or unbound column/field names are accepted."""
    try:
        output = MappingOutput.model_validate_json(content)
        ids = [selection.column_id for selection in output.selections]
        fields = [selection.field for selection in output.selections if selection.field]
        if (len(ids) != len(set(ids)) or set(ids) != {c.id for c in task.columns}
                or len(fields) != len(set(fields)) or not set(fields) <= set(task.allowed_fields)):
            raise ValueError("Output references invalid or duplicate identifiers")
        return output
    except (ValueError, ValidationError, TypeError):
        raise AIError("invalid_output") from None
