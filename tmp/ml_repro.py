"""Reproduce the zero-shot forecast for the demo tenant and report peak memory."""
import faulthandler, os, sys, threading, time, uuid
faulthandler.enable()
import psutil
proc = psutil.Process()
peak = [0]
def watch():
    while True:
        peak[0] = max(peak[0], proc.memory_info().rss); time.sleep(0.2)
threading.Thread(target=watch, daemon=True).start()
from sanket_ml.config import get_ml_settings
from sanket_ml.inference.zero_shot import ZeroShotForecaster
s = get_ml_settings()
vm = psutil.virtual_memory()
print(f"batch_size={s.zero_shot_batch_size} num_samples={s.zero_shot_num_samples} total_ram={vm.total/2**30:.1f}GB free={vm.available/2**30:.1f}GB", flush=True)
t0 = time.time()
r = ZeroShotForecaster(s).forecast(tenant_id=uuid.UUID("1fea4cb5-b9f3-45fe-8801-d58c13599d00"), industry="fashion", horizon=12)
print(f"OK series={r.n_series} secs={time.time()-t0:.0f} peak_rss={peak[0]/2**30:.2f}GB", flush=True)
