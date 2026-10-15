# 非球体恢复演练与表面网格问题处理

日期：2026-10-13（Pacific/Honolulu）。

## 飞机检查点恢复演练

任务 2f7c72f876984d3788f6bf4e5b183c5f：从 v6 已有 ANSA/Pointwise 检查点开始。

- v7 故意导入损坏 .pw；真实 Pointwise 导出失败，NEEDS_MANUAL_REPAIR；没有 solver.log 或报告。
- 由本机 Pointwise 加载原有效工程，修改体块名称并另存；这是模拟人工交回，不是修复真实几何缺陷。
- v8 导入新工程，真实导出和 checkMesh 通过；核对原始 IGES、表面 STL、ANSA 工程哈希一致，没有重跑 ANSA。
- v9 设置高黏度层流连通性测试参数；v10 从时间零运行两个真实时间步，ParaView、真实图片/CSV/PVSM/HTML/ZIP 均已生成。最终 WAITING_FOR_REVIEW，物理验证未通过/未完成。
- trace.json、summary.json 和原生保存日志位于 data/rehearsals/20261014T080813Z/。
- 原 v1 飞机发散证据仍保留。

## 用户实际操作问题

8123 旧后端缺少 surface-mesh POST 路由，导致 Method Not Allowed。已核实进程并重启为当前代码；API 修订标记 workflow-v1-handoff。关闭本轮 8134 临时服务，统一使用 8123。

小飞机 demo_aircraft_test.igs 的表面网格错误来自固定 12 mm 尺寸与至少 1000 单元门槛：实际 42 单元，不是零网格。0.5 mm 得到 760 单元；0.25 mm 得到 1789 ANSA 面单元，3350 STL 三角面，0 退化、0 开放边、0 非流形边，STL 真实检查通过。

任务 6fb79e3f7cf240539300372dda7f1055：v1/v2 失败保留，v3 表面网格通过。
用户最新任务 e81eb9df3fa640979c9927e8e795455f：v1 失败保留，v2 以 0.25 mm 表面网格通过。浏览器显示可继续生成 Pointwise 体网格。

新增 retry-surface API，复制已审核几何到新版本，旧下游输出失效；增加可编辑网格尺寸和中文错误解释。8 项 pytest 通过，前端构建通过。

本轮没有实际重跑小飞机的后续体网格和求解，也没有人工在 GUI 中修复真实几何缺陷；这些不得标记为已验证。
