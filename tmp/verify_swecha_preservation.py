import asyncio,json,subprocess,re,hashlib
from pathlib import Path
from sqlalchemy import text
from app.core.database import Database
from app.config import get_settings
ROOT=Path(r'C:/Users/admin/Desktop/Prisma');tid='1fea4cb5-b9f3-45fe-8801-d58c13599d00'
raw=subprocess.check_output(['docker','exec','-i','prisma-postgres-1','pg_restore','--data-only','--table=tenants','--file=-'],input=(ROOT/'backups/swecha-before-client-import-2026-10-27.dump').read_bytes()).decode()
m=re.search(r'COPY public.tenants \((.*?)\) FROM stdin;\n(.*?)\n\\\.',raw,re.S);assert m
cols=m[1].split(', ')
row=next(line.split('\t') for line in m[2].splitlines() if line.startswith(tid+'\t'))
def unescape(s):return re.sub(r'\\(.)',lambda m:{'t':'\t','n':'\n','r':'\r','\\':'\\'}.get(m[1],m[1]),s)
original=dict(zip(cols,map(unescape,row)))
async def main():
 d=Database(get_settings());report={}
 async with d.session(tid) as s:
  current=(await s.execute(text('select display_name,settings from tenants where id=:t'),{'t':tid})).one()
  settings=dict(current.settings);settings.pop('client_reports')
  assert settings==json.loads(original['settings']);assert current.display_name==original['display_name']
  saved=json.loads((ROOT/'docs/audit/2026-10-27-swecha-client-data/apply.json').read_text())
  # Login verification legitimately changes last_login_at / refresh rows; verify stable credentials directly against backup separately below.
  assert await s.scalar(text('select count(*) from historical_sales where tenant_id=:t'),{'t':tid})==0
  assert await s.scalar(text('select count(*) from forecast_results where tenant_id=:t'),{'t':tid})==0
  assert await s.scalar(text('select sum(on_hand_units) from inventory_levels where tenant_id=:t'),{'t':tid})==38419
  report={'original_workspace_settings_preserved':True,'workspace_identity_preserved':True,'client_reports_added':True,'stock_units':38419,'fabricated_sales':0,'forecast_results':0,'backup_validated':True,'other_tenants_unchanged_during_migration':saved['other_tenants_unchanged']}
 rawusers=subprocess.check_output(['docker','exec','-i','prisma-postgres-1','pg_restore','--data-only','--table=users','--file=-'],input=(ROOT/'backups/swecha-before-client-import-2026-10-27.dump').read_bytes()).decode()
 um=re.search(r'COPY public.users \((.*?)\) FROM stdin;\n(.*?)\n\\\.',rawusers,re.S);uc=um[1].split(', ')
 originals=[dict(zip(uc,map(unescape,line.split('\t')))) for line in um[2].splitlines() if tid in line]
 async with d.session(tid) as s:
  for u in originals:
   live=(await s.execute(text('select id,email,password_hash,role,full_name from users where id=:u and tenant_id=:t'),{'u':u['id'],'t':tid})).mappings().one()
   assert all(str(live[k])==u[k] for k in live)
 report['login_credentials_and_roles_preserved']=True
 (ROOT/'docs/audit/2026-10-27-swecha-client-data/final-data-verification.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
 await d.close()
asyncio.run(main())
