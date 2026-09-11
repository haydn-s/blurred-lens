// Full-screen gallery of one country's composite images: a card per place, scroll-snapped
// horizontally, driven by swipe, wheel, keyboard, arrow buttons or the place tabs.

import { el, formatCount, prefersReducedMotion } from "./util.js";

const CLOSE_MS = 480; // matches --gallery-ms in styles.css
const WHEEL_QUIET_MS = 180; // one wheel/trackpad gesture moves one card
const SUPPORTS_SCROLLEND = "onscrollend" in window;
const METHOD_LABELS = { mean: "Mean", median: "Median" };

export class Gallery {
  constructor(root, { places, onRequestClose }) {
    this.root = root;
    this.placeLabels = new Map(places.map((p) => [p.id, p.label]));
    this.onRequestClose = onRequestClose;
    this.track = root.querySelector(".gallery-track");
    this.tabs = root.querySelector(".gallery-tabs");
    this.title = root.querySelector(".gallery-title");
    this.region = root.querySelector(".gallery-region");
    this.summary = root.querySelector(".gallery-summary");
    this.prevButton = root.querySelector('[data-action="prev"]');
    this.nextButton = root.querySelector('[data-action="next"]');
    this.methodButtons = [...root.querySelectorAll("[data-method]")];

    this.country = null;
    this.method = "mean";
    this.cards = []; // { node, frame, image, count, entry }
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
    this.go(Math.max(0, country.entries.findIndex((e) => e.composites)), false);
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
      let image = null;
      if (entry.composites) {
        image = el("img", { class: "card-image", decoding: "async", draggable: "false" });
        image.addEventListener("load", () => frame.classList.add("is-loaded"));
        frame.append(image);
      } else {
        frame.classList.add("is-empty");
        frame.append(el("span", { class: "card-empty-label" }, "Not generated yet"));
      }
      const count = el("span", { class: "card-count" });
      const sources = entry.samples.map((s) =>
        el("img", { src: `data/${s.image}`, alt: "", loading: "lazy", draggable: "false", title: s.revised_prompt ?? entry.prompt }),
      );
      const node = el("li", { class: "card", style: `--i: ${i}`, "aria-roledescription": "slide", "aria-label": `${label}, ${i + 1} of ${total}` },
        el("figure", { class: "card-figure" },
          frame,
          el("figcaption", { class: "card-caption" },
            el("div", { class: "card-heading" }, el("span", { class: "card-place" }, label), count),
            el("p", { class: "card-prompt" }, `“${entry.prompt}”`),
            sources.length ? el("div", { class: "card-sources", title: "Some of the images behind this composite" }, ...sources) : null,
          ),
        ),
      );
      return { node, frame, image, count, entry };
    });
    this.cards.forEach((card) => this.showMethod(card));
    this.track.replaceChildren(...this.cards.map((card) => card.node));
    this.track.scrollLeft = 0;
  }

  renderTabs(country) {
    this.tabButtons = country.entries.map((entry, i) =>
      el("button", { class: "tab", type: "button", "data-index": i, "data-empty": !entry.composites },
        this.placeLabels.get(entry.place) ?? entry.place),
    );
    this.tabs.replaceChildren(...this.tabButtons);
  }

  showMethod({ frame, image, count, entry }) {
    if (!entry.composites) {
      count.textContent = "Awaiting generation";
      return;
    }
    const label = METHOD_LABELS[this.method];
    count.textContent = `${label} of ${formatCount(entry.n_images)} images`;
    image.alt = `${label} of ${formatCount(entry.n_images)} AI-generated images for “${entry.prompt}”`;
    const src = `data/${entry.composites[this.method]}`;
    if (image.getAttribute("src") !== src) {
      frame.classList.remove("is-loaded");
      image.src = src;
    }
  }

  setMethod(method) {
    if (method === this.method) return;
    this.method = method;
    for (const button of this.methodButtons) button.setAttribute("aria-pressed", String(button.dataset.method === method));
    this.cards.forEach((card) => this.showMethod(card));
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
      const { action, method, index } = button.dataset;
      if (action === "close") this.onRequestClose();
      else if (action === "prev") this.go(this.index - 1);
      else if (action === "next") this.go(this.index + 1);
      else if (method) this.setMethod(method);
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

const totalImages = (country) => country.entries.reduce((sum, e) => sum + e.n_images, 0);
