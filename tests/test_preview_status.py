from backend import app


def test_missing_upload_reports_file_loss_before_preview_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(app, 'rows', lambda *args: [{'path': str(tmp_path/'deleted.igs')}])
    result=app.cad_preview_status('missing')
    assert result['status']=='error'
    assert '原始上传文件不存在' in result['error']
    assert '重新上传' in result['error']
