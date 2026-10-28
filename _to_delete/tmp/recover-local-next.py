import os, subprocess
from pathlib import Path
from dotenv import dotenv_values
from sqlalchemy.engine import make_url
from app.config import get_settings
values=dotenv_values('../.env')
u=make_url(get_settings().database_url).set(username='postgres',password=values.get('POSTGRES_SUPERUSER_PASSWORD') or 'postgres',database='sanket_recovered_20261026')
env=dict(os.environ, MIGRATION_DATABASE_URL=u.render_as_string(hide_password=False))
for command in [['stamp','0007'],['upgrade','head']]:
    p=subprocess.run([os.sys.executable,'-m','alembic',*command],env=env,capture_output=True,text=True)
    Path('../tmp/startup-recovery/'+command[0]+'-'+command[1]+'.log').write_text(p.stdout+p.stderr)
    print(command, 'exit',p.returncode)
    if p.returncode: raise SystemExit(p.returncode)

