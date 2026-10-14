# 统一流程与验收记录（2026-10-14）

## 入口与边界

前端 `UnifiedApp.tsx` 是唯一主页面：选工程 → 上传文件 → 选择流程 → 查看一条阶段链 → 下载原生文件与报告。任务都由 `/api/workflows` 管理，文件按版本保存；旧 L1 运行记录和数据未删除。

| 流程 | 当前执行能力 | 人工接管 |
|---|---|---|
| L1 20 mm IGES 球体 | 真正调用 ANSA、Pointwise、OpenFOAM Foundation 13、ParaView；到 `report.md` | 失败后保留旧尝试，上传新 IGES 启动新版本；完整阶段内断点续算尚未实现 |
| 通用 CAD / ANSA 工程 | 真正调用 ANSA 只读导入、拓扑与相交检查 | 可直接人工处理或自动检查后转人工；ANSA GUI 修复、回传新版本、自动复检；通用表面/体网格与物理配置没有验证模板时阻断 |

本机人工处理现在可点“在本机 ANSA 打开工作副本”。服务在任务版本目录生成独立副本，直接启动 ANSA GUI 打开；保存到页面显示的路径后，点“提交本机修复并复检”，系统从该副本创建新版本并执行原有复检。原始上传和检查工程不会被修改。另存到别处或跨电脑操作时仍可选择文件上传。L1 流程仅接受导出的 IGES 球体，不能用 ANSA 原生工程直接重跑完整链。

所有任务展示八个阶段：文件输入、ANSA 几何检查、ANSA 表面网格、Pointwise 体网格、OpenFOAM 网格检查、OpenFOAM 求解、ParaView 后处理、报告。通用流程中未实现的阶段显示 `BLOCKED`；不会仅凭按钮或文件后缀放行。

## 主要接口

- `POST /api/workflows/projects/{project_id}?file_id=...&profile=l1_full`：启动已验证 L1 全链；`profile=general` 启动 ANSA 检查，另可设 `manual=true` 直接人工处理。
- `GET /api/workflows/projects/{project_id}`、`GET /api/workflows/{job_id}`：读取统一任务状态、阶段、版本、日志与结果。
- `POST /api/workflows/{job_id}/manual`：将已检查的通用几何交给人工。
- `POST /api/workflows/{job_id}/repair`：回传新版本；通用几何重跑 ANSA 检查，L1 球体保留旧运行并启动新一轮全链。
- `POST /api/workflows/{job_id}/open-in-ansa`：在本机 ANSA GUI 打开该任务的独立工作副本。
- `POST /api/workflows/{job_id}/submit-local-repair`：检查工作副本已保存修改，再提交为新版本复检。
- `POST /api/workflows/{job_id}/approve?reviewer=...`：只在 ANSA 检查真正通过且当前文件哈希一致时记录人工确认。
- `GET /api/files/{file_id}/inspect`：识别文件类型、大小、哈希；不宣称候选网格已具备合格体网格。

## 真实验证

| 检查 | 结果 | 证据 |
|---|---|---|
| 前端生产构建 | PASS | `npm run build` 完成，生成 `frontend/dist/`；TypeScript 无错误。 |
| 统一 L1 从上传文件到报告 | PASS | 任务 `3996548c2880427cace66222d2053185`，关联运行 `ee08831e485d4bddbb1ba2335c0a2eb8`；75,415 单元、400 步、最终 0.2 s；`result.json`、`solver.log`、`U.png`、`p.png`、`report.md` 均存在。 |
| CRM 人工关口 | PASS（阻断） | 任务 `784d3a25d51d488d9a642fb27ab62bc2` 为 `NEEDS_MANUAL_REPAIR`；ANSA 报 76 条自由 CONS、1 处相交；下游阶段 `BLOCKED`。 |
| 服务与页面 HTTP | PASS | `http://127.0.0.1:8123/api/health` 为 `ok`；首页 HTTP 200、返回新构建资源。 |
| 失败 → 人工回传 → 新版本到报告 | PASS | 任务 `4cd06b00745e4f2a990b00d982adf0f8`：v1 的无效 IGES 在 ANSA 导入失败，状态 `NEEDS_MANUAL_REPAIR`，后续 7 阶段阻断；上传真实 `test_sphere_20mm.igs` 为 v2 后，新运行 `2a802fb7bb724a0b95ef6127e4896cd6` 八阶段通过，报告与 U/p 图片存在。v1 状态和文件保留。此测试仍只验证 L1 球体模板。 |
| 失败详情回归 | PASS | 无效 IGES 使旧 `run_summary.json.geometry` 为 `null`，此前详情 API 返回 500；现返回阻断状态。`python -m unittest discover -s tests -v` 通过。 |
| 本机 ANSA 人工接管 | PASS | 对 CRM 人工任务调用直开接口，返回独立 `manual_edit.ansa` 路径；本机 ANSA 通过系统文件关联的 `-i` 参数启动。未保存修改时提交接口返回 409；隔离测试验证保存后提交创建 v2，并保留 v1 输入。 |

## 还不能声称完成的范围

通用 CAD 经人工修复后，尚无经过验证的 ANSA 表面网格模板、Pointwise 边界映射和物理模型，因此不能自动走到 CRM 求解与报告。L1 失败后的新版本会重跑整条已验证链，还不是从失败阶段精确续算。实际工程需补齐这些适配器与质量门槛；不能把 L1 的球体物理设置套给其他外形。
