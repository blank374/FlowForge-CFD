# 人机协作工作流实施与验收记录

日期：2026-10-13（Pacific/Honolulu）。分支 codex/product-v1。原有未提交修改继续保留。

## 当前实现

自动化执行 → 检查失败停下 → 原生软件人工修复 → 新版本提交 → 真实复检 → 从检查点继续。

- ANSA：保留原有受控启动、工作副本、保存变化检测、新版本导入和几何复检。
- Pointwise：新增受控启动当前工程副本、提交本机保存副本、上传 .pw。每次导入新版本保留几何及表面网格，不复制旧求解结果。先由 Pointwise 打开并导出，再运行 checkMesh，失败停在人工处理状态。通过后暂停，等待配置/继续求解。
- 求解重试：原输入哈希、常量/网格哈希、参数哈希、父版本记录；复制后再次核对。重新 checkMesh，再从时间零求解。此前日志和产物不覆盖。
- 通用外流场：显式来流速度、黏度、真实壁面和远场映射；当前层流、+X 来流、一个壁面组和一个远场组。拒绝不完整映射，不使用球体边界。
- 通用 ParaView 提取真实内部场和域中心切面，生成 CSV、PVSM、压力/速度 PNG、残差图和独立 HTML 报告。
- Pointwise 自动建域改为按实际包围盒和中心确定尺寸，API 接收远场尺寸比例、近壁间距比例和层数。该脚本修改尚未重新实际运行。

## 实际验证

- pytest tests -q：7 passed。涵盖旧状态、版本证据、ANSA 接管、检查点、不覆盖旧结果、错误边界拒绝、Pointwise 失败阻止继续、报告输入转义和图片完整性。
- 前端 TypeScript + Vite 生产构建通过；包尺寸有警告，尚未拆包。
- 实际浏览器：打开飞机任务、真实 STL 加载、22,210 三角面及包围盒、重试按钮、新版本刷新、待审核状态、真实报告打开。
- Pointwise 打开修复副本 API 与浏览器按钮实际调用成功；未保存直接提交，得到“尚未检测到保存的修改”，没有创建假修复通过记录。
- 球体本机全链路新运行 0a4ef8179af74aca812aee4885dc0d77：真实 ANSA、Pointwise、47,543 体单元、checkMesh、400 步到 0.2 秒、ParaView、HTML 报告和 ZIP 成功。仅作为软件调用链回归证据。
- 飞机工作流 2f7c72f876984d3788f6bf4e5b183c5f：v1 原始发散日志保留。v2 命令传参失败保留。v3 旧配置试算未通过。v4 显式外流场测试配置。v5 暴露日志误判和时间对齐问题，记录保留。v6 修正后以已有 506,417 单元真实网格执行两步高黏度层流测试至 0.000002 秒，生成真实 ParaView/CSV/PNG/PVSM/报告/ZIP；最终 WAITING_FOR_REVIEW，physics_validated=false。
- 飞机 v6 仅为连通性测试，速度 1 m/s、运动黏度 0.001 m²/s，不是空气气动结果，也不是原失败案例变成物理通过。未宣称稳态收敛或力系数。

## NOT_TESTED 与未完成

- 人工在 ANSA/Pointwise 中实际修复缺陷、保存，再完成真实新版本复检的端到端人工操作。
- 修改后的通用 Pointwise 按包围盒自动建域脚本真实运行及多模型鲁棒性。
- 完整浏览器旋转、缩放、平移交互逐项验收。
- 湍流模型、复杂多壁面边界、多单位自动识别、工程精度验证。
- 人工求解结果审核并放行的独立审核 API；目前保留待审核。
- 直接生成 DOCX/PDF；当前报告为可下载、可打印的 HTML。
- 后端多实例同时运行会干扰启动恢复状态；正式使用应只启动一个服务。

## 文件与界面

主要新增 backend/recovery.py、external_setup.py、pointwise_handoff.py、render_external.py、reporting.py；修改 app.py、workflow.py、UnifiedApp.tsx、CadViewer.tsx、style.css、Pointwise 脚本。测试依赖记录在 requirements-dev.txt，测试数据已与正式 data 隔离。

本轮验收服务 http://127.0.0.1:8134/ 。生产启动入口仍为 start.ps1（8123），需重启以加载最新后端代码。

截图：acceptance/generic-aircraft-report.jpg、acceptance/manual-pointwise-handoff.jpg、acceptance/local-chain-report.jpg。
