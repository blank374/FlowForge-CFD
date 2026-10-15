# 自动 Word 仿真报告

计算完成后生成 report.docx，与 HTML 报告并列提供下载。通用外流场与 L1 报告调用 backend.word_report，使用 python-docx，依赖列于 requirements.txt。求解失败时输出明确标记状态的过程记录；缺失图像不伪造。生成错误写入 word_report_error.log 并反映到任务错误信息。

报告依据用户提供的标准过程定义1-WB-20250103结果对比组织八章：几何、网格、前处理工况、求解与收敛、后处理、残差和实验对比、定量考核、要求覆盖和结论。已有证据自动填写，CL/CD/Cm、Cp、流线、DPW 对比、网格敏感性及人工审核等缺项明确标记未完成，不以软件链路完成替代标准工况或工程精度通过。

通用任务详情中有“下载 Word 标准过程与仿真报告”，文件也出现在当前和历史版本产物中；L1 在报告下载列表中提供 report.docx。新配置及重试不复制旧版本 Word 报告。

标准中的增长率、远场换算、后缘数量及攻角口径存在歧义，报告保留待确认提示。CFX CCL/DEF/RES 与 OpenFOAM 字典和结果字段按实际软件区分，不虚构原生文件。

结构样张位于 deliverables/standard_report_preview/report.docx，不关联实际运行数据。已使用本机 Word 隐藏导出 PDF 并逐页检查；默认 LibreOffice 渲染器不可用。测试覆盖 Word 结构、真实图片嵌入、缺失证据、产物下载和重试清除旧报告。
