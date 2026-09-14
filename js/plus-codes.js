// Minimal Open Location Code (Plus Code) support - just enough to
// compute the length-4 prefix used to partition station data, and to
// enumerate which prefixes cover a search radius around a point.
//
// Full spec: https://github.com/google/open-location-code
// We only need the first two character-pairs (20 degrees, then 1
// degree), so this is a small hand-rolled encoder rather than pulling
// in the full library - verified byte-for-byte against the real
// python `openlocationcode` package (the same one the data pipeline
// uses) for multiple reference points worldwide, including negative
// longitudes, southern hemisphere, and the antimeridian.

const ALPHABET = "23456789CFGHJMPQRVWX";
const CODE_LENGTH = 4;

export function encode4(lat, lon) {
  // Normalize into OLC's encoding range the same way the spec does.
  let latVal = lat + 90;
  let lonVal = lon + 180;
  lonVal = ((lonVal % 360) + 360) % 360; // wrap the antimeridian

  const latDigit1 = Math.min(Math.floor(latVal / 20), 8); // clamp: lat=90 edge case
  const lonDigit1 = Math.floor(lonVal / 20);
  latVal -= latDigit1 * 20;
  lonVal -= lonDigit1 * 20;

  const latDigit2 = Math.min(Math.floor(latVal), 19);
  const lonDigit2 = Math.min(Math.floor(lonVal), 19);

  return (
    ALPHABET[latDigit1] +
    ALPHABET[lonDigit1] +
    ALPHABET[latDigit2] +
    ALPHABET[lonDigit2]
  );
}

const KM_PER_DEGREE_LAT = 111.0;

// Every 4-char-prefix cell is exactly 1 *actual* degree of latitude and
// 1 *actual* degree of longitude - cell boundaries sit on whole-degree
// lines regardless of latitude (that's why they narrow in physical km
// toward the poles, rather than staying square). So neighbor cells must
// be sampled at 1-degree steps to land on adjacent cells; only the
// *number* of lon steps needed to cover a given radius should account
// for longitude degrees getting physically narrower at higher latitudes.
// (A cosine-scaled step here previously overshot by more than a degree
// per step at mid latitudes and could jump clean over the cell
// immediately next to the search point - see WBZ/Billerica regression.)
export function neighborCodes(lat, lon, radiusKm) {
  const latCells = Math.ceil(radiusKm / KM_PER_DEGREE_LAT);
  const lonCells = Math.ceil(radiusKm / (KM_PER_DEGREE_LAT * Math.cos((lat * Math.PI) / 180)));

  const codes = new Set();
  for (let i = -latCells; i <= latCells; i++) {
    for (let j = -lonCells; j <= lonCells; j++) {
      const sampleLat = lat + i;
      const sampleLon = lon + j;
      if (sampleLat < -90 || sampleLat > 90) continue;
      codes.add(encode4(sampleLat, sampleLon));
    }
  }
  return Array.from(codes);
}

export function haversineKm(lat1, lon1, lat2, lon2) {
  const R = 6371;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}
