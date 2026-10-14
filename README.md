# FlowForge-CFD

FlowForge-CFD 是运行在 Windows 本机的 CFD 工作台。页面统一展示文件输入、ANSA 几何检查与表面网格、Pointwise 体网格、OpenFOAM 检查与求解、ParaView 后处理和报告。任务输入按版本保存，运行日志与产物可在页面查看。

**当前能力边界：**20 mm IGES 球体（L1）已有端到端自动运行记录。通用飞机测试模型已实际完成 ANSA 表面网格、Pointwise 体网格和 OpenFOAM `checkMesh`。首次低速求解出现数值发散，因此飞机的求解、ParaView 和报告未通过。页面依据真实文件显示阶段状态、质量指标、网格预览和可下载的日志；几何修复可保存为新版本并复检。详见[飞机运行记录](docs/generic_aircraft_run_20261014.md)。

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
4. 几何审核通过后，可从任务详情启动 ANSA 表面网格；表面网格通过后，可继续 Pointwise 体网格与 OpenFOAM 网格检查。任务详情可预览真实 STL、查看质量指标及下载当前或历史版本的文件。`FAILED` 表示有真实失败日志；`BLOCKED` 表示后续阶段尚未通过，均不表示计算成功。

运行中的旧 L1 任务可在页面取消，也可调用 `POST /api/runs/{id}/cancel`。运行数据位于 `data/`，不会提交到 Git。

## 文档

- [中文现状概览](docs/status_zh.md)：已验证能力、限制和证据入口。
- [统一流程与验收记录](docs/unified_workflow.md)：任务阶段、接口和验收记录。
- [脚本与人工协作流程](docs/human_in_the_loop_cfd.md)：CRM 人工检查与交接。
- [文档索引](docs/README.md)：其余专题记录及阅读顺序。
- [仓库整理建议](docs/repository_cleanup_plan.md)：下一阶段的结构整理清单。

`F:\Auto\automation` 是旧项目，不是本工作台的运行依赖。
