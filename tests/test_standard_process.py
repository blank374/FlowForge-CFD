import json
from backend.standard_process import assess, convergence


def test_missing_evidence_never_accepts_engineering(tmp_path):
    report = assess(tmp_path)
    assert not report['engineering_ready']
    assert all(c['status'] == 'MISSING' for c in report['checks'])
    (tmp_path / 'external_setup.json').write_text(json.dumps({'settings': {'speed_m_s': 1}}))
    assert assess(tmp_path)['checks'][2]['status'] == 'FAILED'


def test_real_iteration_convergence_and_invalid_samples(tmp_path):
    assert not convergence([0.5] * 49)['passed']
    assert convergence([0.5] * 50)['passed']
    assert not convergence([0.5] * 25 + [0.6] * 25)['passed']
    assert not convergence([float('nan')] * 50)['passed']
    path = tmp_path / 'force_coefficients.csv'
    path.write_text('iteration,CL,CD,Cm\n' + '\n'.join(f'{i},0.5,0.02,-0.1' for i in range(50)))
    report = assess(tmp_path)
    assert report['checks'][3]['status'] == 'PASSED'
    assert not report['engineering_ready']
    path.write_text('iteration,CL,CD,Cm\n' + '\n'.join('1,0.5,0.02,-0.1' for _ in range(50)))
    assert assess(tmp_path)['checks'][3]['status'] == 'FAILED'
