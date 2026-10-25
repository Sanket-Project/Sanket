"""Fashion size variants: 3XL–6XL and free size, normalised but still validated (F06).

Swecha's catalogue lists kurtis through 5XL; creating a 5XL SKU used to return
422 because the enum stopped at XXXL. Each size stays its own SKU — sizes are
never merged to get past validation.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.models.enums import IndustryCode
from app.services.fashion_sizes import CANONICAL_SIZES, normalize_size
from app.services.industry_context import ELECTRONICS, FASHION
from app.services.integrations import file_import as fi


@pytest.mark.parametrize(
    ("raw", "canonical"),
    [
        ("4XL", "4XL"),
        ("5xl", "5XL"),
        (" xxxl ", "3XL"),
        ("2XL", "XXL"),
        ("XXXXL", "4XL"),
        ("xxxxxl", "5XL"),
        ("Free Size", "FREE"),
        ("one-size", "FREE"),
        ("m", "M"),
        ("XL", "XL"),
    ],
)
def test_labels_normalise_to_one_canonical_size(raw, canonical):
    assert normalize_size(raw) == canonical


@pytest.mark.parametrize("raw", ["7XL", "XXXXXXXL", "38", "medium-ish", "", None])
def test_unknown_labels_are_not_guessed(raw):
    assert normalize_size(raw) is None


def test_canonical_sizes_are_ordered_small_to_large():
    assert CANONICAL_SIZES[:5] == ("XS", "S", "M", "L", "XL")
    assert CANONICAL_SIZES.index("3XL") < CANONICAL_SIZES.index("5XL") < CANONICAL_SIZES.index("6XL")


def test_original_label_is_kept_when_it_differs():
    assert FASHION.normalize_sku_attributes({"size": "xxxl", "color": "red"}) == {
        "size": "3XL", "size_label": "xxxl", "color": "red"
    }
    assert FASHION.normalize_sku_attributes({"size": "M"}) == {"size": "M"}


def test_unknown_size_is_still_rejected_with_the_allowed_list():
    errors = FASHION.validate_sku_attributes(FASHION.normalize_sku_attributes({"size": "7XL"}))
    assert errors
    assert "5XL" in errors[0]


def test_other_industries_are_untouched():
    attrs = {"model_year": 2026, "size": "whatever"}
    assert ELECTRONICS.normalize_sku_attributes(attrs) == attrs


async def _product(client, headers) -> str:
    r = await client.post(
        "/api/v1/products", headers=headers,
        json={"name": "Straight kurti (synthetic)", "category": "Kurtis"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def test_create_and_edit_skus_with_extended_sizes(client, signed_in_workspace):
    _, headers = await signed_in_workspace()
    pid = await _product(client, headers)

    created = await client.post(
        f"/api/v1/skus/{pid}/skus", headers=headers,
        json={"sku_code": "KURTI-5XL", "attributes": {"size": "5XL"}},
    )
    legacy = await client.post(
        f"/api/v1/skus/{pid}/skus", headers=headers,
        json={"sku_code": "KURTI-3XL", "attributes": {"size": "xxxl"}},
    )
    rejected = await client.post(
        f"/api/v1/skus/{pid}/skus", headers=headers,
        json={"sku_code": "KURTI-9XL", "attributes": {"size": "9XL"}},
    )

    assert created.status_code == 201, created.text
    assert created.json()["attributes"]["size"] == "5XL"
    assert legacy.json()["attributes"] == {"size": "3XL", "size_label": "xxxl"}
    assert rejected.status_code == 422

    sku_id = created.json()["id"]
    edited = await client.patch(
        f"/api/v1/skus/{sku_id}", headers=headers, json={"attributes": {"size": "4xl"}}
    )
    bad_edit = await client.patch(
        f"/api/v1/skus/{sku_id}", headers=headers, json={"attributes": {"size": "ZZ"}}
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["attributes"]["size"] == "4XL"
    assert bad_edit.status_code == 422


async def test_product_import_keeps_each_size_as_its_own_sku(app_role_db, make_tenant):
    tenant = await make_tenant()
    headers, records = fi.parse_table(
        "catalog.csv",
        b"sku,name,size\nKURTI-4XL,Kurti,4xl\nKURTI-5XL,Kurti,5XL\nKURTI-BAD,Kurti,ZZ\n",
    )

    stats = await fi.import_rows(
        db=app_role_db, tenant_id=tenant, industry=IndustryCode.fashion, kind="products",
        headers=headers, records=records,
    )

    assert stats["rows_imported"] == 2
    assert stats["rows_skipped"] == 1
    assert any("KURTI-BAD" in e and "size" in e for e in stats["errors"])
    async with app_role_db.session(str(tenant)) as s:
        sizes = dict(
            (await s.execute(text("SELECT sku_code, attributes->>'size' FROM skus"))).all()
        )
    assert sizes == {"KURTI-4XL": "4XL", "KURTI-5XL": "5XL"}


async def test_size_curve_merges_spellings_and_orders_by_size(client, db_session, signed_in_workspace):
    tenant, headers = await signed_in_workspace()
    pid = await _product(client, headers)
    ids = {}
    for code, size in [("K-5XL", "5XL"), ("K-M", "M"), ("K-3XL-OLD", "XXXL"), ("K-3XL", "3XL")]:
        sid = uuid.uuid4()
        ids[code] = sid
        # Legacy rows may hold spellings from before normalisation existed.
        await db_session.execute(
            text(
                "INSERT INTO skus (id, tenant_id, product_id, industry, sku_code, attributes) "
                "VALUES (:id, :t, :p, 'fashion', :c, CAST(:a AS jsonb))"
            ),
            {"id": str(sid), "t": str(tenant), "p": pid, "c": code, "a": f'{{"size": "{size}"}}'},
        )
    for code, units in [("K-5XL", 5), ("K-M", 20), ("K-3XL-OLD", 3), ("K-3XL", 4)]:
        await db_session.execute(
            text(
                "INSERT INTO historical_sales (tenant_id, sku_id, industry, sale_time, channel, "
                "units_sold) VALUES (:t, :s, 'fashion', '2026-08-24', 'pos', :u)"
            ),
            {"t": str(tenant), "s": str(ids[code]), "u": units},
        )
    await db_session.commit()

    r = await client.get(f"/api/v1/fashion/size-curve/{pid}", headers=headers)

    assert r.status_code == 200, r.text
    assert [(b["size"], b["units"]) for b in r.json()["size_curve"]] == [
        ("M", 20), ("3XL", 7), ("5XL", 5)
    ]
