// Small shared helpers.

export const prefersReducedMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;

export const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

export const clamp = (value, min, max) => Math.min(max, Math.max(min, value));

export const formatCount = (n) => n.toLocaleString("en-US");

export const isEditable = (node) => Boolean(node?.closest?.("input, textarea, select, [contenteditable]"));

// el("p", { class: "hint" }, "text", childNode, ...) -> <p class="hint">text…</p>
export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === false || value == null) continue;
    node.setAttribute(key, value === true ? "" : value);
  }
  node.append(...children.filter((child) => child != null && child !== false));
  return node;
}
