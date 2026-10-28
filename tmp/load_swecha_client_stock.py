import asyncio,csv,json,uuid,hashlib,sys
from pathlib import Path
from decimal import Decimal as D
from sqlalchemy import select,func,insert,text
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.core.database import Database
from app.config import get_settings
from app.models.product import Product,Sku
from app.models.inventory import InventoryLevel
from app.models.location import Location
from app.models.tenant import Tenant
TID=uuid.UUID('1fea4cb5-b9f3-45fe-8801-d58c13599d00')
P=Path(r'C:/Users/admin/Downloads/stock balence Report 2026.csv')
async def main():
 db=Database(get_settings()); rows=list(csv.DictReader(P.open(encoding='utf-8-sig')));rows=[r for r in rows if r['Stock No'].strip()]
 out=ROOT/'docs/audit/2026-10-27-swecha-client-data';out.mkdir(parents=True,exist_ok=True)
 async with db.session(str(TID)) as s:
  role=(await s.execute(text('SELECT current_user, rolsuper, rolbypassrls FROM pg_roles WHERE rolname=current_user'))).one()
  assert not role[1] and not role[2], 'Application connection must enforce RLS'
  t=await s.scalar(select(Tenant).where(Tenant.id==TID));assert t.slug=='swecha-demo'
  assert await s.scalar(select(func.count()).select_from(Sku))==0,'Refuse to overwrite existing catalogue'
  assert await s.scalar(select(func.count()).select_from(InventoryLevel))==0
  products={};skus={};pr=[];sr=[];inv=[]
  for r in rows:
   code=r['Stock No'];key=(r['Item Description'],r['Category'],r['Brand'])
   if code not in skus:
    if key not in products:
     products[key]=uuid.uuid4();pr.append(dict(id=products[key],tenant_id=TID,industry='fashion',name=key[0],category=key[1] or 'Uncategorized',brand=key[2],subcategory=r['Sub Category'],attributes={'source_file':P.name,'style_no':r['Style No']}))
    skus[code]=uuid.uuid4();sr.append(dict(id=skus[code],tenant_id=TID,industry='fashion',product_id=products[key],sku_code=code,description=r['Item Description'],unit_cost=D(r['Cost Price']),unit_price=D(r['Retail Price']),currency='INR',attributes={'source_file':P.name}))
   inv.append(dict(tenant_id=TID,industry='fashion',sku_id=skus[code],location=r['Company Name'].strip().lower(),on_hand_units=D(r['Closing Bal.Qty']),source='upload',attributes={'source_file':P.name,'source_company':r['Company Name'],'source_cost_price':r['Cost Price'],'source_retail_price':r['Retail Price'],'source_closing_value':r['Closing Bal.Val'],'snapshot_date':'not supplied; imported 2026-10-27'}))
  for model,items in [(Product,pr),(Sku,sr),(InventoryLevel,inv)]:
   for i in range(0,len(items),500):await s.execute(insert(model),items[i:i+500])
  for name in sorted({r['Company Name'] for r in rows}):
   await s.execute(insert(Location).values(tenant_id=TID,code=name.strip().lower(),name=name,kind='warehouse' if name.endswith(' - WH') else 'store',attributes={'source_file':P.name}))
  units=await s.scalar(select(func.sum(InventoryLevel.on_hand_units)))
  assert units==D('38419')
  report={'tenant_slug':t.slug,'connection_role':role[0],'rls_enforced':True,'source_sha256':hashlib.sha256(P.read_bytes()).hexdigest(),'products':len(pr),'skus':len(sr),'inventory_positions':len(inv),'locations':6,'units':str(units),'source_inventory_value':str(sum(D(r['Closing Bal.Val']) for r in rows)),'sales_history_imported':False,'limitations':['Sales report is store/day aggregate without SKU','Gross profit is SKU/store period aggregate without sale dates','Purchases contain supplier invoices without SKU lines','Stock snapshot date not supplied; recorded import time; source prices retained per position']}
 (out/'import-verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
 await db.close()
asyncio.run(main())
