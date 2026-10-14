# ANSA 20.1.6 几何门槛改动与真实测试

源文件 `backend/ansa_geometry_gate.py` 先导入 IGS 并保存独立 `review.ansa`，再在 ANSA 内存/工作副本中执行基础 Topo。未调用容差设置、自动填洞或修复函数。测试前后核对上传源文件 SHA-256 均未变化。

本机 ANSA 20.1.6 Python API 文档：`docs/extending/python_api/build_ansa/html/_sources/base.rst.txt`。其中 `Topo(cons, paste_with_frozen_faces, paste_different_pids)` 使用 ANSA 当前容差；`cons="all"` 处理全部 CONS，返回 0 表示没有输入 CONS、1 表示执行。采用 `Topo(cons="all", paste_with_frozen_faces=False, paste_different_pids=False)`。没有发现必须另行调用的拓扑更新 API，整理后重新 `CollectEntities` / `GetFacesOfCons` 统计。

`CheckIntersections(False, False, True)` 文档说明它检查有限元**单元**，返回 `None` 表示无相交；`fast_run=False, return_regions=True` 时返回按区域分组的列表。它不证明 CAD 曲面无自相交。几何另用 `CheckAndFixGeometry(0, options, [0,...], True, True)` 只检查裂缝、重叠、针状面、塌陷 CONS、三重 CONS，不执行 fix。

| 输入 | Topo 前 FACE / CONS / 自由 CONS | Topo 后 FACE / CONS / 自由 CONS | 非流形 / 几何错误 / FE 相交区域 | 结果 |
|---|---:|---:|---:|---|
| 上传的 `DPW4_wb_no_tail_v03.igs` | 20 / 76 / 76 | 20 / 53 / 20 | 0 / 0 / 1（8 个单元） | `NEEDS_MANUAL_REPAIR`：开放边用途不明且有 FE 单元相交。 |
| 演示飞机 `demo_aircraft_test.igs` | 6 / 24 / 24 | 6 / 12 / 0 | 0 / 0 / 0 | 检查项通过；工作流仍进入人工审核，通用 CFD 下游仍阻断。 |
| L1 `test_sphere_20mm.igs` | 3 / 7 / 7 | 3 / 5 / 1 | 0 / 0 / 0 | `WAITING_FOR_REVIEW`：一条开放 CONS 的用途须工程师说明。独立的原 L1 全链回归通过。 |

原 L1 全链回归任务 `6fa52c0a3cf7402693ecbbbb1ecb1072`、关联运行 `8e870de79700469898329d503a758154`：八阶段均为 `PASSED`，生成 `report.md`。通用 ANSA 门槛不会替代 L1 专用几何门槛。

完整 JSON、ANSA 日志和独立工作工程保存在 `data/verification/geometry_gate_20261014_aircraft/`、`geometry_gate_20261014_demo_aircraft/`、`geometry_gate_20261014_l1/`；`data/` 被 Git 忽略。
