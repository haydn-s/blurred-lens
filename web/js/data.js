// Loads the world map and the exported manifest, and ties each map shape to a country.

import { geoArea, geoCentroid } from "d3-geo";
import { feature } from "topojson-client";

const WORLD_URL = "https://cdn.jsdelivr.net/npm/world-atlas@2.0.2/countries-50m.json";
const MANIFEST_URL = "data/manifest.json";

// Map shapes with no ISO code of their own, shown as part of the UN member they belong to.
const SHAPE_ALIASES = { somaliland: "SOM", "n. cyprus": "CYP" };

const pad3 = (id) => (id == null ? null : String(id).padStart(3, "0"));

async function fetchJson(url, options) {
  const res = await fetch(url, options);
  if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
  return res.json();
}

export async function loadData() {
  const [world, manifest] = await Promise.all([
    fetchJson(WORLD_URL),
    // The globe still works before `python -m blurred_lens.export_site` has ever run.
    fetchJson(MANIFEST_URL, { cache: "no-cache" }).catch(() => null),
  ]);

  const countries = (manifest?.countries ?? []).map((c) => ({
    ...c,
    done: c.entries.filter((e) => e.metrics).length, // places whose images have been measured
    focus: null, // { lat, lng } the camera flies to
  }));
  const byIso3 = new Map(countries.map((c) => [c.iso3, c]));
  const byNum = new Map(countries.filter((c) => c.iso_num).map((c) => [pad3(c.iso_num), c]));
  const byName = new Map(countries.map((c) => [c.name.toLowerCase(), c]));

  const shapes = feature(world, world.objects.countries).features;
  for (const shape of shapes) {
    const name = shape.properties.name?.toLowerCase();
    const direct = byNum.get(pad3(shape.id)) ?? byName.get(name);
    shape.country = direct ?? byIso3.get(SHAPE_ALIASES[name]) ?? null;
    if (direct && !direct.focus) direct.focus = focusPoint(shape.geometry);
  }
  return { manifest, countries, byIso3, shapes };
}

// Centroid of the largest landmass, so e.g. France centers on Europe, not the Atlantic
// between Paris and French Guiana.
function focusPoint(geometry) {
  const polygons = geometry.type === "MultiPolygon" ? geometry.coordinates : [geometry.coordinates];
  let largest = polygons[0];
  let largestArea = -1;
  for (const coordinates of polygons) {
    const area = geoArea({ type: "Polygon", coordinates });
    if (area > largestArea) [largest, largestArea] = [coordinates, area];
  }
  const [lng, lat] = geoCentroid({ type: "Polygon", coordinates: largest });
  return { lat, lng };
}
