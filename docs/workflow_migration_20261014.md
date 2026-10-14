# 半自动工作流改造记录（2026-10-14）

## 审计与最小改动方案

- `backend/app.py` 的 SQLite 只有项目、文件、整次运行三张表；L1、cavity 和验证任务由一个后台线程执行，取消功能已有。它不记录独立阶段或人工版本。
- `integrations/l1` 的 ANSA、Pointwise、OpenFOAM 与 ParaView 链路是球体专用，必须保留；通用 CAD 不应走它的球体门槛。
- React 页面已有上传、预览、运行日志、结果下载；原工作流图仅是静态提示。
- CRM 诊断和 CFX5 转换已有独立试验及日志，但尚未成为通用 API。CFX5 网格的 `checkMesh` 仍失败，不能进入求解。

因此先在原 FastAPI/SQLite/React 中增加版本化 ANSA 几何关口，不改 L1 执行代码，不迁移旧运行数据。下一步再将表面网格、Pointwise、OpenFOAM 接到相同的阶段状态模型。

## 本阶段实现

- `POST /api/workflows/projects/{project_id}?file_id=...`：对已上传的 CAD/ANSA 文件建立不可变版本，复制后调用真实 ANSA 检查。
- 同一接口增加 `manual=true`：直接进入人工 ANSA 处理，不运行自动几何修改。`POST /api/workflows/{job_id}/manual` 可在检查结束后主动转人工。
- `GET /api/workflows/projects/{project_id}`、`GET /api/workflows/{job_id}`：列出任务、阶段和每个版本的检查报告。
- `GET /api/workflows/{job_id}/versions/{version}/file`、`/review-project`、`/log`：下载输入、ANSA 检查工程和日志。网页提供下载后在本地 ANSA GUI 打开的路径，没有伪造浏览器直接启动功能。
- `POST /api/workflows/{job_id}/repair`：回传修复后的 CAD/ANSA 工程，建立新版本，自动重新调用 ANSA；旧版本不覆盖。
- `POST /api/workflows/{job_id}/approve?reviewer=...`：仅真实检查报告通过且输入哈希未改变时，可登记人工审核。通用 Pointwise 接口未接入前，后续阶段仍为 `BLOCKED`。
- `GET /api/files/{file_id}/inspect`：读取文件头、大小和 SHA-256，区分 CAD 与工程/网格候选；不会仅凭后缀宣称网格完整。CFX5 不在本轮产品范围。
- 原有 L1 任务详情从 `run_summary.json`、`checkMesh.log`、`solver.log`、ParaView 文件和报告读取 ANSA → Pointwise → OpenFOAM → ParaView → 报告的阶段状态。前端展示这些真实阶段与证据链接；没有运行产物的阶段不会显示为通过。

本阶段的几何门槛保守：**不自动 Topo、粘合或修复**；只读取 FACE、CONS、自由 CONS、相交区域并保存独立 ANSA 检查工程。需要 FACE、CONS、零自由 CONS、零相交区域及成功保存检查工程。法线、表面网格、设计外形和边界语义尚未纳入此门槛，所以即使自动检查通过也必须人工审核；审核后仍不能自动进入求解。`.ansa` 工程现可作为工程文件上传；网页不提供其 3D 预览，下载后在 ANSA GUI 中查看。

## 真实验证

