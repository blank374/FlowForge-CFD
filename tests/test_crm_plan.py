import math
import pytest
from pydantic import ValidationError
from backend.crm_plan import CRMPlan


def test_crm_units_and_reynolds_consistency():
    plan = CRMPlan(reference_chord_m=7.00532, reference_area_m2=100, halfspan_m=29.3814)
    result = plan.preview()
    p = result['physics']
    assert math.isclose(p['density_kg_m3']*p['speed_m_s']*7.00532/p['dynamic_viscosity_pa_s'], 5e6)
    assert result['mesh']['first_layer_mm'] == 0.01
    assert result['mesh']['farfield_distance_m'] > 100*29.3814
    assert result['status'] == 'PLANNED_NOT_EXECUTED'


@pytest.mark.parametrize('invalid', [{'growth_rate':1.2}, {'farfield_halfspan_ratio':100},
                                     {'mach':float('nan')}, {'reference_area_m2':0}])
def test_invalid_standard_plan_rejected(invalid):
    inputs = dict(reference_chord_m=7, reference_area_m2=100, halfspan_m=29)
    inputs.update(invalid)
    with pytest.raises(ValidationError):
        CRMPlan(**inputs)
