# 翼身测试模型的短时稳定性诊断

最新任务 e344b177d9ca4be4afce2b90909a456e 使用 12 mm 表面网格，513242 个体单元。v5 在速度 1 m/s、运动黏度 1.5e-5 m²/s、初始步长 1e-6 s、终止时间 1e-5 s 时出现时间步持续缩小，约在模拟时间 6e-6 s 停滞。已终止并保留日志。

网格普通 checkMesh 为 Mesh OK，但有 2016 个面非正交角大于 70°，最大约 88.326°。原始 fvSchemes 使用无限制 corrected 非正交修正。

## 对照

在 data/stability_diagnostic_limited/case 中保持网格、边界、初值、速度、黏度及求解器设置不变，仅将 laplacianSchemes 与 snGradSchemes 的非正交修正改为 limited corrected 0.33。7 步完成 1e-5 s，最大 Courant 数 0.1645436，未发生时间步崩缩。对照只支持该设置是本次短时失稳的重要影响因素，不能确定唯一根因，也不代表坏网格已经修好。

## 工作台复现

v6 使用同样调整，完整执行 checkMesh、foamRun、ParaView 数据提取、图像生成与报告输出。求解约 84 秒墙钟时间，正常 End，末时刻 U 和 p 存在，最大 Courant 数 0.1645436。独立读取全部 513242 个内部速度向量均为有限值，最大速度 2.7706725 m/s，平均速度 1.0042186 m/s。这些仅为诊断观察值，不构成速度场精度验收。

最终任务状态 WAITING_FOR_REVIEW，物理验证保持 false。报告和原始日志位于 data/workflows/e344b177d9ca4be4afce2b90909a456e/v6/。17 项回归测试通过。

## 软件变更与限制

backend/numerics.py 只为已接入的外流场层流重试应用受限修正；未知数值字典拒绝自动改写，历史版本不变。checkpoint.json 记录 profile、修正系数和 fvSchemes 哈希。当前服务已加载该修改。

这是一段 1e-5 秒的瞬态诊断，不是稳态收敛验证。延长时间后可能再次失稳；后续应修复高非正交网格、进行残差及气动力收敛分析，并实现可压缩湍流标准工况。不能直接拿本报告与 CRM/DPW 试验比较。
