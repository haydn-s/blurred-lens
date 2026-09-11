// About page: renders project_description.md, so the text can be edited without touching HTML.

import { marked } from "marked";

const SOURCE = "project_description.md";
const article = document.querySelector("#about-content");

try {
  const res = await fetch(SOURCE, { cache: "no-cache" }); // pick up edits on the next reload
  if (!res.ok) throw new Error(`${SOURCE}: HTTP ${res.status}`);
  // The Markdown is our own file, so the HTML it produces is trusted and left unsanitized.
  article.innerHTML = marked.parse(await res.text());
  for (const link of article.querySelectorAll('a[href^="http"]')) {
    link.target = "_blank";
    link.rel = "noopener noreferrer";
  }
} catch (err) {
  console.error(err);
  const message = document.createElement("p");
  message.className = "about-status";
  message.innerHTML =
    `Couldn’t load <code>${SOURCE}</code>. Serve the site over HTTP (for example ` +
    "<code>python -m http.server --directory web 8000</code>) instead of opening the file directly.";
  article.replaceChildren(message);
} finally {
  article.removeAttribute("aria-busy");
}
