# Blurred Lens

How does an AI image model picture *a city in Nigeria*, *a farm in France*, or *a house in Japan*?
Blurred Lens sends the same simple prompt for every country × place pair, generates many images per
prompt, and measures every one of them: how warm the color is, how hazy, how dark, how vivid. An
interactive 3D globe lets people click a country and see how the model's pictures of it compare with
every other country's, next to sample images and the exact prompts behind them.

The question is the one film critics ask about the sepia "Mexico filter": does the model reach for
warmer, dustier, darker color when the country is poorer?

Class project for AIPI 590 (Explainable AI), Duke University.

## Pipeline

```
data/countries.json ─┐
data/places.json ────┼─► generate ──► outputs/<run>-<condition>/images/<ISO3>/<place>/0001.jpg …
config.toml ─────────┘                               │
                                                     ▼
                                    analyze ──► outputs/<run>/analysis/<ISO3>/<place>.json
                                                     │
                                     report ──► outputs/<run>/analysis/report.json
                                                     │
                                                     ▼
                                export_site ──► web/data/manifest.json + images ──► web/ (globe)
```

| Step | Command | What it does |
|---|---|---|
| 1. Generate | `python -m blurred_lens.generate` | Sends every prompt to an image API. One condition at a time, resumable, breadth-first, seeded, logs metadata. |
| 2. Measure | `python -m blurred_lens.analyze` | Measures color, tone and haze on every image; summarizes each prompt. |
| 3. Compare | `python -m blurred_lens.report` | Ranks countries within each place, and tests the ranking against region and income. |
| 4. Export | `python -m blurred_lens.export_site` | Copies sample thumbnails, writes `web/data/manifest.json` (every prompt, measured or not). |
| 5. View | `python -m http.server --directory web 8000` | The interactive globe at http://localhost:8000 |

## Conditions

A run asks one question, and a **condition** is the sentence it asks it with. The conditions live in
`[prompts.conditions]` in `config.toml`, `generate --condition <name>` picks one, and each writes to
its own folder — `outputs/<run_name>-<condition>/` — so two different sentences can never be averaged
into one measurement. Everything downstream takes that folder with `--run`.

| Condition | Prompt | What it is for |
|---|---|---|
| `free` | *A photograph of {place} in {country}, {view}.* | what the model does when only the country, the place and the camera are fixed |
| `noon` | …*, at noon under a clear sky with the sun high overhead.* | the light control |
| `baseline` | *A photograph of {place}, {view}.* | the model's default picture of a place, with no country at all |
| `baseline_noon` | the baseline, light-controlled | a default to compare light-controlled countries with |

**The light control is the one that turns a number into a claim.** The free prompt fixes the camera
but not the hour, so a country that measures warm may simply be one the model chose to draw at golden
hour — a scene choice, not a grade. `noon` pins the hour, the sky and the sun's height and *names no
color at all*, deliberately: an instruction like "neutral light" would control the grade as well as
the scene, and a warmth gap that vanished under it would prove nothing. Run both, and a gap that
survives `noon` is a cast laid over the frame rather than a time of day.

**The baseline says what "warm" is warm against.** Ranking countries against each other says who is
warmest, not whether the model is doing anything unusual to any of them. The no-country prompt gives
the model's own default for a city, a village, a house, so each country can be read as a deviation
from that default. It has no country dimension: one prompt per place, filed under `_none`, which is
not an ISO code, so the baseline never enters the country rankings or the globe. `report` has nothing
to rank in a baseline run and says so; its numbers are in `analysis/_none/<place>.json`.

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
returns is still saved at exactly `generation.size`, so images line up across models.

### Making a run repeatable

- **A seed per image.** Image *i* of every prompt is generated with `generation.seed_base + i`, and the
  seed is written into `metadata.jsonl`, so any single image can be made again. The seed depends on
  the image number alone — not on the country, the place or the condition — so image 7 of Norway's
  city, of Nigeria's city and of the no-country baseline all start from the same noise, and the
  sentence is the only thing that differs between them. Seeding needs `images_per_request = 1`:
  a model handed one seed for a batch of four picks the other three itself, and the seed recorded
  would not be one that reproduces the image. `generate` refuses the combination rather than logging
  a seed it cannot stand behind.
