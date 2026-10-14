import base64
import pytest
from backend.reporting import write_report

def test_report_requires_real_images_and_escapes_input(tmp_path):
    data={'input_model':'<script>bad</script>','cells':100,'physics':{'solver':'OpenFOAM 13'}}
    with pytest.raises(RuntimeError):write_report(tmp_path,data)
    for name in ['p.png','U.png','residuals.png']:(tmp_path/name).write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a8nUAAAAASUVORK5CYII='))
    write_report(tmp_path,data)
    content=(tmp_path/'report.html').read_text(encoding='utf-8')
    assert '<script>bad' not in content and '&lt;script&gt;' in content
    assert content.count('data:image/png;base64,')==3
