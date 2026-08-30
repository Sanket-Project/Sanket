# Live browser test — SANKET upload + forecasting (via Claude in Chrome)

**Date:** 2026-07-15
**How:** Logged into the actual running app at `localhost:8080` through the sandbox flow (Fashion & Apparel vertical), and drove the real UI with the Chrome extension — no API shortcuts this time. Cross-checked with the backend container logs in Docker Desktop.

## 1. Upload — reproduced live, and found a second bug beyond the stale backend

Went to **Integrations → Excel Upload**, attached today's file (`Redwine_Label_Fashion_Sales_and_Inventory_Record (1).xlsx`), and tried all three import types the UI offers:

| Import type selected | Result |
|---|---|
| Sales history | `POST /api/v1/integrations/upload` → **400** |
| Inventory levels | `POST /api/v1/integrations/upload` → **400** |
| Product catalog | `POST /api/v1/integrations/upload` → **400** |

Same root cause as before (stale backend container not rebuilt with the newer multi-sheet-detection code — see prior report). That part isn't new.

**What's new: the UI shows the user nothing when this happens.** After each failed attempt, the modal just silently resets — no red error text, no toast, no banner. I checked the page's accessibility tree and console directly: there is no error state rendered anywhere. A real tenant clicking "Import file" today would see the button flash and... nothing. No data, no explanation, no indication anything went wrong. They'd have no way to know why their upload didn't work, or even that it failed at all.

(I also checked the backend container logs during this — the failed upload requests don't show up in the log stream either, so there's no server-side trail to debug from that side right now.)

## 2. Regular forecasting — works
**Forecasts** page → **Generate Live Forecast** → `POST /api/v1/forecasts/generate` → 200. Rendered P10/P50/P90 charts per SKU with reorder guidance, using the 8 SKUs already seeded in the tenant (since the new upload never went through).

## 3. Hybrid forecasting — works, but was flaky
**Hybrid Forecasts** page → **Run hybrid forecast** → this time it completed successfully (202 → polled to completion), showing trend-fused P10/P50/P90 bands per SKU (e.g. `FA-SNEAKER-02`, `FA-JEANS-01`) plus narrative call-outs tied to live signals (port congestion, weather deviations). Note: an identical run through the raw API a short time earlier in this session failed with *"ML baseline unavailable... ml-api returned no forecast rows or was unreachable."* Same feature, different outcome a few minutes apart — worth keeping an eye on for reliability once real upload data is flowing.

## 4. On the requirement: "whatever the tenant uploads, analyze and ingest all of it"

Right now the product doesn't work this way, for two separate reasons:

1. **Immediate bug (fixable with a rebuild):** the running backend is stale, so nothing imports at all today, for any file, regardless of format.
2. **Product gap (needs actual design/dev work, not just a rebuild):** even on the current code in your repo, the importer is built to read **one sheet, mapped to one category** (sales *or* inventory *or* products) per upload — chosen automatically by scoring which sheet has the most recognizable columns. It doesn't inspect a workbook, notice "this tab looks like sales and this other tab looks like inventory," and load both. A tenant with a combined sales+inventory workbook (exactly like the file tested here) will only ever get one of those sheets in, no matter which option they pick in the UI — the other sheet is silently dropped every time.

To actually match "upload whatever data he has and it figures out and loads everything," the import pipeline would need to change from *pick the single best sheet* to *evaluate every sheet independently and ingest each one under whatever category it best matches* — and the UI would need to tell the user what it found and imported per sheet, rather than a single pass/fail for the whole file. That's a real feature change, separate from fixing the stale container.

## Suggested next steps
1. Rebuild the backend so today's importer code is actually running (`docker compose up -d --build backend worker`), then re-test — this alone should get the Sales Ledger sheet importing correctly.
2. Decide whether you want the importer upgraded to handle multiple sheets/categories in a single upload — that's a scoped feature, not a quick fix.
3. Add a visible error/success state to the upload modal so failures are never silent.
