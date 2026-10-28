import openpyxl,json
from pathlib import Path
from collections import defaultdict
from decimal import Decimal as D
p=Path(r'C:/Users/admin/Downloads/Gross Profit Data 2026.xlsx');s=openpyxl.load_workbook(p,read_only=True,data_only=True).active
assert '01-01-2026 - 25-10-2026' in str(s.cell(1,1).value)
rows=list(s.values)[9:];groups=defaultdict(lambda:{'units':D(0),'locations':defaultdict(D)})
for r in rows:
 if r[1]:
  k=str(r[1]);units=D(str(r[4] or 0));groups[k]['units']+=units;groups[k]['locations'][r[0].strip().lower()]+=units
assert sum(g['units'] for g in groups.values())==D('28923')
out={k:{'start':'2026-01-01','end':'2026-10-25','source':p.name,'units':float(v['units']),'locations':{loc:float(qty) for loc,qty in v['locations'].items()}} for k,v in groups.items()}
Path(r'C:/Users/admin/Desktop/Prisma/tmp/swecha-period-sales.json').write_text(json.dumps(out),encoding='utf-8');print('Verified period totals prepared for',len(out),'source SKUs')