- **A pinned model version.** `generation.model_version` is the version every image of a run must come
  from. Replicate reports the version that answered each prediction, and a mismatch stops the run: a
  model updated half way through would change what the numbers mean without changing anything visible
  on disk. Leave it empty and the first version seen becomes the pin for the rest of that run. Read
  the current one at `https://replicate.com/<owner>/<model>/api`, or
  `GET /v1/models/<owner>/<model>`.

Setting `provider = "openai"` uses any OpenAI-compatible `/images/generations` endpoint instead
(`base_url`, `api_key_env`, `model`, `quality`).

## Scale and budget

**The budget is per run, and a condition is a run.** Set `generation.budget_usd` (or pass `--budget`)
and `generate` splits it evenly: every prompt gets the same number of images, as many as the budget
buys, so every country and place is measured from the same sample size. Generating the same scope
under two conditions costs two budgets.

Phase 2 is 48 countries × 3 places = **144 prompts** per country condition, plus 3 for each baseline
(the baseline has no country dimension). At `$0.003`/image:

| Images per prompt | `free` | `noon` | both baselines | total |
|---:|---:|---:|---:|---:|
| 50 | $21.60 | $21.60 | $0.90 | **$44.10** |
| 100 | $43.20 | $43.20 | $1.80 | **$88.20** |
| 200 | $86.40 | $86.40 | $3.60 | **$176.40** |

The full scope is 197 countries × 8 place types = **1,576 prompts**. Images per prompt for all 1,576,
for one condition:

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
- **How many images are enough?** Enough that the noise on one country's mean is small against the
  spread *between* countries — that ratio, not the images themselves, is what the comparison rests on.
  `report` prints both numbers for every place:

  ```
  How much of this is noise?
    city       countries differ by sd 0.412; a single country's mean is measured to ±0.137
  ```

  A country's mean is measured to `sd/√n`, so quadrupling the images halves that `±`. Run a pilot,
  read those two numbers, and pick the smallest *n* that puts the error well inside the spread —
  then spend what is left on more countries, which are the unit of the statistical test.

## Setup

```bash
uv venv .venv && source .venv/bin/activate
uv pip install -r requirements.txt
cp .env.example .env    # then paste your Replicate token into REPLICATE_API_TOKEN
```

