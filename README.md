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

## Image backend: Replicate

Generation runs on [Replicate](https://replicate.com). `generate` posts to
`/v1/models/<owner>/<model>/predictions` with a `Prefer: wait` header, so a fast model usually answers
on the first request and never needs polling. Replicate allows 600 prediction creations per minute;
`requests_per_minute` throttles below that.

> **The API token decides which account pays.** Create it while switched to the organization that funds
> the work (account menu → the organization → **API tokens**). A token made on a personal account bills
> that person, not the organization.

| Model | Per image | Notes |
|---|---:|---|
| `black-forest-labs/flux-schnell` | $0.003 | 1-4 steps, fastest and cheapest; the default here |
| `black-forest-labs/flux-dev` | $0.025 | slower, usually follows the prompt more closely |
| `black-forest-labs/flux-1.1-pro` | $0.04 | best of the FLUX line |
| `recraft-ai/recraft-v3` | $0.04 | |
| `ideogram-ai/ideogram-v3-quality` | $0.09 | |

Prices from [replicate.com/pricing](https://replicate.com/pricing) — check it before you budget, and
set `price_per_image_usd` to match the model you pick.

Every Replicate model has its own input schema, so a model's inputs live in `[generation.input]` in
`config.toml` instead of in the code, and `count_param` names the input that asks for several images in
one prediction (`num_outputs` for FLUX). Read a model's schema at
`https://replicate.com/<owner>/<model>/api/schema` whenever you change models. Whatever the model
returns is still saved at exactly `generation.size`, so composites line up across models.

Setting `provider = "openai"` uses any OpenAI-compatible `/images/generations` endpoint instead
(`base_url`, `api_key_env`, `model`, `quality`).

## Scale and budget

197 countries × 8 place types = **1,576 prompts**. Set `generation.budget_usd` (or pass `--budget`) and
`generate` splits the budget evenly: every prompt gets the same number of images, as many as the budget
buys, so every country and place gets a composite and all composites are built from equal samples.
Images per prompt for all 1,576 prompts:

| Budget | $0.003/image | $0.01/image | $0.04/image | $0.065/image |
|---:|---:|---:|---:|---:|
| $250 | 52 | 15 | 3 | 2 |
| $1,000 | 211 | 63 | 15 | 9 |
| $2,500 | 528 | 158 | 39 | 24 |
| $5,000 | 1,000 (cap) | 317 | 79 | 48 |

```bash
# What would $1,000 buy at the configured price, and at the other candidate prices?
python -m blurred_lens.generate --dry-run --budget 1000 --prices 0.003,0.01,0.04,0.065
```

- **The budget is a total for the run** and counts images already on disk, so raising it later and
  re-running tops every prompt up to a new, higher count. Nothing is spent beyond it.
- **Too small a budget is refused:** if it buys fewer than `min_images_per_prompt` (default 20) per
  prompt, `generate` says what that minimum would cost. Narrow the run (`--places`), pick a cheaper
  model, or lower the minimum.
- **How many images are enough?** The mean image changes less as N grows (per-pixel standard error
  shrinks as 1/√N), and a fixed camera position (see [Data](#data)) lowers the spread between images, so
  fewer are needed. Run a pilot, check how fast composites settle, and set the minimum from that.

## Setup

```bash
uv venv .venv && source .venv/bin/activate
uv pip install -r requirements.txt
cp .env.example .env    # then paste your Replicate token into REPLICATE_API_TOKEN
```

Then pick a model in `config.toml` — see [Image backend](#image-backend-replicate).

## Usage

```bash
# What would a run do? Prompt count, images, requests, cost, time, disk.
python -m blurred_lens.generate --dry-run

# Pilot: 3 countries × 2 places × 5 images
python -m blurred_lens.generate --countries FRA,NGA,JPN --places city,farm --n 5

# Budgeted run: $1,000 split evenly over every prompt (needs generation.price_per_image_usd)
python -m blurred_lens.generate --budget 1000

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

**`data/places.json`**: the `{place}` and `{view}` slots. Each entry has an `id` (folder name), a
`label` (display), a `phrase` with its article (*a city*, *a rural area*), and a `view` that fixes the
camera position for that kind of place (*taken at eye level from the middle of a street, looking
straight down the street*). Every place added means 197 more prompts.

The view is what makes one prompt's images comparable pixel by pixel. With the camera in the same
place, the road, the horizon and the buildings land in about the same part of every frame, so the
composite shows what the model puts there rather than a blur of different framings. The views pin
down geometry only (eye level, where the camera stands, where it looks); time of day, weather, people
and buildings are left to the model. This is a research decision too: the model no longer chooses the
framing, only what fills it.

Some combinations have no real-world referent (*a farm in Vatican City*, *a village in Singapore*).
What the model does with them is itself a finding.

## Output layout

```
outputs/<run_name>/                      # gitignored; one folder per model/prompt setup
  images/<ISO3>/<place>/0001.jpg …       # generated images
  images/<ISO3>/<place>/metadata.jsonl   # one line per image: prompt, model, revised_prompt, sizes, time
  failures.jsonl                         # errors and content-policy refusals
  predictions.jsonl                      # one line per API call: model version, prediction id, timing
  composites/<ISO3>/<place>_mean.png     # and <place>_median.png
  composites/index.json                  # how many images went into each composite
web/data/                                # gitignored; rebuilt by export_site
```

`predictions.jsonl` is deliberately separate from the image metadata: it describes the API call -- which
model version answered, which prediction id, how long it ran -- rather than the picture, so provenance
questions can be answered without reopening every image's record.

`revised_prompt` is kept because some models (e.g. DALL·E 3) rewrite the prompt before drawing, and that
rewrite is part of how the model sees a place. Refusals are logged instead of retried forever: which
prompts get refused is data too. `returned_size` records the size the model actually sent back: every
image is saved at `generation.size`, and anything else is center-cropped and resized first, so a model
that quietly ignores the requested size shows up in the metadata instead of in the composites.

## Design notes

- **Breadth-first:** requests go out as image 1 of every prompt, then image 2, and so on. If a run stops
  early (budget, rate limit, Ctrl+C), every prompt has about the same number of images, so partial
  results are still comparable.
- **One size, one view:** every image is saved at exactly `generation.size`, and each place fixes the
  camera (`view` in `data/places.json`), so one prompt's images line up when they are averaged.
- **The budget sets the sample size:** `--budget` (or `generation.budget_usd`) decides how many images
  each prompt gets, not the other way round, and every prompt gets the same number, so coverage never
  depends on where a run happened to stop.
- **Resumable:** existing images are never regenerated. Re-run the same command to continue.
- **Runs never mix:** change `generation.run_name` whenever you change the model, template or size.
- **Mean vs. median:** the mean is the literal average (ghostly and blurred); the median is often sharper
  and less swayed by outliers. Both are built and the site shows both.
- **Memory:** `composite` holds one prompt's images in memory at `composite.width` px (512 px ×
  1,000 images ≈ 0.8 GB, about twice that while computing the median).

## Roadmap

- [x] Scaffold: data files, config, generate / composite / export pipeline, map skeleton, tests
- [x] Generation revised: one size and one camera view per prompt, budget-driven sample counts
- [ ] Settle the image size and aspect ratio (see the open question in `config.toml`)
- [ ] Choose an image backend (see above) and run a pilot
- [ ] Choose images-per-prompt from a convergence check on the pilot
- [ ] Full generation run
- [x] Website: 3D globe with hover glow, full-screen gallery, search, deep links
- [ ] Host the site (e.g. GitHub Pages); add comparisons across places and regions
- [ ] XAI analysis: region-level composites, "most typical" images in embedding space, attention maps
      with an open model
