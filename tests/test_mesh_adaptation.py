from backend.mesh_adaptation import next_spacing_ratio


def test_single_skew_failure_can_retry_but_is_bounded():
    log='***Max skewness = 4.85, 18 highly skew faces detected\nFailed 1 mesh checks.'
    assert next_spacing_ratio(log,.001,0)==.002
    assert next_spacing_ratio(log,.002,1)==.0005
    assert next_spacing_ratio(log,.0005,2) is None


def test_environment_topology_and_multiple_failures_never_auto_retry():
    for log in ('Wsl/Service/E_ACCESSDENIED','FOAM FATAL IO ERROR',
                'Failed 1 mesh checks. Boundary topology failure',
                '***Max skewness = 8, 20 highly skew faces\nFailed 2 mesh checks.'):
        assert next_spacing_ratio(log,.001,0) is None
