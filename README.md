# FlowForge-CFD

FlowForge-CFD 是运行在 Windows 本机的 CFD 工作台。页面统一展示文件输入、ANSA 几何检查与表面网格、Pointwise 体网格、OpenFOAM 检查与求解、ParaView 后处理和报告。任务输入按版本保存，运行日志与产物可在页面查看。

**当前能力边界：**20 mm IGES 球体（L1）已有端到端自动运行记录。通用 CAD/ANSA 文件可进入 ANSA 检查和人工修复、复检流程；通用网格、边界条件和物理配置尚无经过验证的自动模板，后续阶段会阻断。CRM 网格目前未通过 OpenFOAM 网格检查。详见[现状概览](docs/status_zh.md)。

## 本地启动

在 PowerShell 中执行：

```powershell
cd F:\Auto\FlowForge-CFD
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
npm --prefix frontend install
npm --prefix frontend run build
pwsh -NoProfile -File .\start.ps1
```

打开 <http://127.0.0.1:8123/>，接口文档位于 <http://127.0.0.1:8123/docs>。`start.ps1` 使用项目的 `.venv` 启动服务。ANSA、Pointwise 的本机路径在 `config.json` 配置；WSL 发行版默认 `Ubuntu-F2`，可用 `FLOWFORGE_WSL_DISTRO` 覆盖。完整 L1 流程依赖相应软件、许可证及允许调用 WSL 的 Windows 环境。

## 使用路径

1. 在页面中选择或创建工程，上传文件。STL/OBJ 和部分 CAD 文件可进行三维预览。
2. 对 20 mm L1 球体，选择已上传的 `.igs`/`.iges` 文件并运行球体流程，也可运行内置球体。其他形状不会通过 L1 专用几何门槛。
3. 对通用 CAD 或 ANSA 工程，运行 ANSA 检查。需要人工处理时，在本机 ANSA 中打开独立工作副本，保存后提交为新版本复检；跨电脑操作可下载、修复再上传。
4. 在任务详情查看阶段状态、日志和产物。`BLOCKED` 表示缺少合格输入或经过验证的后续流程，不表示计算成功。

运行中的旧 L1 任务可在页面取消，也可调用 `POST /api/runs/{id}/cancel`。运行数据位于 `data/`，不会提交到 Git。

## 文档

- [中文现状概览](docs/status_zh.md)：已验证能力、限制和证据入口。
- [统一流程与验收记录](docs/unified_workflow.md)：任务阶段、接口和验收记录。
- [脚本与人工协作流程](docs/human_in_the_loop_cfd.md)：CRM 人工检查与交接。
- [文档索引](docs/README.md)：其余专题记录及阅读顺序。
- [仓库整理建议](docs/repository_cleanup_plan.md)：下一阶段的结构整理清单。

`F:\Auto\automation` 是旧项目，不是本工作台的运行依赖。
