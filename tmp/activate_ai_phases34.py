"""Back up then apply approved additive local migrations. Never print credentials."""
import json, os, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BACKEND=ROOT/'backend'
sys.path.insert(0,str(BACKEND))
os.chdir(BACKEND)
from app.config import get_settings
from sqlalchemy.engine import make_url
settings=get_settings()
app_url=make_url(settings.database_url)
if app_url.host not in {'localhost','127.0.0.1'} or app_url.database!='sanket_recovered_20261026':
    raise SystemExit('Unexpected local database target; no mutation performed')
info=json.loads(subprocess.check_output(['docker','inspect','prisma-postgres-1']))[0]
ports=info['NetworkSettings']['Ports'].get('5432/tcp',[])
if str(app_url.port or 5432) not in {p['HostPort'] for p in ports}:
    raise SystemExit('Container does not own configured database port; no mutation performed')
values=dict(item.split('=',1) for item in info['Config']['Env'] if '=' in item)
user=values.get('POSTGRES_USER','postgres')
backup=ROOT/'tmp'/'backups'/'ai-phases34-before.dump'
backup.parent.mkdir(parents=True,exist_ok=True)
if backup.exists():
    raise SystemExit('Backup already exists; refusing to overwrite it')
with backup.open('wb') as output:
    result=subprocess.run(['docker','exec','prisma-postgres-1','pg_dump','-U',user,'-d',app_url.database,'-Fc'],stdout=output,stderr=subprocess.PIPE)
if result.returncode:
    raise SystemExit('Backup failed; no migration performed')
with backup.open('rb') as source:
    result=subprocess.run(['docker','exec','-i','prisma-postgres-1','pg_restore','--list'],stdin=source,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
if result.returncode or backup.stat().st_size<1024:
    raise SystemExit('Backup validation failed; no migration performed')
print('Local custom-format backup validated; bytes:',backup.stat().st_size,flush=True)
env=dict(os.environ)
env['MIGRATION_DATABASE_URL']=app_url.set(username=user,password=values.get('POSTGRES_PASSWORD')).render_as_string(hide_password=False)
result=subprocess.run([sys.executable,'-m','alembic','upgrade','head'],cwd=BACKEND,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
if result.returncode:
    # Exception messages can embed a URL: keep them local, never print credentials.
    (ROOT/'tmp'/'ai-phases34-migration-private.log').write_bytes(result.stdout+result.stderr)
    raise SystemExit('Migration failed; private local log retained for diagnosis')
print('Approved additive migrations applied successfully',flush=True)
