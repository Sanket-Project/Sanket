from pathlib import Path
import subprocess

paths = [
    'backend/app/routers/ai.py', 'backend/app/services/llm/context.py', 'backend/app/services/llm/explanations.py',
    'backend/app/services/llm/facts.py', 'backend/tests/llm/test_explanations.py', 'backend/tests/llm/test_facts.py',
    'frontend/src/api/ai.ts', 'frontend/src/components/ai/AISettings.tsx', 'frontend/src/components/ai/AISettings.test.tsx',
    'frontend/src/components/ai/AISummary.tsx', 'frontend/src/components/ai/AISummary.test.tsx',
    'frontend/src/pages/Decisions.tsx', 'frontend/src/pages/Decisions.test.tsx',
    'frontend/src/pages/ForecastAccuracy.tsx', 'frontend/src/pages/ForecastAccuracy.test.tsx',
    'frontend/src/pages/ShortageAlerts.tsx', 'frontend/src/pages/ShortageAlerts.test.tsx',
]
subprocess.run(['git','add','--',*paths], check=True)

def stage_blob(path, content):
    sha = subprocess.check_output(['git','hash-object','-w','--stdin'], input=content.encode()).decode().strip()
    subprocess.run(['git','update-index','--cacheinfo',f'100644,{sha},{path}'], check=True)

path = 'frontend/src/components/dashboard/PlanningBriefDashboard.tsx'
original = subprocess.check_output(['git','show','HEAD:'+path]).decode()
original = original.replace('import { Link } from "react-router-dom";', 'import { Link } from "react-router-dom";\nimport { AISummary } from "@/components/ai/AISummary";', 1)
line = next(line for line in Path(path).read_text(encoding='utf-8').splitlines() if '<AISummary feature="planning_brief"' in line)
original = original.replace('    <div className="animate-fade-in space-y-3">', '    <div className="animate-fade-in space-y-3">\n'+line, 1)
stage_blob(path, original)
path = 'frontend/src/components/dashboard/PlanningBriefDashboard.test.tsx'
original = subprocess.check_output(['git','show','HEAD:'+path]).decode()
current = Path(path).read_text(encoding='utf-8')
original = original.replace('import { fireEvent,', 'import { act, fireEvent,', 1)
new_test = current[current.index('it("offers an optional grounded summary'):]
stage_blob(path, original+'\n'+new_test)
print('Staged only Phase 2 changes; overlapping dashboard work remains in the working tree.')
