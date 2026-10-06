// The interactive globe: country styling, hover glow, selection and camera moves.

import Globe from "globe.gl";
import * as THREE from "three";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { clamp, prefersReducedMotion, wait } from "./util.js";

// A country's tint is its standing on the headline measurement: a diverging scale, because the
// number has a sign -- how far above or below the average country it sits, in either direction.
// Blue for cooler, amber for warmer, so the encoding is the thing being measured rather than an
// arbitrary mapping, with a neutral grey in the middle that reads as "nothing to report".
//
// Built from OKLCH so the two arms are symmetric: equal lightness at equal distance from the
// middle (L 0.53 -> 0.60 -> 0.69 -> 0.78 on both sides), chroma lowest in the middle, hue alone
// carrying the sign. That symmetry is what stops one direction looking stronger than the other.
// The poles separate by Delta-E 25 under protanopia and tritanopia, well clear of the 8 the
// palette validator asks for, and every step clears 3:1 against the ocean behind it.
//
// The breaks match the language the About page uses: inside a third of a standard deviation is
// the middle of the pack, past one and a half is far out.
export const SCALE = {
  breaks: [-1.5, -0.9, -0.3, 0.3, 0.9, 1.5], // 7 buckets, symmetric about zero
  colors: ["#6abcff", "#649fe0", "#6283a6", "#6d6c67", "#957c53", "#c2923f", "#eca92e"],
};

const COLORS = {
  background: "#04060c",
  ocean: "#070d1b",
  oceanSpecular: "#1e2f55",
  land: "#1b2538",
  landUnlisted: "#131a28",
  side: "#0e1524",
  border: "rgba(160, 185, 255, 0.2)",
  // Hover has to say "you are pointing at this", never "this country measured pink". So it sits off
  // the scale's blue-amber axis entirely -- 83 degrees of hue from the cool pole and 102 from the
  // warm one -- and above it in lightness: OKLCH L 0.88 against the brightest step's 0.78, which
  // makes the hovered country the brightest thing on the globe whatever its own tint. Lightness is
  // what carries that when hue cannot: against all seven steps and both land tones the worst
  // separation is Delta-E 8.7 under deuteranopia, protanopia and tritanopia. The country also rises
  // and blooms, so the colour is never the only cue.
  glow: "#ffbef0",
  glowBorder: "rgba(255, 233, 250, 0.9)",
  atmosphere: "#4776ff",
};
const ALTITUDE = { rest: 0.006, lit: 0.026 };
const VIEW = { start: { lat: 22, lng: 12, altitude: 2.5 }, focus: 1.55, overview: 2.35 };
// A faint glow: bloom only picks up pixels brighter than `threshold`, which the lit country
// clears but land and atmosphere don't. Stronger settings wash the country out to white.
const BLOOM = { strength: 0.18, radius: 0.5, threshold: 0.2 };
const AUTO_ROTATE_RESUME_MS = 3500;
const FLY_MS = 1200;
const hasHover = matchMedia("(hover: hover) and (pointer: fine)").matches;

export class GlobeView {
  constructor(container, shapes, { onHover, onSelect, onReady }) {
    this.onHover = onHover;
    this.onSelect = onSelect;
    this.hovered = null; // country under the pointer
    this.selected = null; // country whose gallery is open
    this.resumeTimer = 0;

    const lambert = (color) => new THREE.MeshLambertMaterial({ color });
    // One material per bucket rather than per country: 7 shared materials, not 60.
    this.scaleMaterials = SCALE.colors.map(lambert);
    this.materials = {
      land: lambert(COLORS.land),
      landUnlisted: lambert(COLORS.landUnlisted),
      side: lambert(COLORS.side),
      glow: new THREE.MeshBasicMaterial({ color: COLORS.glow }),
      glowSide: new THREE.MeshBasicMaterial({ color: COLORS.glow, transparent: true, opacity: 0.35 }),
    };

    this.globe = new Globe(container, { animateIn: !prefersReducedMotion })
      .width(innerWidth)
      .height(innerHeight)
      .backgroundColor(COLORS.background)
      .globeMaterial(new THREE.MeshPhongMaterial({ color: COLORS.ocean, specular: COLORS.oceanSpecular, shininess: 16 }))
      .atmosphereColor(COLORS.atmosphere)
      .atmosphereAltitude(0.19)
      .polygonsData(shapes)
      .polygonCapCurvatureResolution(4)
      .polygonsTransitionDuration(prefersReducedMotion ? 0 : 300)
      .polygonLabel(() => null)
      .showPointerCursor((type, data) => type === "polygon" && Boolean(data?.country))
      .onPolygonHover((shape) => this.setHovered(shape?.country ?? null))
      .onPolygonClick((shape) => shape?.country && this.onSelect(shape.country))
      .onGlobeReady(onReady);

    // Draw the background as part of the scene. With post-processing, the renderer's clear
    // color gets sRGB-encoded twice (#04060c would come out slate gray, #222a3d).
    this.globe.scene().background = new THREE.Color(COLORS.background);
    this.globe.pointOfView({ ...VIEW.start, altitude: this.fitAltitude(VIEW.start.altitude) });
    this.restyle();
    this.setupLights();
    this.setupControls();
    if (hasHover) this.setupGlow(); // touch screens can't hover, so skip the extra render passes
    // globe.gl resizes the renderer and the post-processing passes to match.
    addEventListener("resize", () => {
      this.globe.width(innerWidth).height(innerHeight);
      this.updateZoomLimits();
    });
  }

