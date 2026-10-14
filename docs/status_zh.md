# 项目现状概览（2026-10-14）

本文汇总仓库已有的验收记录。记录中的 `PASS` 指特定输入和环境下通过，不等于任意外形的工程验证。

| 范围 | 现状 | 证据入口 |
|---|---|---|
| 20 mm L1 IGES 球体 | 已记录 ANSA → Pointwise → OpenFOAM Foundation 13 → ParaView 数据提取 → 报告的完整运行 | [统一流程验收](unified_workflow.md)、[L1 原始验收](implementation_status.md) |
| 通用 CAD/ANSA 文件 | 可上传、版本化、ANSA 检查、人工修复并复检；后续通用网格和求解流程仍阻断 | [统一流程验收](unified_workflow.md)、[人工协作流程](human_in_the_loop_cfd.md) |
| ANSA 几何检查 | 已有只读检查和专项 Topo 测试；开放边用途及外形语义仍需人工判断 | [几何门槛测试](geometry_gate_20261014.md) |
| CRM-WB 原始几何 | 存在开放边/相交等问题，尚未得到可接受的修复几何 | [CRM-WB 原始诊断](crm_wb_geometry_status.md) |
| CRM CFX5 网格 | Pointwise 与 ANSA 可以导入，但既有 OpenFOAM 网格检查未通过，未进行可靠求解 | [CFX5 网格评估](cfx5_mesh_assessment.md)、[人工协作流程](human_in_the_loop_cfd.md) |

## 使用上的关键区别

- L1 球体使用专用几何门槛和物理模板，不能把它的边界条件、网格参数直接用于其他外形。
- 页面预览、文件成功导入或 ANSA 工程保存成功，都不能单独证明体网格和 CFD 结果合格。
- 通用任务的人工审核是几何交接步骤；缺少后续适配器时，`BLOCKED` 是预期状态。
- L1 现有验证属于软件集成与数值测试。网格无关性、远场尺寸研究和实验对比仍未完成，不能作为生产工程精度结论。

## 证据与复现

仓库 `data/` 保存本机运行记录并被 Git 忽略。历史验收文档列有具体任务 ID、日志、图像及复现命令；换机器后，这些本机产物未必存在。先按[首页](../README.md)启动，再查[统一流程与验收记录](unified_workflow.md)的接口及当前运行结果。
