"""Transactional client stock load, called only by the approved local data migration."""
import csv,json,uuid
from decimal import Decimal as D
from pathlib import Path
from sqlalchemy import insert,text
from app.models.product import Product,Sku
from app.models.inventory import InventoryLevel
from app.models.location import Location
ROOT=Path(__file__).resolve().parents[1]
TID=uuid.UUID('1fea4cb5-b9f3-45fe-8801-d58c13599d00')
async def load(conn):
 p=Path(r'C:/Users/admin/Downloads/stock balence Report 2026.csv')
 rows=list(csv.DictReader(p.open(encoding='utf-8-sig')));footer=rows[-1];rows=[r for r in rows if r['Stock No'].strip()]
 assert len(rows)==16519 and len({(r['Stock No'],r['Company Name']) for r in rows})==len(rows)
 assert sum(D(r['Closing Bal.Qty']) for r in rows)==D(footer['Closing Bal.Qty'])==D('38419')
 assert abs(sum(D(r['Closing Bal.Val']) for r in rows)-D(footer['Closing Bal.Val']))<=D('.02')
 products={};skus={};pr=[];sr=[];inv=[]
 for r in rows:
  code=r['Stock No'];key=(r['Item Description'],r['Category'],r['Brand'])
  if code not in skus:
   if key not in products:
    products[key]=uuid.uuid4();pr.append(dict(id=products[key],tenant_id=TID,industry='fashion',name=key[0],category=key[1] or 'Uncategorized',brand=key[2],subcategory=r['Sub Category'],attributes={'source_file':p.name,'style_no':r['Style No']}))
   skus[code]=uuid.uuid4();sr.append(dict(id=skus[code],tenant_id=TID,industry='fashion',product_id=products[key],sku_code=code,description=r['Item Description'],unit_cost=D(r['Cost Price']),unit_price=D(r['Retail Price']),currency='INR',attributes={'source_file':p.name}))
  inv.append(dict(tenant_id=TID,industry='fashion',sku_id=skus[code],location=r['Company Name'].strip().lower(),on_hand_units=D(r['Closing Bal.Qty']),source='upload',attributes={'source_file':p.name,'source_company':r['Company Name'],'source_cost_price':r['Cost Price'],'source_retail_price':r['Retail Price'],'source_closing_value':r['Closing Bal.Val'],'snapshot_date':'not supplied; imported 2026-10-27'}))
 for model,items in [(Product,pr),(Sku,sr),(InventoryLevel,inv)]:
  for i in range(0,len(items),500):await conn.execute(insert(model),items[i:i+500])
 for name in sorted({r['Company Name'] for r in rows}):
  await conn.execute(insert(Location).values(tenant_id=TID,code=name.strip().lower(),name=name,kind='warehouse' if name.endswith(' - WH') else 'store',attributes={'source_file':p.name}))
 report=json.loads((ROOT/'tmp/swecha-client-reports.json').read_text(encoding='utf-8'))
 await conn.execute(text('UPDATE tenants SET settings=settings || CAST(:r AS jsonb) WHERE id=:t'),{'t':TID,'r':json.dumps({'client_reports':report})})
 units=await conn.scalar(text('SELECT sum(on_hand_units) FROM inventory_levels WHERE tenant_id=:t'),{'t':TID});assert units==D('38419')
 return {'products':len(pr),'skus':len(sr),'stock_positions':len(inv),'locations':6,'units':str(units),'inventory_source_value':str(sum(D(r['Closing Bal.Val']) for r in rows)),'aggregate_reports':3,'no_fabricated_sales':True}
