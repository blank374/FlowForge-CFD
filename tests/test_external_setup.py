from pathlib import Path
import pytest
from fastapi import HTTPException
from backend.external_setup import ExternalSetup,configure_case

def test_external_setup_maps_actual_boundaries(tmp_path):
    case=tmp_path;mesh=case/'constant/polyMesh';mesh.mkdir(parents=True)
    (mesh/'boundary').write_text('CAR_BODY { type wall; nFaces 10; } OUTER { type patch; nFaces 20; }')
    setup=ExternalSetup(speed_m_s=12,nu_m2_s=1.5e-5,wall_patch='CAR_BODY',farfield_patch='OUTER',laminar_confirmed=True,units_confirmed=True)
    configure_case(case,setup)
    assert '12.0 0 0' in (case/'0/U').read_text()
    assert 'CAR_BODY' in (case/'0/p').read_text() and 'L1_' not in (case/'0/p').read_text()
    with pytest.raises(HTTPException):configure_case(case,setup.model_copy(update={'wall_patch':'WRONG'}))
    with pytest.raises(HTTPException):configure_case(case,setup.model_copy(update={'laminar_confirmed':False}))
