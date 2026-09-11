# Blurred Lens

How does an AI image model picture *a city in Nigeria*, *a farm in France*, or *a house in Japan*?
Blurred Lens sends the same simple prompt for every country × place pair, generates many images per
prompt, and averages them into a single composite: the model's "blurred lens" on that place. An
interactive 3D globe lets people click a country and browse its composites, sample images, and the
exact prompts behind them.

Class project for AIPI 590 (Explainable AI), Duke University.

## Pipeline

```
data/countries.json ─┐
data/places.json ────┼─► generate ──► outputs/<run>/images/<ISO3>/<place>/0001.jpg …
config.toml ─────────┘                               │
                                                     ▼
                                  composite ──► outputs/<run>/composites/<ISO3>/<place>_mean.png
                                                     │
                                                     ▼
                                export_site ──► web/data/manifest.json + images ──► web/ (globe)
```

| Step | Command | What it does |
|---|---|---|
| 1. Generate | `python -m blurred_lens.generate` | Sends every prompt to an image API. Resumable, breadth-first, logs metadata. |
| 2. Composite | `python -m blurred_lens.composite` | Pixel-wise mean and median of each prompt's images. |
| 3. Export | `python -m blurred_lens.export_site` | Copies composites and thumbnails, writes `web/data/manifest.json` (every prompt, generated or not). |
| 4. View | `python -m http.server --directory web 8000` | The interactive globe at http://localhost:8000 |

## ⚠️ Before generating: choose an image backend

As of 2026-09-10 the **Duke AI Gateway** (`https://litellm.oit.duke.edu/v1`) serves 36 models (chat,
embeddings, rerank, speech-to-text) but **no image-generation models**, and the key this project was
set up with is capped at **$1/day** and **20 requests/minute**. `generate` has nothing to call until
`generation.model` in `config.toml` names a working image model. Options:

1. **Ask Duke OIT or the course staff** to enable an image model on the gateway, and whether a course
   fund code can lift the daily budget (the gateway supports fund codes for higher limits).
2. **Use a paid provider** with an OpenAI-compatible images API (e.g. OpenAI's `gpt-image-*` models):
   set `base_url`, `api_key_env`, `model` and `price_per_image_usd` in `config.toml`.
3. **Run an open-weights model** (e.g. FLUX.1-schnell or SDXL-Turbo with Hugging Face `diffusers`) on a
   GPU such as the Duke Compute Cluster. No per-image cost or rate limit, and white-box access to the
   model, which enables XAI methods an API can't (e.g. cross-attention maps showing which pixels respond
   to the country name). This needs a second backend in `generate.py` (not written yet).

## Scale

197 countries × 8 place types = **1,576 prompts**. At 1,000 images per prompt that is **1,576,000 images**.

| Images per prompt | Total images | Time at 20 requests/min | Cost at $0.01/image | Cost at $0.04/image |
|---:|---:|---:|---:|---:|
| 10 | 15,760 | 13 hours | $158 | $630 |
| 100 | 157,600 | 5.5 days | $1,576 | $6,304 |
| 1,000 | 1,576,000 | 55 days | $15,760 | $63,040 |

The prices are illustrative. Check your provider's current pricing and set `price_per_image_usd` to get
real estimates from `python -m blurred_lens.generate --dry-run`. On a $1/day budget even 10 images per
prompt would take months. Start with a pilot (a few countries, ~5 images each) and scale up: the mean
image changes less and less as N grows (per-pixel standard error shrinks as 1/√N), so a convergence
check on pilot data can justify a smaller N than 1,000.

## Setup

```bash
uv venv .venv && source .venv/bin/activate
uv pip install -r requirements.txt
cp .env.example .env    # then paste your API key into .env
```

