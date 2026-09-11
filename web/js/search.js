// Country search: a keyboard-friendly combobox matching names (accent-insensitive) and ISO codes.

import { el, isEditable } from "./util.js";

const MAX_RESULTS = 7;
const normalize = (text) => text.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase().trim();

export function createSearch(root, countries, { onSelect }) {
  const input = root.querySelector("input");
  const list = root.querySelector('[role="listbox"]');
  const index = countries.map((country) => ({ country, name: normalize(country.name), iso3: country.iso3.toLowerCase() }));
  let results = [];
  let active = -1;

  function rank(query) {
    if (!query) return [];
    const scored = [];
    for (const item of index) {
      let score = -1;
      if (item.iso3 === query) score = 0;
      else if (item.name.startsWith(query)) score = 1;
      else if (item.name.split(/[\s'-]+/).some((word) => word.startsWith(query))) score = 2;
      else if (item.name.includes(query)) score = 3;
      if (score >= 0) scored.push({ score, item });
    }
    scored.sort((a, b) => a.score - b.score || a.item.name.localeCompare(b.item.name));
    return scored.slice(0, MAX_RESULTS).map(({ item }) => item.country);
  }

  function render() {
    list.replaceChildren(
      ...results.map((country, i) =>
        el("li", { id: `search-${country.iso3}`, class: "search-option", role: "option", "aria-selected": String(i === active), "data-iso3": country.iso3 },
          el("span", { class: `dot${country.done ? " is-on" : ""}`, "aria-hidden": "true" }),
          el("span", { class: "search-option-name" }, country.name),
          el("span", { class: "search-option-meta" }, country.subregion),
        ),
      ),
    );
    const open = results.length > 0;
    list.hidden = !open;
    input.setAttribute("aria-expanded", String(open));
    if (active >= 0) input.setAttribute("aria-activedescendant", `search-${results[active].iso3}`);
    else input.removeAttribute("aria-activedescendant");
    list.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: "nearest" });
  }

  function reset() {
    results = [];
    active = -1;
    render();
  }

  function choose(country) {
    input.value = "";
    reset();
    input.blur();
    onSelect(country);
  }

  input.addEventListener("input", () => {
    results = rank(normalize(input.value));
    active = results.length ? 0 : -1;
    render();
  });

  input.addEventListener("keydown", (e) => {
    if ((e.key === "ArrowDown" || e.key === "ArrowUp") && results.length) {
      e.preventDefault();
      active = (active + (e.key === "ArrowDown" ? 1 : -1) + results.length) % results.length;
      render();
    } else if (e.key === "Enter" && results[active]) {
      e.preventDefault();
      choose(results[active]);
    } else if (e.key === "Escape") {
      input.value = "";
      reset();
      input.blur();
    }
  });

  // pointerdown fires before the input loses focus, so the list is still there to click.
  list.addEventListener("pointerdown", (e) => {
    const option = e.target.closest("[data-iso3]");
    if (!option) return;
    e.preventDefault();
    choose(countries.find((c) => c.iso3 === option.dataset.iso3));
  });

  input.addEventListener("blur", reset);

  // "/" jumps to search from anywhere, like on GitHub or YouTube.
  document.addEventListener("keydown", (e) => {
    if (e.key === "/" && !isEditable(e.target) && !e.metaKey && !e.ctrlKey) {
      e.preventDefault();
      input.focus();
    }
  });
}
