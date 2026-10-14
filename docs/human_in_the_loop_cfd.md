# FlowForge CFD：脚本与人工协作流程

更新：2026-10-14。目标是让脚本完成可重复、可核对的操作，由工程师决定几何修复、物理模型与结果是否可信。每个项目保留原始输入、运行目录、软件版本、日志和人工签字记录。任一质量门槛未通过时，后续脚本停止；人工在副本上修复后创建**新运行**，不得覆盖旧失败记录。

## 分工与停机点

| 阶段 | 脚本负责 | 必须人工负责 | 继续条件 |
|---|---|---|---|
| 接收模型 | 复制输入、计算 SHA-256、识别格式、只读盘点单位/实体/分组 | 确认模型版本、坐标系、长度单位和使用许可；说明是 CAD 还是已有网格 | 输入来源、单位、目标工况有记录 |
| ANSA 几何与表面 | 导入副本，统计 FACE/CONS、开放边、交叉、分组与尺寸；导出候选网格和诊断 | 判断相交/裂缝是否为真实几何，决定 Topo、补洞、重划分和局部网格尺寸；在 ANSA 审查修复副本 | 表面封闭性、交叉、几何尺寸和关键区域分辨率经审核 |
| Pointwise 体网格 | 导入候选，统计单元类型、Jacobian、skew，保存工程与日志；对比导入前后边界面数 | 审查边界层、局部质量、域尺寸；确认每个域属于入口、出口、远场、对称面或壁面 | 无负/零体积，质量异常有处理结论，边界映射逐项确认 |
| OpenFOAM 网格转换 | 只在新目录转换；记录是否缩放一次、包围盒、单元数及各 Patch 面数；运行普通和完整 `checkMesh` | 审查严重 skew、non-orthogonality、低 determinant、凹单元的空间位置和对解的影响；决定修网格或书面接受偏差 | 边界名/类型与面数一致，网格检查达到本项目验收门槛 |
| 工况与求解 | 从已审核参数生成 `0/`、`constant/`、`system/`；语法检查、短时试跑、正式求解、记录残差与力系数 | 提供 Mach/速度、雷诺数或物性、迎角、湍流模型、参考面积/长度、目标精度；审批边界条件和求解预算 | 工况单签字；短时试跑无异常；正式运行另行确认 |
| ParaView 与报告 | 提取真实 U/p 等字段、生成图片/曲线、保存 `.pvsm` 和原始算例；标注时间、变量和单位 | 检查激波/分离/尾流、边界影响、网格独立性、实验或基准对比；给出工程 PASS/FAIL | 图像非空且字段正确，仅工程师可签工程验收 |

平台状态应分别记录：`软件执行成功`、`数值检查通过`、`工程人工通过`。前两项不能自动推出第三项。人工审批要保留审批人、时间、输入 SHA-256、检查项、结论和修复后新运行 ID。

## 当前 CRM_cfx5_mesh.ansa 的实际结论

输入位于 `data/CRM_cfx5_mesh.ansa`，是 **已有体网格的 ANSA 工程**，没有 CAD FACE，不能按球体 IGES 脚本重新划 CAD 表面。只读盘点见 `data/crm_inspect_20261013/inventory.json`：声明单位为 mm；3,722,509 个体单元、1,450,569 个节点、124,962 个表面单元；`far/fuse/inlet/outlet/sym/wing` 六个物理表面组和一个体区；源文件前后 SHA-256 均为 `d90808cd39f127ae3328626523624603dd6b76b1c6ec587fdda9447d9b8b416d`。

已在 `data/crm_trial_20261013/` 建立独立转换副本。ANSA 导出的 Fluent ASCII 网格为 `crm_si.msh`，坐标按 0.001 缩放到米；OpenFOAM `fluentMeshToFoam -scale 1` 成功，所得网格为 3,722,509 单元、六个具名 Patch，外域约 `(-50,0,-50)` 至 `(50,50,50)` m。`pointwise_import.log` 证明 Pointwise 也能读入该体网格且无负/零 Jacobian，但其导入结果只有 `dom-1/dom-2` 两个通用表面域，**不能直接作为保持六组语义的导出源**。

ANSA 导出把六组都写成 `wall`。脚本 `integrations/crm/set_boundary_types.py` 已在独立 OpenFOAM 副本中按**确切名称与面数**把 `far/inlet/outlet` 改为 `patch`，`sym` 改为 `symmetryPlane`，`wing/fuse` 保持 `wall`；原 `boundary` 备份为 `boundary.before_types`，`patchSummary.log` 确认 OpenFOAM 能读取。此脚本只适用于该 CRM 网格签名，不能用于未知模型。

**当前停机点：网格质量。** `checkMesh_default.log` 报 85 个高 skew 面，`Failed 1 mesh checks`。`checkMesh.log` 的完整拓扑与几何检查报 7,850 个低质量或负分解体积的面、156,880 个低 determinant 单元、15 个凹单元，并合计 `Failed 6 mesh checks`。日志进程退出码为 0，但日志结果是 FAIL；不能按退出码标 PASS。因此 CRM 低速试跑、ParaView 真实解场与工程报告均为 **BLOCKED**，尚无 CRM 求解结果。

首次 ANSA 导出脚本被批处理调用了两次：第一次生成 `crm_si.msh` 并显示 `Output Completed`，第二次因拒绝覆盖现有文件把 `ansa_export.json` 写成 error。该网格后来被 OpenFOAM 成功转换；应以 `fluentMeshToFoam.log`、文件内容和 `checkMesh` 为转换证据。脚本现已移除自动 `main()` 调用，后续运行只显式调用一次。2026-10-13 被中断的重复导出 `ansa_export_confirmed.log` 没有完成报告或新网格，不计入验收。

## 下一轮人工任务

1. 在 ANSA/Pointwise 中定位上述坏单元和高 skew 面，检查是否集中在机翼、机身交界或远场；保存修复前后图片与计数。不可直接删除异常单元后继续求解。
2. 确认六组边界的物理含义、对称方向、实际机翼参考尺寸和所需边界层。Pointwise 若继续作为导出节点，须恢复六组边界及逐组面数；也可保留 Pointwise 只读质量审核节点，使用 ANSA → OpenFOAM 转换链路。
3. 修复网格副本并重新跑普通与完整 `checkMesh`。如拟人工接受剩余质量异常，须记录位置、数量、风险和批准人，再创建新的求解任务。
4. 用户已选择**低速接线测试**。网格获准后，由工程师填写速度、物性、迎角、湍流模型、参考量和收敛标准；脚本再生成并试跑工况。低速接线测试不能当作 CRM 标准气动工况验收。

## 可复现检查

在 `F:\Auto\FlowForge-CFD` 中，已有网格与日志位于 `data/crm_trial_20261013/`。读取检查结果：

```powershell
Get-Content data\crm_inspect_20261013\inventory.json
Get-Content data\crm_trial_20261013\pointwise_import.log
Get-Content data\crm_trial_20261013\fluentMeshToFoam.log -Tail 45
Get-Content data\crm_trial_20261013\checkMesh_default.log -Tail 45
Get-Content data\crm_trial_20261013\checkMesh.log -Tail 45
Get-Content data\crm_trial_20261013\boundary_types.json
```

任何后续自动执行器都应先读取这两份 `checkMesh` 日志；只要仍含 `Failed ... mesh checks`，状态必须保持 `BLOCKED`，不得调用求解器。
