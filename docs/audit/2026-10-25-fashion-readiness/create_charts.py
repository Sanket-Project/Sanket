from pathlib import Path
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

p=Path(__file__).parent
m=json.loads((p/'clean-run/holdout-metrics.json').read_text())
plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
fig,ax=plt.subplots(figsize=(9,3.6),layout='constrained')
names=['Clean Chronos','Repeat last week','Chronos after duplicate import']
values=[8.54,12.36,97.45]
bars=ax.barh(names,values,color=['#0b595e','#87949b','#d45c4d'],height=.56)
ax.invert_yaxis();ax.set_xlim(0,112);ax.set_xlabel('Weighted absolute percentage error (%) - lower is better')
ax.set_title('Synthetic fashion holdout: input integrity dominates forecast quality',loc='left',fontweight='bold',pad=16)
for b,v in zip(bars,values):ax.text(v+1.2,b.get_y()+b.get_height()/2,f'{v:.2f}%',va='center',fontweight='bold')
ax.grid(axis='x',alpha=.15);ax.set_axisbelow(True)
fig.savefig(p/'forecast-comparison.png',dpi=180,bbox_inches='tight');plt.close(fig)
fig,ax=plt.subplots(figsize=(9,3.8),layout='constrained')
x=np.arange(6);a=[r['wape'] for r in m['rows']];b=[r['baselines']['last_value'] for r in m['rows']]
ax.bar(x-.18,a,.36,label='Chronos p50',color='#0b595e');ax.bar(x+.18,b,.36,label='Last-value baseline',color='#a5b0b5')
ax.set_xticks(x,[r['sku'] for r in m['rows']]);ax.set_ylabel('WAPE (%)');ax.set_ylim(0,116)
ax.set_title('Portfolio averages hide weak SKU cohorts',loc='left',fontweight='bold',pad=16)
ax.legend(frameon=False,ncol=2,loc='upper left');ax.grid(axis='y',alpha=.15);ax.set_axisbelow(True)
fig.savefig(p/'sku-comparison.png',dpi=180,bbox_inches='tight');plt.close(fig)
