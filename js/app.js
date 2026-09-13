import { neighborCodes } from "./plus-codes.js";
import {
  evaluateStation,
  THRESHOLD_MIN_DBU,
  THRESHOLD_MAX_DBU,
  THRESHOLD_DEFAULT_DBU,
} from "./reception.js";

// Conservative worst-case AM range (km) at each threshold, based on the
// most powerful legal AM stations (50kW) over our assumed average
// ground - used only to decide how wide a neighborhood of Plus Code
// cells to fetch, not for the actual per-station reception calculation
// (that always uses the station's own precomputed table). Padded above
// the real worst case we've observed (WABC, 50kW) since lower-frequency
// AM channels attenuate somewhat less.
const FETCH_RADIUS_BY_THRESHOLD_KM = [
  [20, 460], [25, 360], [30, 260], [35, 190],
  [40, 130], [45, 90], [50, 55], [55, 35],
  [60, 25], [65, 25], [70, 25], [75, 25], [80, 25],
];

function fetchRadiusForThreshold(thresholdDbu) {
  for (const [t, r] of FETCH_RADIUS_BY_THRESHOLD_KM) {
    if (thresholdDbu <= t) return r;
  }
  return 25;
}

const state = {
  userLat: null,
  userLon: null,
  loadedCodes: new Set(),
  stations: [],
  thresholdDbu: THRESHOLD_DEFAULT_DBU,
  isDaytime: isLikelyDaytime(),
  manifest: null, // Set of partition codes that actually exist, or null if unknown
};

// Known ahead of time so we don't 404 on every one of the many empty
// (ocean, unpopulated) neighbor cells around a typical US location.
// Falls back to "fetch everything and ignore failures" if unavailable.
fetch("data/plus4/manifest.json")
  .then((r) => (r.ok ? r.json() : null))
  .then((codes) => {
    if (codes) state.manifest = new Set(codes);
  })
  .catch(() => {});

function isLikelyDaytime() {
  const hour = new Date().getHours();
  return hour >= 7 && hour < 19;
}

const map = L.map("map", { zoomControl: true }).setView([39.8, -98.6], 4);
L.tileLayer(
  "https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}",
  {
    attribution:
      "Tiles &copy; Esri &mdash; Source: Esri, DeLorme, NAVTEQ, USGS, Intermap, iPC, NRCAN, Esri Japan, METI, Esri China (Hong Kong), Esri (Thailand), TomTom",
    maxZoom: 19,
  }
).addTo(map);

const userMarker = L.marker([39.8, -98.6], { opacity: 0 }).addTo(map);
const stationLayer = L.layerGroup().addTo(map);

const statusEl = document.getElementById("status");
const listEl = document.getElementById("station-list");
const thresholdInput = document.getElementById("threshold");
const thresholdLabel = document.getElementById("threshold-label");
const dayNightInput = document.getElementById("day-night");
const locateBtn = document.getElementById("locate-btn");

thresholdInput.min = THRESHOLD_MIN_DBU;
thresholdInput.max = THRESHOLD_MAX_DBU;
thresholdInput.value = THRESHOLD_DEFAULT_DBU;
dayNightInput.checked = state.isDaytime;
updateThresholdLabel();

thresholdInput.addEventListener("input", () => {
  state.thresholdDbu = Number(thresholdInput.value);
  updateThresholdLabel();
  refreshForThreshold();
});
dayNightInput.addEventListener("change", () => {
  state.isDaytime = dayNightInput.checked;
  render();
});
locateBtn.addEventListener("click", () => locate());
map.on("click", (e) => setLocation(e.latlng.lat, e.latlng.lng));

function updateThresholdLabel() {
  let desc = "Fringe";
  if (state.thresholdDbu >= 70) desc = "Strong / city-grade";
  else if (state.thresholdDbu >= 50) desc = "Reliable";
  else if (state.thresholdDbu >= 35) desc = "Marginal";
  thresholdLabel.textContent = `${state.thresholdDbu} dBu (${desc})`;
}

function locate() {
  if (!navigator.geolocation) {
    setStatus("Geolocation isn't available in this browser - click the map to set a location.");
    return;
  }
  setStatus("Requesting your location...");
  navigator.geolocation.getCurrentPosition(
    (pos) => setLocation(pos.coords.latitude, pos.coords.longitude),
    () => setStatus("Location permission denied - click the map to set a location instead."),
    { enableHighAccuracy: false, timeout: 10000 }
  );
}

async function setLocation(lat, lon) {
  state.userLat = lat;
  state.userLon = lon;
  userMarker.setLatLng([lat, lon]).setOpacity(1);
  map.setView([lat, lon], 8);
  await refreshForThreshold();
}

async function refreshForThreshold() {
  if (state.userLat == null) return;
  const radiusKm = fetchRadiusForThreshold(state.thresholdDbu);
  await ensureCoverage(state.userLat, state.userLon, radiusKm);
  render();
}

async function ensureCoverage(lat, lon, radiusKm) {
  const needed = neighborCodes(lat, lon, radiusKm).filter(
    (code) =>
      !state.loadedCodes.has(code) && (state.manifest == null || state.manifest.has(code))
  );
  if (needed.length === 0) return;

  setStatus(`Loading station data (${needed.length} area${needed.length === 1 ? "" : "s"})...`);
  const results = await Promise.all(
    needed.map(async (code) => {
      state.loadedCodes.add(code);
      try {
        const resp = await fetch(`data/plus4/${code}.json`);
        if (!resp.ok) return [];
        return await resp.json();
      } catch {
        return []; // sparsely-populated area with no partition file - expected, not an error
      }
    })
  );
  for (const records of results) {
    state.stations.push(...records);
  }
}

function render() {
  stationLayer.clearLayers();
  if (state.userLat == null) {
    setStatus("Click the map or use “Use my location” to see what you can receive.");
    listEl.innerHTML = "";
    return;
  }

  const results = state.stations
    .map((station) =>
      Object.assign(
        { station },
        evaluateStation(station, state.userLat, state.userLon, state.thresholdDbu, state.isDaytime)
      )
    )
    .filter((r) => r.receivable)
    .sort((a, b) => a.distKm - b.distKm);

  const amCount = results.filter((r) => r.station.service === "AM").length;
  const fmCount = results.length - amCount;
  setStatus(`${results.length} station${results.length === 1 ? "" : "s"} receivable nearby (${amCount} AM, ${fmCount} FM)`);

  listEl.innerHTML = "";
  for (const r of results) {
    const s = r.station;
    const color = s.service === "AM" ? "#c0392b" : "#2c6fbb";
    const marker = L.circleMarker([s.lat, s.lon], {
      radius: 6,
      color,
      fillColor: color,
      fillOpacity: 0.8,
      weight: 1,
    });
    marker.bindPopup(
      `<strong>${s.callsign}</strong> ${s.service} ${s.frequency}<br>` +
        `${s.city}, ${s.state}<br>` +
        `${r.distKm.toFixed(1)} km away`
    );
    marker.addTo(stationLayer);

    const li = document.createElement("li");
    li.innerHTML = `<span class="dot" style="background:${color}"></span>` +
      `<strong>${s.callsign}</strong> ${s.frequency} ${s.service} ` +
      `<span class="muted">${r.distKm.toFixed(0)} km · ${s.city}, ${s.state}</span>`;
    li.addEventListener("click", () => {
      map.setView([s.lat, s.lon], 10);
      marker.openPopup();
    });
    listEl.appendChild(li);
  }
}

function setStatus(text) {
  statusEl.textContent = text;
}

// Try geolocation automatically on load; falls back to manual map click.
locate();
