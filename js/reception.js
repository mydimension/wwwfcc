// Reception modeling. See the data pipeline (scripts/am_groundwave.py,
// scripts/parse_stations.py) for how station data is derived - this
// module is the frontend half of the same "simple, not terrain-aware"
// v1 model described there.
//
// Both bands are compared against the same dBu (dB above 1 uV/m)
// threshold so one slider controls both.

import { haversineKm } from "./plus-codes.js";

export const THRESHOLD_MIN_DBU = 20;
export const THRESHOLD_MAX_DBU = 80;
export const THRESHOLD_DEFAULT_DBU = 50;

// Must exactly match scripts/am_groundwave.py's THRESHOLDS_DBU.
const AM_THRESHOLDS_DBU = [20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80];

const RECEIVER_HEIGHT_M = 2; // typical car/handheld receive height

// FM: free-space field strength + radio horizon cutoff.
// E(dBu) = 106.92 + 10*log10(ERP_kW) - 20*log10(d_km)
// horizon_km = 4.12 * (sqrt(HAAT_m) + sqrt(receiver_height_m))
export function evaluateFm(station, userLat, userLon, thresholdDbu) {
  const distKm = haversineKm(userLat, userLon, station.lat, station.lon);
  if (station.erp_kw == null || station.haat_m == null) {
    return { distKm, receivable: false, dataIncomplete: true };
  }
  const horizonKm =
    4.12 * (Math.sqrt(Math.max(station.haat_m, 0)) + Math.sqrt(RECEIVER_HEIGHT_M));
  if (distKm > horizonKm) {
    return { distKm, receivable: false, horizonKm };
  }
  const fieldDbu =
    106.92 + 10 * Math.log10(station.erp_kw) - 20 * Math.log10(Math.max(distKm, 0.1));
  return { distKm, receivable: fieldDbu >= thresholdDbu, fieldDbu, horizonKm };
}

// AM: interpolate the precomputed GRWAVE range-vs-threshold table.
// Range decreases monotonically as the threshold rises, so we find the
// two bracketing table points and linearly interpolate between them.
// A null table entry means "threshold never reached, even close in" -
// treated as zero range for interpolation purposes.
function interpolateRangeKm(rangeKm, thresholdDbu) {
  if (!rangeKm || rangeKm.every((v) => v == null)) return null;
  const t = Math.min(Math.max(thresholdDbu, THRESHOLD_MIN_DBU), THRESHOLD_MAX_DBU);

  for (let i = 0; i < AM_THRESHOLDS_DBU.length - 1; i++) {
    const t0 = AM_THRESHOLDS_DBU[i];
    const t1 = AM_THRESHOLDS_DBU[i + 1];
    if (t >= t0 && t <= t1) {
      const r0 = rangeKm[i] ?? 0;
      const r1 = rangeKm[i + 1] ?? 0;
      const frac = t1 === t0 ? 0 : (t - t0) / (t1 - t0);
      return r0 + frac * (r1 - r0);
    }
  }
  return null;
}

export function evaluateAm(station, userLat, userLon, thresholdDbu, isDaytime) {
  const distKm = haversineKm(userLat, userLon, station.lat, station.lon);
  const rangeKm = isDaytime ? station.range_day_km : station.range_night_km;
  if (!rangeKm) {
    return { distKm, receivable: false, dataIncomplete: true };
  }
  const maxRangeKm = interpolateRangeKm(rangeKm, thresholdDbu);
  if (maxRangeKm == null) {
    return { distKm, receivable: false };
  }
  return { distKm, receivable: distKm <= maxRangeKm, maxRangeKm };
}

export function evaluateStation(station, userLat, userLon, thresholdDbu, isDaytime) {
  if (station.service === "FM") {
    return evaluateFm(station, userLat, userLon, thresholdDbu);
  }
  return evaluateAm(station, userLat, userLon, thresholdDbu, isDaytime);
}

// The largest radius any station in the dataset could plausibly reach
// at the most permissive threshold this UI allows - used to decide how
// wide a neighborhood of Plus Code cells to fetch. AM's precomputed
// table caps at 500km (am_groundwave.DMAX_KM); FM's horizon+free-space
// model rarely exceeds ~150km for even the tallest/most powerful
// stations. AM dominates, so this drives the fetch radius.
export const MAX_SEARCH_RADIUS_KM = 500;