| 测试 | 状态 | 证据与结论 |
|---|---|---|
| CRM-WB 原始 IGS | PASS（阻断机制） | `data/workflows/136c3d134e034a8d909ba79eef520913/v1/`：ANSA 在独立副本上 Topo 后仍有 16 条自由 CONS、1 处相交；状态 `NEEDS_MANUAL_REPAIR`。原始输入哈希未变。 |
| ANSA 修复文件回传与复检 | PASS（拒绝机制） | 同一任务 `v2/` 回传现有 `crm_wb_prepared.ansa` 候选；真实 ANSA 复检仍未通过，保持 `NEEDS_MANUAL_REPAIR`，没有进入 Pointwise。此文件不是已修复合格的几何。 |
| 未通过的复检不能人工批准 | PASS | 调用审核端点返回 HTTP 409：`ANSA geometry verification has not passed`。 |
| L1 原有全链回归 | PASS | `data/runs/694e7ad1ccd448c0b86d50879b4bc345/`：真实 ANSA → Pointwise → OpenFOAM → ParaView 数据提取；74,934 单元，400 步至 0.2 s，求解日志正常 `End`，压力残差与连续性门槛通过，结果及 U/p 图保留。首次受限运行 `48f659669f8146fda97bb31cc6f7b2f7` 在 WSL 访问被沙箱拒绝，使用允许访问 WSL 的环境重跑成功。 |
| L1 球体在新通用几何门槛 | BLOCKED | `data/workflows/69eab585a4464d72b2f3a81b5cbe7927/v1/`：Topo 后有 1 条自由 CONS。新通用门槛暂不适用于这个球体；原 L1 专用链未改动。 |
| Pointwise 人工接管 | NOT_TESTED | 此阶段 API 尚未实现。 |
| OpenFOAM 人工配置与求解 | NOT_TESTED | 此阶段 API 尚未实现；历史 L1 真求解证据见 `docs/implementation_status.md`。 |
| CFX5 已有网格入口 | BLOCKED | `docs/cfx5_mesh_assessment.md` 和 `docs/human_in_the_loop_cfd.md` 记录了真实 ANSA 导入与 OpenFOAM 转换，但现有网格 `checkMesh` 失败。 |
| 上游版本失效 | PASS（ANSA 范围） | 修复文件成为 v2；审批只检查当前版本报告和哈希，旧 v1 报告不能批准 v2。跨 Pointwise/求解的失效链待后续阶段接入。 |
| 人工按钮与只读自动检查 | PASS | `data/workflows/b25ad9c6eb1f4c15ba696de9b162afd6/v1/`：`manual=true` 直接进入 `NEEDS_MANUAL_REPAIR`，没有启动 ANSA 检查。`data/workflows/784d3a25d51d488d9a642fb27ab62bc2/v1/`：自动模式只读检查原始 CRM，76 条自由 CONS、1 处相交，报告无 `topo_return`。 |
| 人工回传后的只读复检 | PASS（拒绝机制） | 人工任务 `b25ad9c6eb1f4c15ba696de9b162afd6/v2/` 回传现有候选工程；ANSA 复检发现 16 条自由 CONS，仍为 `NEEDS_MANUAL_REPAIR`。 |
| L1 阶段显示 | PASS | 读取既有成功任务 `27e63b6565344386934a7540267a3492`，六个阶段均有真实通过证据；读取失败任务 `1c41dd4534494b99bd53310453ad4a9d`，后续阶段均显示阻断。 |
| 文件识别 | PASS | 上传的 CRM-WB IGS 被识别为 CAD / IGES 候选，流式 SHA-256 为 `e2b7ed29bc632e99ef95da87525f81f9943315a0c1e380cacf932737b6329a21`；`volume_mesh_verified=false`。 |

## 未完成事项

1. 实现 ANSA 表面网格质量门槛；根据几何类别配置允许的开放边，不能用单一零自由 CONS 规则处理所有外流模型。
2. 让 Pointwise 阶段接受并复检真实人工工程，记录边界映射和体网格质量。
3. 为已有体网格增加类型识别、经验证的转换路径及 `checkMesh` 门槛。
4. 加入物理配置人工确认、求解断点、ParaView 审核与最终报告。
5. 补齐每阶段软件版本及操作人身份认证。当前审核人是用户填写的姓名，尚无登录认证。
6. 将目前独立的 L1 全链与通用 ANSA 人工任务合成一个可继续的任务对象；当前通用路径在 Pointwise 前阻断，尚未实现复杂模型从人工修复继续至报告。
