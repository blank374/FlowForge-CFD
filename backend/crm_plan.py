"""Validated engineering inputs, distinct from an executable/accepted case."""
import math
from pydantic import BaseModel, Field


class CRMPlan(BaseModel):
    reference_chord_m: float = Field(gt=0, allow_inf_nan=False)
    reference_area_m2: float = Field(gt=0, allow_inf_nan=False)
    halfspan_m: float = Field(gt=0, allow_inf_nan=False)
    alpha_deg: float = Field(default=0, ge=-2.8151, le=10.19, allow_inf_nan=False)
    mach: float = Field(default=0.85, gt=0, le=1.2, allow_inf_nan=False)
    reynolds: float = Field(default=5e6, gt=0, allow_inf_nan=False)
    static_temperature_k: float = Field(default=271.73, gt=0, allow_inf_nan=False)
    static_pressure_pa: float = Field(default=125446.22, gt=0, allow_inf_nan=False)
    growth_rate: float = Field(default=1.19, gt=1, lt=1.2, allow_inf_nan=False)
    farfield_halfspan_ratio: float = Field(default=101, gt=100, allow_inf_nan=False)
    maximum_layers: int = Field(default=100, ge=1, le=100)

    def preview(self):
        gas_constant = 287.05
        speed = self.mach * math.sqrt(1.4 * gas_constant * self.static_temperature_k)
        density = self.static_pressure_pa / (gas_constant * self.static_temperature_k)
        alpha = math.radians(self.alpha_deg)
        return {
            'status': 'PLANNED_NOT_EXECUTED', 'inputs': self.model_dump(),
            'physics': {'solver': 'OpenFOAM Foundation 13 fluid', 'turbulence': 'kOmegaSST',
                        'speed_m_s': speed, 'velocity_m_s': [speed*math.cos(alpha), 0, speed*math.sin(alpha)],
                        'density_kg_m3': density,
                        'dynamic_viscosity_pa_s': density*speed*self.reference_chord_m/self.reynolds},
            'mesh': {'working_units': 'mm', 'solver_units': 'm', 'first_layer_mm': 0.01,
                     'growth_rate': self.growth_rate, 'maximum_layers': self.maximum_layers,
                     'farfield_distance_m': self.halfspan_m*self.farfield_halfspan_ratio,
                     'root_tip_spacing_max_mm_exclusive': 0.001*self.halfspan_m*1000,
                     'leading_trailing_edge_spacing': '<0.001 times local chord'},
            'required_before_execution': ['设计外形审核', 'wing/body 分组与对称面',
                '局部弦长分布', '网格质量及首层实测', '湍流入口参数及壁面处理审核'],
            'notes': ['黏度按指定 Re、参考弦长和静态来流计算；不是测量值。',
                      '采用理想气体空气 R=287.05，gamma=1.4；总温总压一致性需审核。'],
        }
