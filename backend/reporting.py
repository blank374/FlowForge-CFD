"""Portable printable report made exclusively from validated run artifacts."""
import base64
import html
import json

def write_report(directory, result):
    esc=lambda value:html.escape(str(value))
    figures=[]
    for name,label in [('p.png','压力分布'),('U.png','速度分布'),('residuals.png','残差历史')]:
        path=directory/name
        if not path.is_file(): raise RuntimeError('报告所需真实图片缺失：'+name)
        encoded=base64.b64encode(path.read_bytes()).decode('ascii')
        figures.append(f'<figure><h2>{label}</h2><img alt="{label}" src="data:image/png;base64,{encoded}"></figure>')
    rows=''.join(f'<tr><th>{esc(k)}</th><td>{esc(v)}</td></tr>' for k,v in result['physics'].items())
    document=f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>{esc(result.get('title','L1 球体 CFD 计算报告'))}</title>
<style>body{{font:15px/1.6 system-ui,sans-serif;color:#203045;max-width:960px;margin:40px auto;padding:24px}}h1,h2{{color:#154e63}}table{{border-collapse:collapse;width:100%}}td,th{{text-align:left;border:1px solid #ccd5df;padding:8px}}img{{max-width:100%}}figure{{margin:24px 0;break-inside:avoid}}pre{{white-space:pre-wrap;overflow-wrap:anywhere}}@media print{{body{{margin:0}}button{{display:none}}}}</style>
<h1>{esc(result.get('title','L1 球体 CFD 计算报告'))}</h1><p>ANSA → Pointwise → OpenFOAM Foundation 13 → ParaView → 报告</p>
<p>{esc(result.get('scope','本报告记录 20 mm 球体的瞬态测试计算，已完成规定时间段与数值检查。它不代表稳态收敛或任意 CAD 的工程精度验证。'))}</p>
<h2>模型与网格</h2><p>模型：{esc(result['input_model'])}。体单元：{esc(result['cells'])}。网格单位：m。</p>
<h2>物理设置</h2><table>{rows}</table>
<h2>数值检查</h2><p>{esc(result.get('numerical_criteria','未完成'))}</p><p>末时刻：{esc(result.get('final_time_s'))} s；步数：{esc(result.get('steps'))}；末十步最大压力残差：{esc(result.get('max_last_10_p_residual','未提取'))}。</p>
<p>速度异常值警告：{esc(result.get('velocity_outlier_warning'))}。请结合网格、边界与时间尺度检查适用性。未实际计算的力系数不在报告中展示。</p>
{''.join(figures)}<h2>真实数据与追溯</h2><p>运行编号：{esc(directory.name)}。原始记录与工程请从工作台下载 solver.log、checkMesh.log、配置与检查点记录及 openfoam_case.zip。</p><pre>{esc(json.dumps(result,ensure_ascii=False,indent=2))}</pre></html>'''
    (directory/'report.html').write_text(document,encoding='utf-8')
