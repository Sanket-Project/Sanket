import csv, math, random, json
from pathlib import Path
from datetime import date,timedelta
out=Path('data/demo-swecha'); out.mkdir(parents=True,exist_ok=True)
rng=random.Random(26102026)
cutoff=date(2026,8,31)
items=[('SYN-KURTI-M','Straight Cut Kurti','Kurtis','M',960,'steady',24),('SYN-KURTI-L','Straight Cut Kurti','Kurtis','L',960,'steady',30),('SYN-LEGGING-XL','Leggings','Leggings','XL',450,'steady',19),('SYN-PALAZZO-L','Palazzo','Palazzo','L',650,'steady',17),('SYN-GOWN-M','Festive Gown','Gowns','M',1800,'seasonal',16),('SYN-KURTI-XL','Straight Cut Kurti','Kurtis','XL',1000,'seasonal',25),('SYN-PATIALA-L','Patiala','Patiala','L',550,'seasonal',20),('SYN-GOWN-XL','Festive Gown','Gowns','XL',1900,'seasonal',12),('SYN-KURTI-3XL','Straight Cut Kurti','Kurtis','XXXL',1105,'intermittent',9),('SYN-KURTI-4XL','Straight Cut Kurti','Kurtis','4XL',1105,'intermittent',7),('SYN-KURTI-5XL','Straight Cut Kurti','Kurtis','5XL',1105,'intermittent',5),('SYN-PALAZZO-3XL','Palazzo','Palazzo','XXXL',750,'intermittent',6)]
def write(name,fields,rows):
    with (out/name).open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
products=[dict(sku=s,name='SYNTHETIC '+n,category=c,size=z,price=p,currency='INR') for s,n,c,z,p,g,b in items]
write('00-products.csv',['sku','name','category','size','price','currency'],products)
rows={g:[] for g in ['steady','seasonal','intermittent']}; hold=[]; inventory=[]
for s,n,c,z,p,g,b in items:
    for week in range(112):
        day=cutoff+timedelta(weeks=week-104)
        for store,factor in [('Boduppal',0.6),('Alwal',0.4)]:
            season=1+0.6*math.sin(2*math.pi*(week-8)/52) if g=='seasonal' else 1
            demand=max(0,round(b*factor*season*(1+week*0.0015)+rng.gauss(0,2)))
            if g=='intermittent' and rng.random()<0.6: demand=0
            row=dict(sku=s,date=day.isoformat(),quantity=demand,price=p,currency='INR',location=store,channel='retail',in_stock='yes')
            (rows[g] if week<104 else hold).append(row)
    for store,factor in [('Boduppal',1),('Alwal',0.5)]:
        inventory.append(dict(sku=s,location=store,available=round(b*factor*3),inbound=10,reserved=0))
fields=['sku','date','quantity','price','currency','location','channel','in_stock']
for i,(g,r) in enumerate(rows.items(),1): write(f'0{i}-{g}-training.csv',fields,r)
write('04-heldout-8-weeks.csv',fields,hold)
write('05-inventory.csv',['sku','location','available','inbound','reserved'],inventory)
write('06-invalid-example.csv',fields,[dict(sku='SYN-BAD',date='not-a-date',quantity=-3,price=960,currency='INR',location='Boduppal',channel='retail',in_stock='yes')])
(out/'manifest.json').write_text(json.dumps({'synthetic':True,'seed':26102026,'training_weeks':104,'test_cutoff':str(cutoff),'heldout_weeks':8,'skus':12,'stores':2,'training_rows':sum(map(len,rows.values())),'heldout_rows':len(hold),'sources':['https://swechafashions.com/','https://swechafashions.com/product/straight-cut-kurthi/'],'provenance':'Categories/store names informed by indexed public pages; all SKU codes, sales, inventory and most prices invented for software testing. Not customer sales.'},indent=2))
print('Created synthetic sample pack: 2496 training rows, 192 held-out rows, 12 SKUs, 2 stores.')
