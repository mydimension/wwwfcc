"""Precompute AM groundwave range at a set of field-strength thresholds,
using the real ITU-R P.368 reference algorithm (GRWAVE) rather than a
hand-fit approximation - the FCC's own AM groundwave method (47 CFR
73.184) is graphical/tabular, not a formula, so there's no "correct"
closed-form equation to implement; GRWAVE is the actual numerical
method the curves themselves are derived from.

This runs at build time (not in the browser - GRWAVE is Fortran, no JS
port exists) using a single assumed "average US land" ground constant
pair, not a real conductivity map - that's the v1 simplification. A
terrain-aware upgrade would swap this for FCC's M3 conductivity map,
computed per station's actual site.

Field strength is exactly proportional to sqrt(power) for fixed
frequency/ground/geometry (linear system), so this computes one
reference curve per distinct AM frequency at a reference power, then
scales per station - avoiding one GRWAVE run per station.
"""
import math

from grwave import grwave

# ITU-R P.368's standard "medium dry ground" reference constants -
# a commonly cited stand-in for "average" US land in the absence of a
# real per-site conductivity value.
GROUND_SIGMA_S_M = 3e-3
GROUND_EPSILON = 15

REFERENCE_POWER_W = 1000.0  # 1 kW reference; scale by sqrt(actual/ref)
RECEIVER_HEIGHT_M = 2.0
TRANSMITTER_HEIGHT_M = 0.0  # groundwave is a surface effect; height barely matters at MF
DMAX_KM = 500
DSTEP_KM = 5

# Thresholds to precompute, in dBu (dB above 1 uV/m) - same unit FM
# uses, so the frontend can expose one unified threshold control.
THRESHOLDS_DBU = list(range(20, 85, 5))


def reference_curve_km_vs_dbu(freq_khz):
    """Run GRWAVE once for this frequency at the reference power.
    Returns sorted list of (distance_km, field_strength_dbu).

    grwave's "fs" column is already field strength in dBu (dB above
    1 uV/m) at the given txwatt - not mV/m as an early draft of this
    module assumed (verified against raw output: e.g. ~42 dBu at 10km
    for 1kW/770kHz over medium-dry ground, decaying smoothly to ~0 dBu
    around 470km - a physically sane curve, whereas treating those
    numbers as mV/m and reconverting produced an inflated, saturated
    curve that never dropped below any realistic threshold).
    """
    df = grwave({
        "freqMHz": freq_khz / 1000.0,
        "sigma": GROUND_SIGMA_S_M,
        "epslon": GROUND_EPSILON,
        "dmax": DMAX_KM,
        "hrr": RECEIVER_HEIGHT_M,
        "htt": TRANSMITTER_HEIGHT_M,
        "dstep": DSTEP_KM,
        "txwatt": REFERENCE_POWER_W,
    })
    points = []
    for dist_km, row in df.iterrows():
        if dist_km > 0:
            points.append((float(dist_km), float(row["fs"])))
    points.sort()
    return points


def range_at_thresholds(reference_points, power_kw):
    """Given the reference curve (at REFERENCE_POWER_W) and this
    station's actual power, return {threshold_dbu: range_km}.

    Field strength scales as sqrt(power), i.e. in dB terms shifts by
    10*log10(power_kw*1000 / REFERENCE_POWER_W). Field strength falls
    monotonically with distance, so range at a threshold is found by
    walking outward until the shifted curve drops below it.
    """
    if power_kw is None or power_kw <= 0 or not reference_points:
        return {}
    shift_db = 10 * math.log10((power_kw * 1000.0) / REFERENCE_POWER_W)

    ranges = {}
    for threshold in THRESHOLDS_DBU:
        # Field strength at the reference power that would, after the
        # shift, equal this threshold:
        target_ref_dbu = threshold - shift_db
        found = None
        prev_d, prev_fs = reference_points[0]
        if prev_fs < target_ref_dbu:
            continue  # doesn't even reach the threshold at d>0
        for d, fs in reference_points[1:]:
            if fs < target_ref_dbu:
                # crossed between prev_d and d - linear interpolate
                frac = (prev_fs - target_ref_dbu) / (prev_fs - fs)
                found = prev_d + frac * (d - prev_d)
                break
            prev_d, prev_fs = d, fs
        if found is not None:
            ranges[threshold] = round(found, 1)
        elif prev_fs >= target_ref_dbu:
            # never dropped below threshold within DMAX_KM
            ranges[threshold] = DMAX_KM
    return ranges
