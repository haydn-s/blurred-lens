// Entry point: loads the data, builds the globe, search and gallery, and keeps the URL in
// sync. #/NGA opens Nigeria's gallery, and the browser's back button closes it again.

import { loadData } from "./data.js";
import { Gallery } from "./gallery.js";
import { GlobeView } from "./globe.js";
import { createSearch } from "./search.js";
import { Tooltip } from "./tooltip.js";
import { formatCount, isEditable, prefersReducedMotion, wait } from "./util.js";

const $ = (selector) => document.querySelector(selector);
const GALLERY_DELAY_MS = 450; // start fading the gallery in while the camera is still flying
const LOADER_FALLBACK_MS = 6000;

function webglAvailable() {
  try {
    const canvas = document.createElement("canvas");
    return Boolean(canvas.getContext("webgl2") || canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

function showLoaderError(message) {
  $("#loader").classList.add("is-error");
  $("#loader .loader-text").textContent = message;
}

const hideLoader = () => $("#loader").classList.add("is-done");

function renderHud(manifest, countries) {
  if (!manifest) {
    $("#hud-template").textContent = "—";
    $("#hud-stats").textContent = "No data yet: run python -m blurred_lens.export_site";
    return;
  }
  const entries = countries.flatMap((c) => c.entries);
  const done = entries.filter((e) => e.composite).length;
  const images = entries.reduce((sum, e) => sum + e.n_images, 0);
  $("#hud-template").textContent = `“${manifest.template}”`;
  $("#hud-stats").textContent =
    `${countries.filter((c) => c.done).length} of ${countries.length} countries · ` +
    `${formatCount(done)} of ${formatCount(entries.length)} prompts · ${formatCount(images)} images`;
}

async function main() {
  if (!webglAvailable()) {
    showLoaderError("This globe needs WebGL, which is turned off or unsupported in this browser.");
    return;
  }
  let data;
  try {
    data = await loadData();
  } catch (err) {
    console.error(err);
    showLoaderError("Couldn’t load the globe. Check your connection and reload.");
    return;
  }
  const { manifest, countries, byIso3, shapes } = data;
  renderHud(manifest, countries);

  const chrome = $(".chrome");
  const tooltip = new Tooltip($("#tooltip"));
  const globe = new GlobeView($("#globe"), shapes, {
    onHover: (country) => tooltip.show(country),
    onSelect: (country) => openCountry(country.iso3),
    onReady: hideLoader,
  });
  setTimeout(hideLoader, LOADER_FALLBACK_MS);
  const gallery = new Gallery($("#gallery"), { places: manifest?.places ?? [], onRequestClose: closeCountry });
  createSearch($(".search"), countries, { onSelect: (country) => openCountry(country.iso3) });
  // Open index.html?debug to inspect the globe and gallery from the browser console.
  if (new URLSearchParams(location.search).has("debug")) window.blurredLens = { globe, gallery, countries };

  let current = null; // country whose gallery is open or opening
  let pushedEntry = false; // whether the current history entry was added by openCountry()

  function openCountry(iso3) {
    pushedEntry = true;
    location.hash = `/${iso3}`;
  }

  function closeCountry() {
    if (pushedEntry) {
      history.back(); // pops our entry; the hashchange handler closes the gallery
      return;
    }
    history.replaceState(null, "", location.pathname + location.search);
    route();
  }

  async function route() {
    const country = byIso3.get(location.hash.replace(/^#\/?/, "").toUpperCase()) ?? null;
    if (country === current) return;
    current = country;
    if (!country) {
      pushedEntry = false;
      gallery.close();
      chrome.inert = false;
      globe.release();
      return;
    }
    tooltip.hide();
    chrome.inert = true;
    const flight = globe.focus(country);
    await wait(prefersReducedMotion ? 0 : GALLERY_DELAY_MS);
    if (current !== country) return; // navigated elsewhere mid-flight
    gallery.open(country);
    await flight;
    if (current === country) globe.pause();
  }

  addEventListener("hashchange", route);
  addEventListener("keydown", (e) => {
    if (current || isEditable(e.target) || e.metaKey || e.ctrlKey || e.altKey) return;
    const step = { ArrowLeft: [0, -15], ArrowRight: [0, 15], ArrowUp: [10, 0], ArrowDown: [-10, 0] }[e.key];
    if (!step) return;
    e.preventDefault();
    globe.nudge(...step);
  });
  route(); // honours deep links such as index.html#/JPN
}

main();
