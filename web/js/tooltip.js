// Glassy label that follows the pointer while a country is hovered.

const OFFSET = 18;

export class Tooltip {
  constructor(root) {
    this.root = root;
    this.name = root.querySelector(".tooltip-name");
    this.meta = root.querySelector(".tooltip-meta");
    this.x = 0;
    this.y = 0;
    this.frame = 0;
    addEventListener("pointermove", (e) => this.follow(e), { passive: true });
  }

  show(country) {
    if (!country) {
      this.hide();
      return;
    }
    this.name.textContent = country.name;
    this.meta.textContent = country.done
      ? `${country.subregion} · ${country.done} of ${country.entries.length} places`
      : `${country.subregion} · no images yet`;
    this.root.classList.add("is-visible");
    this.place();
  }

  hide() {
    this.root.classList.remove("is-visible");
  }

  follow(event) {
    this.x = event.clientX;
    this.y = event.clientY;
    if (!this.frame) this.frame = requestAnimationFrame(() => this.place());
  }

  place() {
    this.frame = 0;
    const { offsetWidth: w, offsetHeight: h } = this.root;
    // Flip to the other side of the pointer near the window edges.
    const x = this.x + OFFSET + w > innerWidth ? this.x - OFFSET - w : this.x + OFFSET;
    const y = this.y + OFFSET + h > innerHeight ? this.y - OFFSET - h : this.y + OFFSET;
    this.root.style.transform = `translate3d(${x}px, ${y}px, 0)`;
  }
}
