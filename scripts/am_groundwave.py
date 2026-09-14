"""Precompute AM groundwave range at a set of field-strength thresholds,
using FCC's own published groundwave curves (47 CFR 73.184/73.190,
"Graphs 1-20") rather than a hand-fit approximation - the FCC's AM
groundwave method is graphical/tabular, not a formula, so there's no
"correct" closed-form equation to implement. These are the actual
regulatory curves broadcast engineers use for this exact calculation,
digitized directly from FCC's own PDFs (see fcc_groundwave_curves.py) -
a public domain U.S. government work, unlike the third-party Fortran
package (`grwave`, unresolved 1985 corporate copyright, no accompanying
license) this module depended on previously.

Uses a single assumed "average US land" ground conductivity (3 mS/m,
matching one of FCC's standard labeled curves), not a real conductivity
map - that's the v1 simplification. A terrain-aware upgrade would swap
this for FCC's M3 conductivity map, computed per station's actual site.

Field strength is exactly proportional to sqrt(power) for fixed
frequency/ground/geometry (linear system), so the digitized curves are
precomputed once per distinct AM frequency at a 1 kW reference, then
scaled per station by actual power - avoiding any need to recompute per
station.

Known gap: the digitized curve's closest point is ~5km out, so very
high thresholds (>=~60 dBu for a typical station) that are only crossed
within 5km of the transmitter come back as null even though they're
obviously true in reality - not a practical concern for "can I receive
this station" at any normal distance, but worth knowing if these
numbers ever get used for something near-field.
"""
import math

import fcc_groundwave_curves

# FCC's standard labeled ground conductivity used for the digitized
# curve (see fcc_groundwave_curves.py) - a commonly cited stand-in for
# "average" US land in the absence of a real per-site value.
GROUND_SIGMA_S_M = 3e-3

REFERENCE_POWER_W = 1000.0  # 1 kW reference; scale by sqrt(actual/ref)

# Thresholds to precompute, in dBu (dB above 1 uV/m) - same unit FM
# uses, so the frontend can expose one unified threshold control.
THRESHOLDS_DBU = list(range(20, 85, 5))


def reference_curve_km_vs_dbu(freq_khz):
    """Look up FCC's digitized groundwave curve for this frequency at
    the reference power. Returns sorted list of (distance_km,
    field_strength_dbu), interpolated between FCC's nearest two
    representative frequency graphs when freq_khz doesn't land exactly
    on one of the 20.
    """
    return fcc_groundwave_curves.curve_km_vs_dbu(freq_khz)


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
            # never dropped below threshold within the digitized curve
            ranges[threshold] = reference_points[-1][0]
    return ranges
