// Full-screen gallery of one country's composite images: a card per place, scroll-snapped
// horizontally, driven by swipe, wheel, keyboard, arrow buttons or the place tabs.

import { el, formatCount, prefersReducedMotion } from "./util.js";

const CLOSE_MS = 480; // matches --gallery-ms in styles.css
const WHEEL_QUIET_MS = 180; // one wheel/trackpad gesture moves one card
const SUPPORTS_SCROLLEND = "onscrollend" in window;
const METRIC_SPAN = 3; // z-scores past three standard deviations fill the bar

export class Gallery {
  constructor(root, { places, metric, onRequestClose }) {
    this.root = root;
    this.placeLabels = new Map(places.map((p) => [p.id, p.label]));
    this.metric = metric ?? null; // which measurement the z-scores describe
    this.onRequestClose = onRequestClose;
    this.track = root.querySelector(".gallery-track");
    this.tabs = root.querySelector(".gallery-tabs");
    this.title = root.querySelector(".gallery-title");
    this.region = root.querySelector(".gallery-region");
    this.summary = root.querySelector(".gallery-summary");
    this.prevButton = root.querySelector('[data-action="prev"]');
    this.nextButton = root.querySelector('[data-action="next"]');

    this.country = null;
    this.cards = []; // { node, frame, count, entry }
    this.tabButtons = [];
    this.index = 0;
    this.targetIndex = null; // set while a programmatic scroll is running
    this.frame = 0;
    this.wheelLocked = false;
    this.wheelTimer = 0;
    this.closeTimer = 0;

    root.addEventListener("click", (e) => this.handleClick(e));
    root.addEventListener("wheel", (e) => this.handleWheel(e), { passive: false });
    this.track.addEventListener("scroll", () => this.scheduleFocusUpdate(), { passive: true });
    this.track.addEventListener("scrollend", () => this.finishScroll());
    this.handleKey = this.handleKey.bind(this);
    addEventListener("resize", () => this.isOpen && this.go(this.index, false));
  }

  get isOpen() {
    return this.country !== null;
  }

  open(country) {
    const wasOpen = this.isOpen;
    clearTimeout(this.closeTimer);
    this.country = country;
    if (!wasOpen) this.returnFocus = document.activeElement;

    this.region.textContent = `${country.subregion} · ${country.region}`;
    this.title.textContent = country.name;
    this.summary.textContent = country.done
      ? `${country.done} of ${country.entries.length} places generated · ${formatCount(totalImages(country))} images`
      : "Nothing has been generated for this country yet";
    this.renderCards(country);
    this.renderTabs(country);

    this.root.hidden = false;
    this.root.getBoundingClientRect(); // commit the un-hide before starting the transition
    this.root.classList.add("is-open");
    document.addEventListener("keydown", this.handleKey);
    this.go(Math.max(0, country.entries.findIndex((e) => e.metrics)), false);
    this.root.querySelector('[data-action="close"]').focus({ preventScroll: true });
  }

  close() {
    if (!this.isOpen) return;
    this.country = null;
    document.removeEventListener("keydown", this.handleKey);
    this.root.classList.remove("is-open");
    this.closeTimer = setTimeout(() => {
      this.root.hidden = true;
      this.track.replaceChildren();
    }, prefersReducedMotion ? 0 : CLOSE_MS);
    this.returnFocus?.focus?.({ preventScroll: true });
  }

  // ---- Rendering -----------------------------------------------------------

