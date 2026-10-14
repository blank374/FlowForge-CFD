# CRM.cfx5 mesh import assessment (2026-10-13)

Source: `F:/Auto/标准过程/外形/CRM.cfx5`, SHA-256 `9090c20b4e11b25dcd527fea9cdbd501a0ae041e6d8a93c64a1eb4878f532169`.

Pointwise 2024.1 imported this file as an ANSYS CFX unstructured grid using `integrations/crm/inspect_cfx5.glf`. The read-only log is `data/crm_cfx5_pointwise_quality.log`.

| Check | Result |
|---|---:|
| Volume blocks | 1 |
| Boundary domains imported | 2, generic names `dom-1` and `dom-2` |
| Volume cells | 3,722,509 |
| Tetrahedra | 2,609,653 |
| Prisms | 10,411 |
| Hexahedra | 916,924 |
| Negative / zero Jacobian cells | 0 / 0 |
| Minimum Jacobian | 0.003901885 |
| Maximum equiangle skew | 0.982078494 |
| Average equiangle skew | 0.350988990 |

This establishes that the CFX5 file is readable and contains a 3D volume mesh. It does **not** establish that boundary regions, units, physical setup, or OpenFOAM conversion are correct. The worst quality metrics warrant closer inspection before a production solve. ANSA `base.Open` reported `Not a valid CAD file` and yielded no CAD faces or CONS; that was a CAD import attempt, not a test of an ANSA mesh importer. An IGES cannot be recovered exactly from this mesh. The original `DPW4_wb_no_tail_v03.igs` remains beside the CFX5 file.

## ANSA mesh project

ANSA 20.1.6 `InputCFX` successfully imported the mesh and saved `data/CRM_cfx5_mesh.ansa` (268,229,992 bytes). A fresh ANSA process reopened it and counted 1,450,569 nodes, 124,962 shells and 3,722,509 solids, matching the import. It contains **zero CAD FACE entities**. This is a mesh-only ANSA project, not a repaired IGES or editable CAD surface model. Evidence: `data/CRM_cfx5_mesh_conversion.json` and `data/CRM_cfx5_mesh_verify.json`.
