from pathlib import Path
import openpyxl,csv,json,hashlib
from decimal import Decimal as D
from collections import defaultdict
from datetime import datetime
base=Path(r'C:/Users/admin/Downloads');root=Path(r'C:/Users/admin/Desktop/Prisma')
def dec(v):return D(str(v or 0))
def sheet(fn):return list(openpyxl.load_workbook(base/fn,read_only=True,data_only=True).active.values)
sales=sheet('Sales Data 2026.xlsx');gp=sheet('Gross Profit Data 2026.xlsx');purchases=sheet('Purchasr Report 2026.xlsx')
sr=[r for r in sales[9:] if isinstance(r[1],datetime)]
gr=[r for r in gp[9:] if r[1] is not None and str(r[1]).strip()]
pr=[r for r in purchases[2:] if r[0] in ('Purchase','Purchase Return')]
def total(rows,col):return sum((dec(r[col]) for r in rows),D(0))
# Reconcile detail against supplied grand totals; sales report uses one subtotal per store.
assert total(gr,4)==dec(gp[-1][4]);assert total(gr,5)==dec(gp[-1][5]);assert abs(total(gr,9)-dec(gp[-1][9]))<=D('.02')
assert total(pr,4)==dec(purchases[-1][4]);assert total(pr,7)==dec(purchases[-1][7])
sub=[r for r in sales if str(r[0]).strip()=='Sub Total :']
assert total(sr,10)==total(sub,10);assert total(sr,11)==total(sub,11)
def grouped(rows,key,fields):
 groups=defaultdict(lambda:{k:D(0) for k in fields})
 for r in rows:
  for k,i in fields.items():groups[str(r[key])][k]+=dec(r[i])
 return [dict(name=n,**{k:float(v) for k,v in values.items()}) for n,values in sorted(groups.items())]
skus=defaultdict(lambda:{'units':D(0),'profit':D(0)})
for r in gr:skus[str(r[1])]['units']+=dec(r[4]);skus[str(r[1])]['profit']+=dec(r[9])
report={'industry':'fashion','currency':'INR','imported_at':'2026-10-27',
 'sales':{'period':'1–25 October 2026','net_amount':float(total(sr,11)),'net_units':float(total(sr,10)),'rows':len(sr),'stores':grouped(sr,0,{'net_amount':11,'net_units':10})},
 'gross_profit':{'period':'1 January–25 October 2026','net_sales':float(total(gr,5)),'sales_ex_tax':float(total(gr,6)),'cogs_ex_tax':float(total(gr,8)),'profit':float(total(gr,9)),'margin_pct':float(total(gr,9)/total(gr,6)*100) if total(gr,6) else None,'rows':len(gr),'stores':grouped(gr,0,{'profit':9,'sales_ex_tax':6}),'top_skus':[dict(sku=k,units=float(v['units']),profit=float(v['profit'])) for k,v in sorted(skus.items(),key=lambda x:x[1]['profit'],reverse=True)[:20]]},
 'purchases':{'period':f"{pr[0][1][:10]}–{pr[-1][1][:10]} (day-month-year)",'net_amount':float(total(pr,7)),'net_units':float(total(pr,4)),'rows':len(pr),'suppliers':sorted(grouped(pr,3,{'net_amount':7,'net_units':4}),key=lambda r:r['net_amount'],reverse=True)},
 'limitations':['Dated SKU sales are unavailable; forecasts require SKU-level sales history. Store sales and period gross profit have not been converted into SKU transactions.','Sales and gross profit cover different periods and must not be added together. Gross profit uses sales and cost excluding tax. Purchases include taxes, discounts and signed purchase returns.','The stock report does not specify its snapshot date. Inventory records use the import time; confirm the stock date before making operational decisions.','Catalogue prices use the first reported location for each SKU; original cost, retail price and closing value are retained on each stock position.','Reserved stock, inbound stock, supplier lead times and reorder thresholds were not supplied. Stock coverage and replenishment recommendations require additional inputs.'],
 'sources':['stock balence Report 2026.csv','Sales Data 2026.xlsx','Gross Profit Data 2026.xlsx','Purchasr Report 2026.xlsx']}
(root/'tmp/swecha-client-reports.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
manifest={'sources':{fn:{'sha256':hashlib.sha256((base/fn).read_bytes()).hexdigest(),'bytes':(base/fn).stat().st_size} for fn in report['sources']},'sales_rows':len(sr),'gross_profit_rows':len(gr),'purchase_rows':len(pr),'totals_reconciled':True,'sales_net':str(total(sr,11)),'sales_units':str(total(sr,10)),'gp_sales':str(total(gr,5)),'gross_profit':str(total(gr,9)),'purchases_net':str(total(pr,7))}
(root/'docs/audit/2026-10-27-swecha-client-data/source-reconciliation.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8');print(json.dumps(manifest,indent=2))
