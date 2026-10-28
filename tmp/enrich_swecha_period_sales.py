"""Attach verified source period totals to exact matching client SKUs, under RLS."""
import asyncio,json,hashlib,sys
from pathlib import Path
from collections import defaultdict
from decimal import Decimal as D
from sqlalchemy import text
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from app.core.database import Database
from app.config import get_settings
async def main():
 report=ROOT/'docs/audit/2026-10-27-swecha-client-data'
 source=Path(r'C:/Users/admin/Downloads/Gross Profit Data 2026.xlsx')
 manifest=json.loads((report/'source-reconciliation.json').read_text())
 assert hashlib.sha256(source.read_bytes()).hexdigest()==manifest['sources'][source.name]['sha256']
 # Read-only extraction uses the bundled document runtime. This process consumes its JSON intermediate.
 entries=json.loads((ROOT/'tmp/swecha-period-sales.json').read_text())
 cfg=get_settings();assert cfg.app_env=='development' and 'sanket_recovered_20261026' in cfg.database_url
 db=Database(cfg);tid='1fea4cb5-b9f3-45fe-8801-d58c13599d00'
 async with db.session(tid) as s:
  assert await s.scalar(text("SELECT slug FROM tenants WHERE id=:t"),{'t':tid})=='swecha-demo'
  rows=(await s.execute(text('SELECT id,sku_code,attributes FROM skus WHERE tenant_id=:t'),{'t':tid})).all()
  before=await s.scalar(text('SELECT sum(on_hand_units) FROM inventory_levels WHERE tenant_id=:t'),{'t':tid})
  updates=[];positive=0
  for row in rows:
   if row.sku_code in entries:
    assert 'period_sales' not in row.attributes,'Refuse to overwrite an existing period report'
    data=entries[row.sku_code];updates.append({'s':row.id,'t':tid,'a':json.dumps({'period_sales':data})});positive+=data['units']>0
  assert len(updates)==4125 and positive==4014
  await s.execute(text('UPDATE skus SET attributes=attributes || CAST(:a AS jsonb) WHERE id=:s AND tenant_id=:t'),updates)
  assert await s.scalar(text('SELECT sum(on_hand_units) FROM inventory_levels WHERE tenant_id=:t'),{'t':tid})==before==D('38419')
  assert await s.scalar(text('SELECT count(*) FROM historical_sales WHERE tenant_id=:t'),{'t':tid})==0
  # Refresh the source-coverage message while preserving other workspace settings.
  settings=await s.scalar(text('SELECT settings FROM tenants WHERE id=:t'),{'t':tid});summary=settings['client_reports']
  summary['limitations'][0]='Dated SKU sales are unavailable for Chronos. A separate average-sales projection uses the gross-profit report for matching SKUs only; no daily sales history has been fabricated.'
  await s.execute(text('UPDATE tenants SET settings=settings || CAST(:a AS jsonb) WHERE id=:t'),{'t':tid,'a':json.dumps({'client_reports':summary})})
 result={'matched_skus_enriched':len(updates),'positive_period_totals':positive,'excluded_nonpositive_totals':len(updates)-positive,'unmatched_stock_skus':len(rows)-len(updates),'stock_units_unchanged':str(before),'historical_sales_rows':0,'source_days':298,'rls_scoped':True}
 (report/'period-enrichment.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2));await db.close()
asyncio.run(main())
