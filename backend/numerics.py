"""Conservative nonorthogonal correction for low-speed diagnostic cases."""
import hashlib


def limit_nonorthogonal_correction(case):
    path = case / 'system/fvSchemes'
    original = path.read_text(encoding='utf-8')
    limited = original.replace('Gauss linear corrected', 'Gauss linear limited corrected 0.33')
    limited = limited.replace('default corrected;', 'default limited corrected 0.33;')
    if 'Gauss linear limited corrected 0.33' not in limited or 'default limited corrected 0.33;' not in limited:
        raise ValueError('当前数值字典不匹配已测试的层流诊断模板，请人工审核，未修改字典')
    path.write_text(limited, encoding='utf-8')
    return {'profile': 'laminar_external_limited_nonorthogonal_v1',
            'correction_limit': 0.33,
            'fvSchemes_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'scope': '短时诊断配置，不代表网格质量合格或气动精度验证'}
