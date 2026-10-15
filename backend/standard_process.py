"""Evidence-based CRM-WB acceptance; missing evidence never means passed."""
import csv
import json
import math
from pathlib import Path

STANDARD = {
    'name': 'CRM-WB 标准过程',
    'model': 'DPW4_wb_no_tail_v03.igs',
    'mach': 0.85, 'reynolds': 5e6,
    'first_layer_mm': 0.01, 'growth_rate_max_exclusive': 1.2,
    'farfield_halfspan_ratio_min_exclusive': 100,
    'cl_window_short': 25, 'cl_window_long': 50, 'cl_tolerance': 0.0001,
    'clarifications': [
        '增长率按较严格的 <1.2 验收；原文同时出现 1.2，待标准负责人确认。',
        '远场按 >100 半展长验收；原文长度换算不一致，不采用其中的绝对长度。',
        '后缘网格数量原文为 >>8，精确验收阈值待确认。',
    ],
}


def convergence(values):
    """Use actual iterations, not time-step count or synthetic coefficients."""
    if len(values) < 50:
        return {'passed': False, 'samples': len(values), 'reason': '至少需要 50 个有效迭代样本'}
    if not all(math.isfinite(v) for v in values):
        return {'passed': False, 'samples': len(values), 'reason': '力系数含非有限值'}
    short = sum(values[-25:]) / 25
    long = sum(values[-50:]) / 50
    delta = abs(short - long)
    return {'passed': delta < 0.0001, 'samples': len(values),
            'CL25': short, 'CL50': long, 'difference': delta, 'tolerance': 0.0001}


def assess(directory):
    directory = Path(directory)
    checks = []

    def record(key, label, status, actual, required):
        checks.append(dict(key=key, label=label, status=status, actual=actual, required=required))

    def read(name):
        path = directory / name
        try:
            return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
        except (ValueError, OSError):
            return {}

    geometry = read('geometry_report.json')
    # Existing generic topology reports cannot establish intended CRM shape.
    record('geometry', '指定 CRM-WB 外形与单位', 'MISSING', geometry.get('unit'),
           '指定模型；毫米工作几何；外形、wing/body 和对称面审核')
    record('mesh', '标准网格参数与实测质量', 'MISSING', None,
           '首层 0.01 mm；增长率 <1.2；远场 >100 半展长；局部加密、体积比与对称面实测')
    setup = read('external_setup.json')
    record('physics', '标准可压缩湍流工况', 'FAILED' if setup else 'MISSING',
           setup.get('settings'), 'M=0.85；Re=5e6；攻角、温压、参考面积及参考弦长明确')
    path = directory / 'force_coefficients.csv'
    coeff = None
    if path.is_file():
        try:
            with path.open(encoding='utf-8-sig', newline='') as stream:
                rows = list(csv.DictReader(stream))
            iterations = [float(r['iteration']) for r in rows]
            cl = [float(r['CL']) for r in rows]
            valid = all(math.isfinite(float(r[k])) for r in rows for k in ('iteration', 'CL', 'CD', 'Cm'))
            valid = valid and all(b > a for a, b in zip(iterations, iterations[1:]))
            coeff = convergence(cl) if valid else {'passed': False, 'reason': '迭代编号或力系数无效'}
        except (ValueError, KeyError, TypeError, OSError):
            coeff = {'passed': False, 'reason': '力系数 CSV 格式无效'}
    record('convergence', 'CL CD Cm 监控与 CL 收敛',
           ('PASSED' if coeff['passed'] else 'FAILED') if coeff else 'MISSING', coeff,
           '真实迭代序列；|CL25−CL50| <0.0001；残差另行审核')
    record('validation', 'DPW 试验与网格敏感性验证', 'MISSING', None,
           '同工况气动力、剖面 Cp、实验误差和网格敏感性检查')
    return {'standard': STANDARD, 'status': 'NOT_VALIDATED', 'engineering_ready': False,
            'checks': checks, 'scope': '标准验收清单；程序结束和通用网格检查不能代替工程验证'}