  renderCards(country) {
    const total = country.entries.length;
    this.cards = country.entries.map((entry, i) => {
      const label = this.placeLabels.get(entry.place) ?? entry.place;
      const frame = el("div", { class: "card-frame" });
      const count = el("span", { class: "card-count" });
      if (entry.metrics) {
        // No composite any more: the frame shows a few of the images the numbers came from.
        frame.append(el("div", { class: "card-grid" },
          ...entry.samples.slice(0, 4).map((s) =>
            el("img", { src: `data/${s.image}`, alt: `One of the images generated for “${entry.prompt}”`,
                        loading: "lazy", decoding: "async", draggable: "false" })),
        ));
        frame.classList.add("is-loaded");
        count.textContent = `${formatCount(entry.n_images)} images measured`;
      } else {
        frame.classList.add("is-empty");
        frame.append(el("span", { class: "card-empty-label" }, "Not generated yet"));
        count.textContent = "Awaiting generation";
      }
      const sources = entry.samples.map((s) =>
        el("img", { src: `data/${s.image}`, alt: "", loading: "lazy", draggable: "false", title: s.revised_prompt ?? entry.prompt }),
      );
      const node = el("li", { class: "card", style: `--i: ${i}`, "aria-roledescription": "slide", "aria-label": `${label}, ${i + 1} of ${total}` },
        el("figure", { class: "card-figure" },
          frame,
          el("figcaption", { class: "card-caption" },
            el("div", { class: "card-heading" }, el("span", { class: "card-place" }, label), count),
            el("p", { class: "card-prompt" }, `“${entry.prompt}”`),
            this.measurements(entry),
            sources.length ? el("div", { class: "card-sources", title: "Some of the images these numbers came from" }, ...sources) : null,
          ),
        ),
      );
      return { node, frame, count, entry };
    });
    this.track.replaceChildren(...this.cards.map((card) => card.node));
    this.track.scrollLeft = 0;
  }

  // How this prompt's images compare with every other country's images of the same place.
  measurements(entry) {
    if (!entry.metrics) return null;
    const rows = [];
    if (this.metric && typeof entry.z === "number") {
      rows.push(
        el("div", { class: "metric-head" },
          el("span", { class: "metric-label" }, this.metric.label),
          el("span", { class: "metric-value" }, `${entry.z >= 0 ? "+" : ""}${entry.z.toFixed(2)}σ`)),
        metricBar(entry.z),
      );
    }
    const numbers = metricNumbers(entry.metrics);
    if (numbers) rows.push(el("p", { class: "metric-numbers" }, numbers));
    return rows.length ? el("div", { class: "card-metrics" }, ...rows) : null;
  }

  renderTabs(country) {
    this.tabButtons = country.entries.map((entry, i) =>
      el("button", { class: "tab", type: "button", "data-index": i, "data-empty": !entry.metrics },
        this.placeLabels.get(entry.place) ?? entry.place),
    );
    this.tabs.replaceChildren(...this.tabButtons);
  }

  // ---- Navigation ----------------------------------------------------------

  go(index, smooth = true) {
    const target = Math.max(0, Math.min(this.cards.length - 1, index));
    const card = this.cards[target]?.node;
    if (!card) return;
    const left = card.offsetLeft - (this.track.clientWidth - card.offsetWidth) / 2;
    const animate = smooth && !prefersReducedMotion;
    this.targetIndex = animate ? target : null;
    this.track.scrollTo({ left, behavior: animate ? "smooth" : "instant" });
    this.setIndex(target);
    this.scheduleFocusUpdate();
    // Browsers without `scrollend` (older Safari) get a timer instead. Elsewhere a timer could
    // fire mid-scroll on a slow device and briefly select the wrong card.
    if (animate && !SUPPORTS_SCROLLEND) setTimeout(() => this.finishScroll(), 1000);
  }

  setIndex(index) {
    this.index = index;
    this.tabButtons.forEach((tab, i) => tab.setAttribute("aria-current", String(i === index)));
    this.centerTab(this.tabButtons[index]);
    this.prevButton.disabled = index <= 0;
    this.nextButton.disabled = index >= this.cards.length - 1;
  }

