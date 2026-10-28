"""Real Chronos runtime smoke with explicitly synthetic context; no database writes."""
import json,os,time
from pathlib import Path
os.environ['HF_HUB_OFFLINE']='1'
os.environ['TRANSFORMERS_OFFLINE']='1'
import torch,numpy as np
from sanket_ml.inference.zero_shot import get_chronos_pipeline
start=time.monotonic();pipeline=get_chronos_pipeline()
with torch.inference_mode():
 samples=pipeline.predict([torch.tensor([10,12,11,13,12,14,13,15,14,16,15,17,16,18,17,19],dtype=torch.float32)],prediction_length=4,num_samples=4)
values=samples.cpu().numpy();assert values.shape==(1,4,4);assert np.isfinite(values).all()
q=np.quantile(values,[.1,.5,.9],axis=1);assert np.all(q[0]<=q[1]) and np.all(q[1]<=q[2])
result={'test_context':'explicitly synthetic 16-week series; not Swecha data','real_model_inference':True,'shape':list(values.shape),'finite_outputs':True,'ordered_quantiles':True,'database_writes':False,'elapsed_seconds':round(time.monotonic()-start,2)}
Path(r'C:/Users/admin/Desktop/Prisma/docs/audit/2026-10-27-swecha-client-data/chronos-runtime-smoke.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
