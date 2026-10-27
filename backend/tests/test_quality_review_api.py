async def test_quality_review_api_returns_bound_preview_and_rejects_unconfirmed_tokenless_write(client, signed_in_workspace):
    _, headers = await signed_in_workspace("fashion")
    preview = await client.post("/api/v1/ai/data-quality/fix", headers=headers, json={"action": "dedupe_sales", "confirm": False})
    assert preview.status_code == 200, preview.text
    assert preview.json()["preview_token"]
    refused = await client.post("/api/v1/ai/data-quality/fix", headers=headers, json={"action": "dedupe_sales", "confirm": True})
    assert refused.status_code == 409
