import openpyxl,csv,json,re,collections,datetime
from pathlib import Path
base=Path(r'C:/Users/admin/Downloads');result=[]
for fn in ['Sales Data 2026.xlsx','Gross Profit Data 2026.xlsx','Purchasr Report 2026.xlsx']:
 w=openpyxl.load_workbook(base/fn,read_only=False,data_only=False)
 for s in w:
  rownum=2 if fn.startswith('Purchasr') else 9
  headers=[c.value for c in s[rownum]]
  dates=collections.Counter();examples={};formulas=0
  for row in s.iter_rows(min_row=rownum+1):
   for c in row:
    if isinstance(c.value,(datetime.datetime,datetime.date)) or (isinstance(c.value,str) and re.fullmatch(r'\d{2}-\d{2}-\d{4}( \d{2}:\d{2}:\d{2} [AP]M)?',c.value)):
     dates[c.column_letter]+=1;examples.setdefault(c.column_letter,str(c.value))
    if c.data_type=='f':formulas+=1
  result.append({'file':fn,'sheet':s.title,'sheet_state':s.sheet_state,'rows':s.max_row,'headers':headers,'date_columns_in_detail':dict(dates),'date_examples':examples,'hidden_columns':[k for k,v in s.column_dimensions.items() if v.hidden],'hidden_rows':sum(v.hidden for v in s.row_dimensions.values()),'formula_cells':formulas,'has_sku_column':'Stock No' in headers,'has_dated_sku_rows':False})
  print(fn,'sheets',w.sheetnames,'headers',headers,'dates',dict(dates),'hidden columns',[k for k,v in s.column_dimensions.items() if v.hidden])
p=base/'stock balence Report 2026.csv';rows=list(csv.DictReader(p.open(encoding='utf-8-sig')))
result.append({'file':p.name,'rows':len(rows),'headers':list(rows[0]),'has_sku_column':True,'has_date_column':False,'has_dated_sku_rows':False})
Path(r'C:/Users/admin/Desktop/Prisma/docs/audit/2026-10-27-swecha-client-data/forecast-source-inspection.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
