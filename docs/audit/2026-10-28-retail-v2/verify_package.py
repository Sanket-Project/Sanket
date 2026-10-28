"""Validate the authored specification assets, not a V2 application implementation."""
from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, date
import csv
import hashlib
import json
import re
import zipfile

root = Path(__file__).resolve().parent
checks = []
def check(label, ok):
    checks.append({'check':label,'passed':bool(ok)})
    if not ok: raise AssertionError(label)

def readcsv(path):
    with path.open(encoding='utf-8',newline='') as f:
        reader=csv.DictReader(f)
        return reader.fieldnames,list(reader)

_,dictionary=readcsv(root/'data_dictionary.csv')
names=['products','skus','inventory','sales','returns','purchases','suppliers','locations']
data={}
for name in names:
    fields=[d for d in dictionary if d['template']==name]
    headers,empty=readcsv(root/'templates'/f'{name}_v2.csv')
    sh,rows=readcsv(root/'samples'/f'{name}_v2_SAMPLE_ONLY.csv')
    check(f'{name}: exact ordered headers and header-only template',headers==sh==[d['column'] for d in fields] and not empty and bool(rows) and len(headers)==len(set(headers)))
    data[name]=rows
    for row in rows:
        check(f'{name}: row width',None not in row)
        check(f'{name}: version marker',row['schema_version']==f'retail_v2.0.{name}')
        for field in fields:
            key=field['column']; v=row[key]; typ=field['data_type']
            if field['requirement']=='R': check(f'{name}.{key}: required',v!='')
            if not v: continue
            if typ=='integer': check(f'{name}.{key}: nonnegative integer',bool(re.fullmatch(r'\d+',v)))
            elif typ.startswith('decimal'):
                d=Decimal(v); scale=int(typ.split(',')[1].rstrip(')'))
                check(f'{name}.{key}: finite nonnegative decimal scale',d.is_finite() and d>=0 and max(0,-d.as_tuple().exponent)<=scale)
            elif typ=='timestamptz': check(f'{name}.{key}: offset timestamp',datetime.fromisoformat(v).utcoffset() is not None)
            elif typ=='date': date.fromisoformat(v)
            elif typ=='boolean': check(f'{name}.{key}: boolean',v in ('true','false'))
            elif typ=='json object': check(f'{name}.{key}: JSON object',isinstance(json.loads(v),dict))
            elif typ=='json array': check(f'{name}.{key}: JSON array',isinstance(json.loads(v),list))
            elif typ.startswith('text('): check(f'{name}.{key}: maximum length',len(v)<=int(typ[5:-1]))
            elif typ.startswith('char('): check(f'{name}.{key}: exact length',len(v)==int(typ[5:-1]))

products={r['product_code']:r for r in data['products']}
skus={r['sku_code']:r for r in data['skus']}
suppliers={r['supplier_code'] for r in data['suppliers']}
locations={r['location_code'] for r in data['locations']}
check('unique catalog/source identities',len(products)==len(data['products']) and len(skus)==len(data['skus']))
check('all SKU parents exist',all(r['product_code'] in products for r in data['skus']))
check('variant signatures unique',len({(r['product_code'],r['color_code'],r['size_system'],r['size_code']) for r in data['skus']})==len(skus))
check('one-size dupatta explicit',any(r['size_code']=='OS' and r['size_system']=='ONE_SIZE' for r in data['skus']))
check('all transactional SKUs/locations exist',all(r['sku_code'] in skus and r['location_code'] in locations for name in ('inventory','sales','returns','purchases') for r in data[name]))
check('all purchasing supplier refs exist',all(r['supplier_code'] in suppliers for r in data['purchases']))
check('no fabricated GTIN GSTIN or HSN',all(not r['gtin'] for r in data['skus']) and all(not r['gstin'] for r in data['suppliers']) and all(not r['hsn_code'] for r in data['products']))
check('master templates own no stock/sales/forecast scalars',all(not set(('warehouse_inventory','forecast_demand','monthly_sales','on_hand_qty'))&set(data[name][0]) for name in ('products','skus')))

