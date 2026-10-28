"""One-off local development backup and additive migration; never an app connection."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.config import get_settings
from sqlalchemy.engine import make_url

settings = get_settings()
url = make_url(settings.database_url)
if settings.app_env != 'development' or url.host not in {'localhost', '127.0.0.1'} or url.database != 'sanket_recovered_20261026':
    raise SystemExit('Refusing an unexpected database target')
container = 'prisma-postgres-1'
backup = ROOT / 'tmp/backups/ai-demo-20261027-before-0031.dump'
backup.parent.mkdir(parents=True, exist_ok=True)
if backup.exists():
    raise SystemExit('Backup already exists; inspect before continuing')
with backup.open('xb') as target:
    result = subprocess.run(['docker','exec',container,'pg_dump','-U','postgres','-d',url.database,'-Fc'], stdout=target, stderr=subprocess.PIPE)
if result.returncode or backup.read_bytes()[:5] != b'PGDMP':
    raise SystemExit('Backup failed; migration was not run')
with backup.open('rb') as source:
    check = subprocess.run(['docker','exec','-i',container,'pg_restore','--list'], stdin=source, capture_output=True)
if check.returncode:
    raise SystemExit('Backup validation failed; migration was not run')
print(f'Validated local backup: {backup.name}, {backup.stat().st_size} bytes', flush=True)
meta = json.loads(subprocess.check_output(['docker','inspect',container]))[0]
variables = dict(item.split('=',1) for item in meta['Config']['Env'] if '=' in item)
env = dict(os.environ)
# Privileged credentials are used solely through the documented migration URL.
env['MIGRATION_DATABASE_URL'] = url.set(username='postgres',password=variables['POSTGRES_PASSWORD']).render_as_string(hide_password=False)
result = subprocess.run([sys.executable,'-m','alembic','upgrade','0032'], cwd=ROOT/'backend', env=env, capture_output=True, text=True)
(ROOT/'tmp/ai-demo-migration.log').write_text(result.stdout+'\n'+result.stderr, encoding='utf-8')
if result.returncode:
    raise SystemExit('Migration failed; see local migration log. Backup retained.')
print('Local additive migrations completed to 0032. Application credentials unchanged.')