  // On narrow screens the tab strip overflows: keep the active tab in its middle. This scrolls
  // only the strip, unlike scrollIntoView, which can also scroll the containers around it.
  centerTab(tab) {
    if (!tab || this.tabs.scrollWidth <= this.tabs.clientWidth) return;
    const left = tab.offsetLeft - (this.tabs.clientWidth - tab.offsetWidth) / 2;
    this.tabs.scrollTo({ left, behavior: prefersReducedMotion ? "instant" : "smooth" });
  }

  finishScroll() {
    this.targetIndex = null;
    this.updateFocus();
  }

  scheduleFocusUpdate() {
    if (!this.frame) this.frame = requestAnimationFrame(() => this.updateFocus());
  }

  // Cards scale and fade with their distance from the center, continuously while scrolling.
  updateFocus() {
    this.frame = 0;
    const middle = this.track.scrollLeft + this.track.clientWidth / 2;
    let nearest = 0;
    let nearestDistance = Infinity;
    this.cards.forEach(({ node }, i) => {
      const distance = Math.abs(node.offsetLeft + node.offsetWidth / 2 - middle) / node.offsetWidth;
      node.style.setProperty("--focus", Math.max(0, 1 - distance).toFixed(3));
      node.classList.toggle("is-active", distance < 0.5);
      if (distance < nearestDistance) [nearest, nearestDistance] = [i, distance];
    });
    if (this.targetIndex === null && nearest !== this.index) this.setIndex(nearest);
  }

  handleClick(e) {
    const button = e.target.closest("button");
    if (button) {
      const { action, index } = button.dataset;
      if (action === "close") this.onRequestClose();
      else if (action === "prev") this.go(this.index - 1);
      else if (action === "next") this.go(this.index + 1);
      else if (index !== undefined) this.go(Number(index));
      return;
    }
    const card = e.target.closest(".card");
    if (card && !card.classList.contains("is-active")) this.go(this.cards.findIndex((c) => c.node === card));
  }

  handleWheel(e) {
    if (!this.isOpen || e.ctrlKey) return;
    if (Math.abs(e.deltaX) > Math.abs(e.deltaY)) return; // horizontal swipe: native scroll + snap
    e.preventDefault();
    clearTimeout(this.wheelTimer);
    this.wheelTimer = setTimeout(() => (this.wheelLocked = false), WHEEL_QUIET_MS);
    if (this.wheelLocked || Math.abs(e.deltaY) < 2) return;
    this.wheelLocked = true;
    this.go(this.index + Math.sign(e.deltaY));
  }

  handleKey(e) {
    if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.altKey) return;
    const actions = {
      ArrowLeft: () => this.go(this.index - 1),
      ArrowRight: () => this.go(this.index + 1),
      Home: () => this.go(0),
      End: () => this.go(this.cards.length - 1),
      Escape: () => this.onRequestClose(),
    };
    const action = actions[e.key];
    if (!action) return;
    e.preventDefault();
    action();
  }
}

// A z-score drawn from the middle out: left of center is below the average country, right is above.
function metricBar(z) {
  const clamped = Math.max(-METRIC_SPAN, Math.min(METRIC_SPAN, z));
  const half = (Math.abs(clamped) / METRIC_SPAN) * 50;
  return el("div", { class: "metric-bar", "data-sign": clamped < 0 ? "low" : "high" },
    el("span", { style: `left: ${clamped < 0 ? 50 - half : 50}%; width: ${half}%` }));
}

function metricNumbers(metrics) {
  const parts = [];
  if (metrics.cast_kelvin) parts.push(`${Math.round(metrics.cast_kelvin / 10) * 10} K`);
  if (metrics.haze !== undefined) parts.push(`haze ${metrics.haze.toFixed(2)}`);
  if (metrics.lightness !== undefined) parts.push(`lightness ${Math.round(metrics.lightness)}`);
  if (metrics.colorfulness !== undefined) parts.push(`color ${Math.round(metrics.colorfulness)}`);
  return parts.join(" · ");
}

const totalImages = (country) => country.entries.reduce((sum, e) => sum + e.n_images, 0);