money=lambda d: d.quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
sale=data['sales'][0]; ret=data['returns'][0]
qty=int(sale['quantity_sold']); returned=int(ret['returns'])
check('sales/returns single owner and linked',int(sale['returns'])==0 and 0<returned<=qty and ret['original_transaction_id']==sale['transaction_id'] and ret['original_order_line_id']==sale['order_line_id'])
gross=Decimal(sale['unit_price_ex_tax'])*qty
net=money(gross-Decimal(sale['discount_ex_tax']))
tax=money(net*Decimal(sale['tax_rate_pct'])/100)
check('sale tax and tender arithmetic',tax==Decimal(sale['tax_amount']) and net+tax==Decimal(sale['payment_amount']))
check('return original discounted unit and tax',Decimal(ret['return_value_ex_tax'])==net/qty*returned and Decimal(ret['tax_amount'])==tax/qty*returned)
check('refund equals credit with tax',Decimal(ret['refund_amount'])==Decimal(ret['return_value_ex_tax'])+Decimal(ret['tax_amount']))
remaining_revenue=net-Decimal(ret['return_value_ex_tax'])
cost=Decimal(skus[sale['sku_code']]['reference_cost_ex_tax'])*(qty-returned)
check('demonstration GP with stated historical cost assumption',remaining_revenue==900 and cost==600 and remaining_revenue-cost==300)

opening={r['sku_code']:int(r['on_hand_qty']) for r in data['inventory']}
for row in data['inventory']:
    check('inventory disjoint buckets valid',sum(int(row[k]) for k in ('reserved_qty','damaged_qty','quarantine_qty'))<=int(row['on_hand_qty']))
    check('opening snapshot precedes sample sale',datetime.fromisoformat(row['as_of'])<datetime.fromisoformat(sale['transaction_at']))
documents={r['document_id']:r for r in data['purchases']}
check('procurement document types covered',{r['document_type'] for r in data['purchases']}=={'purchase_order','goods_receipt','supplier_invoice','purchase_return'})
for row in data['purchases']:
    check('PO relationship valid',row['po_id'] in documents and row['po_line_id']==documents[row['po_id']]['document_line_id'])
    if row['related_document_id']:
        check('receipt relationship valid',row['related_document_id'] in documents and row['related_document_line_id']==documents[row['related_document_id']]['document_line_id'])
    taxable=Decimal(row['quantity'])*Decimal(row['unit_cost_ex_tax'])-Decimal(row['discount_ex_tax'])+Decimal(row['freight_ex_tax'])
    check('purchase sample tax arithmetic',money(taxable*Decimal(row['tax_rate_pct'])/100)==Decimal(row['tax_amount']))
physical=opening[sale['sku_code']]-qty+returned
for row in data['purchases']:
    if row['document_type']=='goods_receipt': physical+=int(row['quantity'])
    if row['document_type']=='purchase_return': physical-=int(row['quantity'])
check('sample stock roll-forward',physical==28)
check('sample ATS roll-forward',physical-2-1==25)

manifest=json.loads((root/'source_manifest.json').read_text(encoding='utf-8'))
for entry in manifest:
    check('source unchanged since inspection: '+Path(entry['file']).name,hashlib.sha256(Path(entry['file']).read_bytes()).hexdigest()==entry['sha256'])
prior=json.loads((root.parent/'2026-10-27-swecha-client-data/source-reconciliation.json').read_text(encoding='utf-8'))
check('four original hashes match prior audit',all(entry['sha256']==prior['sources'][Path(entry['file']).name]['sha256'] for entry in manifest[:4]))
profile=json.loads((root/'data_profile.json').read_text(encoding='utf-8'))
controls=[{'file':p['file'],'column':c['header'],'detail_sum':c['detail_sum'],'footer_control':c['footer_control'],'delta':c['detail_minus_footer']} for p in profile for c in p['columns'] if 'footer_control' in c]
check('required deliverables exist',all((root/p).exists() for p in ('README.md','AUDIT.md','ARCHITECTURE.md','DATA_DICTIONARY.md','IMPORT_SPEC.md','ANALYTICS_AND_ROADMAP.md','SOURCES.md')))
result={'scope':'Document/CSV asset verification only; not V2 application tests','checks_passed':len(checks),'failed':0,'template_count':8,'sample_file_count':8,'dictionary_fields':len(dictionary),'synthetic_roll_forward':{'net_sales_ex_tax':'900.00','net_cogs_assuming_confirmed_original_unit_cost_600':'600.00','gross_profit':'300.00','kurti_on_hand':physical,'kurti_available_to_sell':25},'fresh_client_footer_comparisons':controls,'repository_checks':'See CHECKS.md for separately executed repository test results.'}
(root/'verification.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,indent=2))

archive=root/'Fashion_Retail_V2_Review_Package.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for path in sorted(root.rglob('*')):
        if path.is_file() and path.suffix in ('.md','.csv','.json','.mmd'):
            z.write(path,path.relative_to(root))
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
print('ZIP verified:',archive.name)
