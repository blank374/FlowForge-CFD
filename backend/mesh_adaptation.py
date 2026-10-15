"""Bounded, model-independent quality feedback for diagnostic meshes."""
import re


def next_spacing_ratio(log, ratio, attempt):
    # Retry only a single skewness failure, never topology, negative-volume,
    # missing-input or environment errors. Keep the original check threshold.
    if attempt >= 2 or not re.search(r'Failed\s+1\s+mesh checks', log):
        return None
    if not re.search(r'\*\*\*Max skewness.*?highly skew faces', log):
        return None
    if any(token in log for token in ('FOAM FATAL', 'negative volume', 'Failed 2 mesh')):
        return None
    value = ratio*2 if attempt == 0 else ratio/4
    return value if 0 < value <= .1 else None