  // ---- Styling -------------------------------------------------------------

  restyle() {
    const lit = (shape) => shape.country !== null && (shape.country === this.hovered || shape.country === this.selected);
    // globe.gl re-evaluates accessors when they are replaced, animating altitude changes.
    this.globe
      .polygonCapMaterial((s) => (lit(s) ? this.materials.glow : this.restingMaterial(s)))
      .polygonSideMaterial((s) => (lit(s) ? this.materials.glowSide : this.materials.side))
      .polygonStrokeColor((s) => (lit(s) ? COLORS.glowBorder : COLORS.border))
      .polygonAltitude((s) => (lit(s) ? ALTITUDE.lit : ALTITUDE.rest));
  }

  restingMaterial(shape) {
    if (!shape.country) return this.materials.landUnlisted; // not in the country list at all
    const { index } = shape.country;
    // Listed but not generated yet stays unlit, so "no data" never looks like "average".
    if (!shape.country.done || typeof index !== "number") return this.materials.land;
    return this.scaleMaterials[SCALE.breaks.filter((edge) => index >= edge).length];
  }

  setupLights() {
    // A key light attached to the camera keeps the lit side facing the viewer as the globe turns.
    const key = new THREE.DirectionalLight(0xffffff, 2.2);
    key.position.set(-160, 190, 240);
    const camera = this.globe.camera();
    camera.add(key);
    this.globe.scene().add(camera);
    this.globe.lights([new THREE.AmbientLight(0xa9b8ff, 1.3)]);
  }

  setupGlow() {
    const composer = this.globe.postProcessingComposer();
    this.bloom = new UnrealBloomPass(new THREE.Vector2(innerWidth, innerHeight), BLOOM.strength, BLOOM.radius, BLOOM.threshold);
    composer.addPass(this.bloom);
    composer.addPass(new OutputPass()); // tone mapping + sRGB output after the bloom pass
  }

  // ---- Controls ------------------------------------------------------------

  setupControls() {
    // globe.gl already scales rotate/zoom speed with altitude; this adds glide and zoom limits.
    const controls = this.globe.controls();
    const radius = this.globe.getGlobeRadius();
    Object.assign(controls, {
      enableDamping: true,
      dampingFactor: 0.07,
      enablePan: false,
      minDistance: radius * 1.45,
      autoRotate: !prefersReducedMotion,
      autoRotateSpeed: 0.32,
    });
    controls.addEventListener("start", () => this.stopAutoRotate());
    controls.addEventListener("end", () => this.scheduleAutoRotate());
    this.updateZoomLimits();
  }

  // On narrow portrait screens the horizontal field of view is the limit: pull the camera
  // back until the whole globe (plus a sliver of atmosphere) fits the width.
  fitAltitude(altitude) {
    const halfV = THREE.MathUtils.degToRad(this.globe.camera().fov) / 2;
    const halfH = Math.atan(Math.tan(halfV) * (innerWidth / innerHeight));
    return Math.max(altitude, 1.08 / Math.sin(Math.min(halfV, halfH)) - 1);
  }

  updateZoomLimits() {
    const radius = this.globe.getGlobeRadius();
    this.globe.controls().maxDistance = radius * (1 + Math.max(3.2, this.fitAltitude(0) + 0.8));
  }

  stopAutoRotate() {
    clearTimeout(this.resumeTimer);
    this.globe.controls().autoRotate = false;
  }

  scheduleAutoRotate(delay = AUTO_ROTATE_RESUME_MS) {
    clearTimeout(this.resumeTimer);
    if (prefersReducedMotion) return;
    this.resumeTimer = setTimeout(() => {
      if (!this.hovered && !this.selected) this.globe.controls().autoRotate = true;
    }, delay);
  }

  // ---- Public API ----------------------------------------------------------

  setHovered(country) {
    if (country === this.hovered) return;
    this.hovered = country;
    this.restyle();
    this.onHover(country);
    // Hold still under the pointer so the glowing country doesn't drift away.
    if (country) this.stopAutoRotate();
    else this.scheduleAutoRotate();
  }

  // Fly to a country and keep it lit while its gallery is open.
  async focus(country) {
    this.selected = country;
    this.stopAutoRotate();
    this.globe.resumeAnimation();
    this.globe.enablePointerInteraction(false);
    this.setHovered(null);
    this.restyle();
    if (!country.focus) return; // e.g. Tuvalu: too small for the 1:50m map
    const ms = prefersReducedMotion ? 0 : FLY_MS;
    this.globe.pointOfView({ ...country.focus, altitude: VIEW.focus }, ms);
    await wait(ms);
  }

  // Freeze rendering behind the gallery to save battery; the last frame stays on screen.
  pause() {
    this.globe.pauseAnimation();
  }

  release() {
    this.selected = null;
    this.restyle();
    this.globe.resumeAnimation();
    this.globe.enablePointerInteraction(true);
    this.globe.pointOfView({ altitude: this.fitAltitude(VIEW.overview) }, prefersReducedMotion ? 0 : 1000);
    this.scheduleAutoRotate(1600);
  }

  // Keyboard rotation.
  nudge(dLat, dLng) {
    const { lat, lng } = this.globe.pointOfView();
    this.stopAutoRotate();
    this.globe.pointOfView({ lat: clamp(lat + dLat, -75, 75), lng: lng + dLng }, prefersReducedMotion ? 0 : 450);
    this.scheduleAutoRotate();
  }
}