Then pick a model in `config.toml` — see [Image backend](#image-backend-replicate).

## Usage

```bash
# What would a run do? Condition, prompt count, images, requests, cost, time, disk.
python -m blurred_lens.generate --dry-run
python -m blurred_lens.generate --dry-run --condition noon

# Pilot: 3 countries × 2 places × 5 images
python -m blurred_lens.generate --countries FRA,NGA,JPN --places city,farm --n 5

# Budgeted run: $1,000 split evenly over every prompt (needs generation.price_per_image_usd)
python -m blurred_lens.generate --budget 1000

# The full matrix: each condition into its own folder. Asks for confirmation;
# Ctrl+C stops cleanly; re-run the same command to resume.
python -m blurred_lens.generate --condition free            # -> outputs/phase2-free
python -m blurred_lens.generate --condition noon            # -> outputs/phase2-noon
python -m blurred_lens.generate --condition baseline        # -> outputs/phase2-baseline
python -m blurred_lens.generate --condition baseline_noon   # -> outputs/phase2-baseline-noon

# Everything after generation takes the run folder, one condition at a time.
python -m blurred_lens.analyze --run phase2-free --min-images 5   # default: prompts with all images
python -m blurred_lens.report  --run phase2-free                  # --metric haze, lightness, ...
python -m blurred_lens.export_site --run phase2-free
python -m http.server --directory web 8000

python -m pytest
```

## Website

`web/` is a static site with no build step. Serve it with any static server (browsers won't load ES
modules from `file://`), e.g. `python -m http.server --directory web 8000`.

- **Globe:** drag to rotate (with inertia), scroll or pinch to zoom; it turns slowly when idle. Hovering
  a country lifts it with a soft glow; countries whose images have been measured are tinted.
- **Gallery:** clicking a country flies the camera there and opens a full-screen gallery with one card per
  place, each showing sample images and how that country compares with the rest on the headline
  measurement. Swipe, scroll, press ← → or pick a tab; Esc or the browser's back button returns to the
  globe. Places with nothing generated yet say so.
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
| `latitude` | `38.0` | controlling for how far from the equator a country sits |
| `un_status` | `member`, `observer`, `non-member` | filtering |

`prompt_name` exists because grammar and ambiguity change what the model draws:

- Articles where English needs them: *the Netherlands*, *the Philippines*, *the Gambia*, …
- **Georgia** becomes *the country of Georgia*; otherwise the model may draw the US state.
- **Türkiye** rather than *Turkey* (the bird), and **Côte d'Ivoire** / **Cabo Verde** rather than
  *Ivory Coast* / *Cape Verde*, so English words like "coast" and "cape" don't leak into the image.
- The two Congos are spelled out in full.

These are research decisions: review them and note your choices in the write-up.

`latitude` is a country's representative centre, from the public
[Google canonical country centroids](https://developers.google.com/public-data/docs/canonical/countries_csv)
matched on `iso_a2` (South Sudan postdates that table and is filled in by hand). It is there because
latitude is the rival explanation for everything this project measures: near the equator the light
really is harsher and warmer. One degree of precision is plenty — what matters is *distance from the
equator*, as a covariate the analysis can hold constant.

**Which countries a run covers** is `prompts.countries` in `config.toml`, and for phase 2 that list is
built for the income question rather than hand-picked. Across the 195 countries with a World Bank
income group the rich ones sit far from the equator and the poor ones near it — mean |latitude| 37°
for high income against 14° for low — so "warmer because poorer" and "warmer because nearer the
equator" would be the same sentence. The phase-2 list is 48 countries, 12 per income group, chosen to
break that tie: hot high-income countries (Singapore, Panama, Costa Rica, Trinidad and Tobago,
Barbados, the UAE, Saudi Arabia) against cool or highland low- and lower-middle-income ones (North
Korea, Syria, Afghanistan, Mongolia, Kyrgyzstan, Uzbekistan, Nepal, Bolivia, Lesotho, the Ethiopian
and Rwandan highlands). That leaves the groups nearly level — mean |latitude| 25°, 23°, 23°, 19° from
high income to low, a 6° spread where the world's is 23° — and puts all four income groups in every
latitude band, so latitude can be controlled for instead of merely hoped about. `tests/test_data.py`
holds the list to that standard, so editing it fails loudly rather than quietly re-introducing the
confound.

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
outputs/<run_name>-<condition>/          # gitignored; one folder per model/prompt setup
  images/<ISO3>/<place>/0001.jpg …       # generated images (<ISO3> is _none for a baseline run)
  images/<ISO3>/<place>/metadata.jsonl   # one line per image: prompt, condition, seed, model,
                                         #   revised_prompt, sizes, time
  failures.jsonl                         # errors and content-policy refusals
  predictions.jsonl                      # one line per API call: model version, prediction id, timing
  analysis/<ISO3>/<place>.json           # every image's measurements, and a summary of each metric
  analysis/index.json                    # what was measured, what was left out and why, and the settings
  analysis/report.json                   # the comparison across countries (written by report)
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

## What is measured

Every image is measured at `analysis.width`, and each prompt's numbers come with the standard error of
their mean, so a gap between two countries can be weighed against the noise in the sample.

| Measurement | What it catches |
|---|---|
| `cast_a`, `cast_b`, `cast_kelvin` | the color cast lying over the picture, estimated with shades-of-gray (Finlayson and Trezzi, 2004); kelvin says the same thing in film's own units, where lower is warmer |
| `midtone_b`, `shadow_b`, `highlight_b`, `sky_b` | where that cast falls. A grade laid over the whole frame moves all of them together; a golden sky moves mostly the sky |
| `warm_split` | warm highlights against cool shadows, the teal-and-orange look. Near zero means one flat cast instead |
| `chroma`, `colorfulness` | saturation, the other half of "vibrant" stereotypes (Hasler and Suesstrunk, 2003) |
| `lightness`, `contrast` | how dark, and how flat |
| `haze` | dust and smog, via the dark channel prior (He, Sun and Tang, 2009) |
| `amber_share`, `cool_share`, `green_share` | how much of the frame sits in each hue band |
| `edge_density` | how busy the frame is |

The cast estimate deliberately cannot adapt to the picture. An earlier version measured it from "the
least colorful pixels", which simply followed the grade: warming an image made its blue sky the most
neutral thing in frame, so the measurement came back *cooler*. `tests/test_metrics.py` guards that.

No single image can prove a grade was applied -- a sunset really in frame is warm content, and looks
much like a warm filter. What carries the argument is that the prompt, the camera view, the model and
the size are all fixed, so between two countries' pictures of the same place, the country name is the
only thing that changed.

## Design notes

- **Breadth-first:** requests go out as image 1 of every prompt, then image 2, and so on. If a run stops
  early (budget, rate limit, Ctrl+C), every prompt has about the same number of images, so partial
  results are still comparable.
- **One size, one view:** every image is saved at exactly `generation.size`, and each place fixes the
  camera (`view` in `data/places.json`), so two countries' pictures of the same place differ only
  because the country name differs.
- **The budget sets the sample size:** `--budget` (or `generation.budget_usd`) decides how many images
  each prompt gets, not the other way round, and every prompt gets the same number, so coverage never
  depends on where a run happened to stop.
- **Resumable:** existing images are never regenerated. Re-run the same command to continue.
- **Runs never mix:** the condition is part of the run folder, so changing the sentence cannot top up
  a folder generated from another one. Change `generation.run_name` yourself whenever you change the
  model or the size, and `generation.model_version` makes a model that changes under you fatal
  rather than invisible.
- **The same noise for every country:** image *i* of every prompt uses seed `seed_base + i`, so the
  country name is the only thing that differs between Norway's image 7 and Nigeria's — in the
  sampling as well as in the sentence.
- **The light is controlled separately, not described away:** `noon` pins the hour, the sky and the
  sun's height and names no color, so what survives it is a grade rather than a scene choice.
- **There is a zero to measure from:** the no-country baseline gives the model's own default picture
  of a place, so a country can be read as a deviation from that default and not only from the average
  country. It lives under `_none`, which is not an ISO code, so it never joins the rankings.
- **Countries are compared within a place:** a city is only ever ranked against other countries'
  cities. Place types differ in color for reasons that have nothing to do with the country, and
  mixing them would hand back that difference as a finding.
- **The country is the unit, not the image:** 500 images of one prompt say precisely what that one
  answer looks like, not that the answer is common, so the group tests shuffle country labels rather
  than image labels, and `report` prints how many comparisons it made.
- **Blank frames are left out:** an image whose pixels barely vary (`analysis.min_spread`) is usually a
  model handing back a black or single-color frame instead of refusing, and its color is not a color
  the model chose for that country. It is skipped and recorded in `analysis/index.json`.
- **Nothing is measured twice:** a prompt is re-measured only when its images or the measurement
  settings change, and `export_site` re-encodes a web image only when its source or the export settings
  change, deleting any image the manifest no longer names. `--force` measures again regardless.
- **Memory:** `analyze` holds one image at a time, so a run of any size measures in a few hundred MB.

## Roadmap

- [x] Scaffold: data files, config, generate / measure / compare / export pipeline, tests
- [x] Image backend (Replicate), budgeting, and measurement of every image
- [x] Generation built for the question: a light control, a no-country baseline, a 48-country list
      that separates income from latitude, per-image seeds and a pinned model version
- [ ] Pilot: a few contrasting countries at ~50 images, then set the sample size from the noise line
- [ ] Run the phase-2 matrix (`free`, `noon`, and both baselines) at the size the pilot picks
- [x] Website: 3D globe with hover glow, full-screen gallery, search, deep links
- [ ] Tint the globe by the headline measurement once there is real data to scale it against
- [ ] Report countries as deviations from the baseline run, and control for latitude, in `report`
- [ ] Write up: which countries the model grades warmest, whether that survives the light control,
      and whether it tracks income once latitude is held constant
- [ ] Widen beyond color: what the model puts in the frame, not only how it lights it
