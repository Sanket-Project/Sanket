# SANKET upload + forecasting test — results

**Date:** 2026-07-15
**File tested:** `Redwine_Label_Fashion_Sales_and_Inventory_Record (1).xlsx` (Downloads, most recently downloaded — 15-07-2026 5:01 PM)

## Method note
The Claude-in-Chrome browser extension wasn't connected in this session, so I couldn't click through the web UI directly. Instead I drove the exact same backend endpoints the UI itself calls (via the app's built-in dev/sandbox login, no password needed), which gives a more precise, row-level answer to "did everything upload."

## 1. Project status
Already running via Docker Compose — frontend (:8080), backend (:8000), ml-api (:8001), worker, postgres, redis, grafana, prometheus all healthy. No action needed to start it.

## 2. What's actually in the source file
Three sheets:

| Sheet | Rows | Content |
|---|---|---|
| Executive Summary | 9 (of 14) | Narrative/dashboard text, no real column headers — not tabular data |
| Sales Ledger | 500 | Order ID, Order Date, SKU, Product ID, Product Name, Category, Size, Quantity Ordered, Unit Retail Price, Total Revenue, Unit Product Cost, Total Cost of Goods, Gross Profit Contribution, Fulfillment Warehouse, Sales Channel |
| Warehouse Inventory | 150 | SKU, Product ID, Product Name, Category, Size, Warehouse Code, Fulfillment City, Stock On Hand (Qty), Safety/Reorder Threshold, Unit Cost, Unit Price, Total Asset Value, Inventory Status |

## 3. Upload result: **0 of 650 data rows imported**
I tried uploading the file as all three supported kinds (sales, inventory, products). All three were rejected outright:

- `kind=sales` → 400: *"File is missing required column(s) for sales: quantity, sku, timestamp"*
- `kind=inventory` → 400: *"File is missing required column(s) for inventory: available, sku"*
- `kind=products` → 400: *"File is missing required column(s) for products: sku"*

### Root cause (confirmed, not guessed)
I compared the importer code on disk against the code actually running inside the `backend` container:

- **On disk** (`backend/app/services/integrations/file_import.py`): has smart multi-sheet detection — scores every sheet by how many headers match known field names, and picks the best one. Scoring it against your file: Sales Ledger = 9 matches, Warehouse Inventory = 4, Executive Summary = 0 → it would correctly pick **Sales Ledger**.
- **Inside the running `prisma-backend-1` container**: the file dated **Jul 5** has none of that logic (`grep` for the scoring function found nothing) — it's an older version that just grabs the first/active sheet with no scoring. That lands on **Executive Summary**, which has no real headers, so the importer finds zero usable columns and rejects the whole file.

**In short: the backend container is running stale code.** It was built from an image (`sanket/backend:dev`) that hasn't been rebuilt since this newer importer logic was written — `docker-compose.yml` builds the backend into a static image rather than mounting live source, so code edits don't take effect until you run something like `docker compose up -d --build backend worker`.

### Even after rebuilding, one limitation will remain
The importer only ever reads **one sheet per upload** (whichever scores highest), regardless of which "kind" you select in the UI. For this file, that will always be **Sales Ledger (500 rows)** — the **Warehouse Inventory sheet's 150 rows will never come in through a single upload of this file**, no matter what you pick. To get that inventory data in, you'd need to split it into its own file and upload it separately as "inventory." The Executive Summary tab is correctly ignored (it's not data).

## 4. Forecasting
- **Regular forecast** (`POST /forecasts/generate`, Chronos zero-shot ensemble): ✅ succeeded (200) — returned 208 weekly predictions across 8 SKUs already in the tenant's database. (Not from this file, since the upload never went through — this ran against whatever demo data already existed.)
- **Hybrid forecast** (`POST /forecast/hybrid/runs`): job was accepted (202) but then **failed**: *"ML baseline unavailable: the ml-api returned no forecast rows or was unreachable."* This is a separate issue from the upload problem — worth a look at the ml-api logs if you want the hybrid path working.

## Bottom line
Right now, uploading this file imports **nothing** because of the stale backend build. Once rebuilt, it will import the 500-row Sales Ledger sheet correctly, but the 150-row Warehouse Inventory sheet will still be silently skipped on every upload of this same file — that's a structural limit of the single-sheet importer, not a bug that a rebuild fixes.

Supporting evidence (raw request/response data, sheet inspection, and the code diff proof) saved alongside this report in `qa_artifacts/`.