Then set `generation.model` (and the endpoint, if not Duke's) in `config.toml`.

## Usage

```bash
# What would a run do? Prompt count, images, requests, cost, time, disk.
python -m blurred_lens.generate --dry-run

# Pilot: 3 countries × 2 places × 5 images
python -m blurred_lens.generate --countries FRA,NGA,JPN --places city,farm --n 5

# Full run. Asks for confirmation; Ctrl+C stops cleanly; re-run the same command to resume.
python -m blurred_lens.generate

python -m blurred_lens.composite --min-images 5   # default: only prompts that have all their images
python -m blurred_lens.export_site
python -m http.server --directory web 8000

python -m pytest
```

## Website

`web/` is a static site with no build step. Serve it with any static server (browsers won't load ES
modules from `file://`), e.g. `python -m http.server --directory web 8000`.

- **Globe:** drag to rotate (with inertia), scroll or pinch to zoom; it turns slowly when idle. Hovering
  a country lifts it with a soft glow; countries that have composites are tinted.
- **Gallery:** clicking a country flies the camera there and opens a full-screen gallery with one card per
  place. Swipe, scroll, press ← → or pick a tab; switch between **Mean** and **Median**; Esc or the
  browser's back button returns to the globe. Places without composites show as "not generated yet".
- **Search:** press `/` to find any country by name or ISO code, including ones too small to click
  (Tuvalu has no shape on the 1:50m map).
- **About page:** `about.html` displays [`web/project_description.md`](web/project_description.md). Edit that
  Markdown file to change the text; the page picks up changes on reload, with no build step.
- **Footer:** links to the About page and to this repository on GitHub.
- **Deep links:** `index.html#/NGA` opens Nigeria's gallery directly.
- **Debugging:** `index.html?debug` exposes the globe and gallery as `window.blurredLens`.

Libraries come from CDNs through the import map in `web/index.html`: [globe.gl](https://globe.gl)
(bundled by esm.sh), [three.js](https://threejs.org), d3-geo and topojson-client, with country shapes from
[world-atlas](https://github.com/topojson/world-atlas). The import map gives every module the same copy of
three.js, so upgrade those versions together. To host the site (e.g. GitHub Pages), publish `web/`
including `web/data/`, which is gitignored by default. `web/.nojekyll` stops GitHub Pages from converting
`project_description.md` into HTML; the About page needs the raw Markdown.

## Data

**`data/countries.json`**: 197 entries: the 193 UN member states, the 2 UN observer states (Palestine,
Vatican City), plus Taiwan and Kosovo. `un_status` tells them apart; delete entries to change the set.
ISO 3166-1 codes come from the ISO data in [`pycountry`](https://pypi.org/project/pycountry/) (Kosovo,
which has no ISO code, uses the common `XK`/`XKX`). Regions follow the UN M49 scheme.

| Field | Example | Used for |
|---|---|---|
| `name` | `United States` | display |
| `prompt_name` | `the United States` | the `{country}` slot of the prompt |
| `iso_a2`, `iso_a3`, `iso_num` | `US`, `USA`, `840` | folder names (`iso_a3`), map matching (`iso_num`) |
| `region`, `subregion` | `Americas`, `Northern America` | grouping and analysis |
| `un_status` | `member`, `observer`, `non-member` | filtering |

`prompt_name` exists because grammar and ambiguity change what the model draws:

- Articles where English needs them: *the Netherlands*, *the Philippines*, *the Gambia*, …
- **Georgia** becomes *the country of Georgia*; otherwise the model may draw the US state.
- **Türkiye** rather than *Turkey* (the bird), and **Côte d'Ivoire** / **Cabo Verde** rather than
  *Ivory Coast* / *Cape Verde*, so English words like "coast" and "cape" don't leak into the image.
- The two Congos are spelled out in full.

These are research decisions: review them and note your choices in the write-up.

**`data/places.json`**: the `{place}` slot. Each entry has an `id` (folder name), a `label` (display),
and a `phrase` with its article (*a city*, *a rural area*). Every place added means 197 more prompts.

Some combinations have no real-world referent (*a farm in Vatican City*, *a village in Singapore*).
What the model does with them is itself a finding.

## Output layout

```
outputs/<run_name>/                      # gitignored; one folder per model/prompt setup
  images/<ISO3>/<place>/0001.jpg …       # generated images
  images/<ISO3>/<place>/metadata.jsonl   # one line per image: prompt, model, revised_prompt, time
  failures.jsonl                         # errors and content-policy refusals
  composites/<ISO3>/<place>_mean.png     # and <place>_median.png
  composites/index.json                  # how many images went into each composite
web/data/                                # gitignored; rebuilt by export_site
```

`revised_prompt` is kept because some models (e.g. DALL·E 3) rewrite the prompt before drawing, and that
rewrite is part of how the model sees a place. Refusals are logged instead of retried forever: which
prompts get refused is data too.

## Design notes

- **Breadth-first:** requests go out as image 1 of every prompt, then image 2, and so on. If a run stops
  early (budget, rate limit, Ctrl+C), every prompt has about the same number of images, so partial
  results are still comparable.
- **Resumable:** existing images are never regenerated. Re-run the same command to continue.
- **Runs never mix:** change `generation.run_name` whenever you change the model, template or size.
- **Mean vs. median:** the mean is the literal average (ghostly and blurred); the median is often sharper
  and less swayed by outliers. Both are built and the site shows both.
- **Memory:** `composite` holds one prompt's images in memory at `composite.width` px (512 px ×
  1,000 images ≈ 0.8 GB, about twice that while computing the median).

## Roadmap

- [x] Scaffold: data files, config, generate / composite / export pipeline, map skeleton, tests
- [ ] Choose an image backend (see above) and run a pilot
- [ ] Choose images-per-prompt from a convergence check on the pilot
- [ ] Full generation run
- [x] Website: 3D globe with hover glow, full-screen gallery, search, deep links
- [ ] Host the site (e.g. GitHub Pages); add comparisons across places and regions
- [ ] XAI analysis: region-level composites, "most typical" images in embedding space, attention maps
      with an open model
