import struct
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from matplotlib.collections import PolyCollection

folder=Path(__file__).resolve().parents[2]/'deliverables/crm_like_wb_clean'
raw=(folder/'preview.stl').read_bytes()
count=struct.unpack_from('<I',raw,80)[0]
tri=np.array([struct.unpack_from('<9f',raw,84+50*i+12) for i in range(count)]).reshape(-1,3,3)
fig=plt.figure(figsize=(12,6),facecolor='white')
ax=fig.add_subplot(121)
xy=tri.reshape(-1,3)
ax.add_collection(PolyCollection(tri[:,:,:2],facecolors='#246687',edgecolors='none'))
ax.set_xlim(-800,800);ax.set_ylim(-650,650)
ax.set_aspect('equal');ax.set_xlabel('X (mm)');ax.set_ylabel('Y (mm)');ax.set_title('Top view - no-tail swept wing body')
ax=fig.add_subplot(122,projection='3d')
ax.add_collection3d(Poly3DCollection(tri,facecolor='#65a5c6',edgecolor='none',linewidth=0))
ax.set_xlim(-780,780);ax.set_ylim(-650,650);ax.set_zlim(-100,100)
ax.set_box_aspect((1500,1300,200));ax.view_init(28,-55)
ax.set_xlabel('X (mm)');ax.set_ylabel('Y (mm)');ax.set_zlabel('Z (mm)')
ax.set_title('Closed CAD demonstration geometry')
ax.set_axis_off()
fig.suptitle('CRM-like layout demonstration - not the CRM reference geometry')
fig.tight_layout(rect=(0,0,1,0.90));fig.savefig(folder/'preview.png',dpi=150)
