import pytest
from backend.numerics import limit_nonorthogonal_correction


def test_limits_only_known_correction_and_rejects_unknown_dictionary(tmp_path):
    system = tmp_path/'system';system.mkdir()
    path = system/'fvSchemes'
    path.write_text('laplacianSchemes { default Gauss linear corrected; }\nsnGradSchemes { default corrected; }\ndivSchemes { div(phi,U) Gauss linearUpwind grad(U); }')
    metadata = limit_nonorthogonal_correction(tmp_path)
    assert 'Gauss linear limited corrected 0.33' in path.read_text()
    assert 'div(phi,U) Gauss linearUpwind grad(U)' in path.read_text()
    assert metadata['fvSchemes_sha256']
    assert limit_nonorthogonal_correction(tmp_path)['fvSchemes_sha256'] == metadata['fvSchemes_sha256']
    path.write_text('custom numerical dictionary')
    with pytest.raises(ValueError):
        limit_nonorthogonal_correction(tmp_path)
    assert path.read_text() == 'custom numerical dictionary'
