"""Generate images for every (country, place) prompt through an image-generation API.

    python -m blurred_lens.generate --dry-run              # plan only: counts, cost, time, disk
    python -m blurred_lens.generate --countries FRA,NGA --places city,farm --n 5
    python -m blurred_lens.generate --condition noon       # the light-controlled template
    python -m blurred_lens.generate --budget 1000          # spread $1,000 evenly over every prompt
    python -m blurred_lens.generate                        # everything in config.toml

Resumable: images already on disk are skipped, so re-running continues where the last
run stopped. Requests go out breadth-first (image 1 of every prompt, then image 2, ...),
so a run cut short by a budget or rate limit leaves every prompt with about the same
number of images instead of a few finished prompts and many empty ones.

A budget (generation.budget_usd, or --budget) decides how many images each prompt gets:
it is split evenly, so every country and place is measured from the same sample size.
Every image is saved at exactly generation.size, and each place fixes the camera
position, so one prompt's images differ only because the prompt does.

One run, one sentence. A condition (see [prompts.conditions]) is a prompt template, and
each one writes to outputs/<run_name>-<condition>/, so the light-controlled images, the
free ones and the no-country baseline can never be averaged together by accident. The
later steps take that folder with --run:

    python -m blurred_lens.generate --condition noon
    python -m blurred_lens.analyze --run phase2-noon
    python -m blurred_lens.report  --run phase2-noon

Two things make a run repeatable: image i of every prompt is generated with the seed
generation.seed_base + i, recorded in metadata.jsonl, and generation.model_version says
which model version this run's numbers came from -- if Replicate ever answers with
another one, the run stops rather than quietly measuring two models at once.
"""

import argparse
import base64
import io
import itertools
import json
import os
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import openai
from dotenv import load_dotenv
from PIL import Image, ImageOps
from tqdm import tqdm

from .config import IMAGE_RE, ROOT, load_config, run_dir
from .prompts import NO_COUNTRY, Prompt, load_prompts, template_for

EXTENSIONS = {"jpeg": "jpg", "webp": "webp", "png": "png"}
TYPICAL_BYTES = {"jpeg": 250_000, "webp": 150_000, "png": 1_600_000}  # rough size of one 1024x1024 image

MAX_CONSECUTIVE_FAILURES = 10
MAX_REFUSALS_PER_PROMPT = 3  # content-policy refusals before a prompt is skipped for this run
REPLICATE_API = "https://api.replicate.com/v1"
# Replicate sits behind Cloudflare, which rejects urllib's default agent with HTTP 403 (code 1010).
USER_AGENT = "blurred-lens/1.0 (AIPI 590 research project)"
POLL_INTERVAL = 2.0          # seconds between polls while a prediction is still running
POLL_TIMEOUT = 900           # give up on a prediction that never finishes
HTTP_RETRIES = 5             # retries for rate limits, timeouts and server errors
REFUSAL_WORDS = ("nsfw", "safety", "flagged", "sensitive content", "content policy", "moderation")


class FatalError(RuntimeError):
    """An error retrying won't fix: a bad token, no access to the model, a wrong endpoint."""


class Refusal(RuntimeError):
    """A safety filter rejected this prompt: a result worth recording, not an error to retry."""


def looks_like_refusal(text: str) -> bool:
    return any(word in text.lower() for word in REFUSAL_WORDS)


@dataclass
class Job:
    """One API request, filling image numbers `indices` for `prompt`."""

    prompt: Prompt
    indices: list[int]


@dataclass
class Generated:
    """What one API call returned: the images, and what the provider said about the call itself.

    `info` describes the call (which model version answered, how long it took), not the picture, so
    it is logged to predictions.jsonl rather than written into each image's metadata.
    """

    images: list[tuple[bytes, str | None]]  # (image bytes, revised prompt)
    info: dict


def existing_indices(folder: Path) -> set[int]:
    if not folder.is_dir():
        return set()
    return {int(m.group(1)) for f in folder.iterdir() if (m := IMAGE_RE.match(f.name))}


def plan_jobs(prompts: list[Prompt], images_dir: Path, n_per_prompt: int, per_request: int) -> list[Job]:
    """Every request still needed to reach n_per_prompt images for each prompt, breadth-first."""
    queues = []
    for p in prompts:
        have = existing_indices(images_dir / p.iso3 / p.place)
        missing = [i for i in range(1, n_per_prompt + 1) if i not in have]
        queues.append([Job(p, missing[i:i + per_request]) for i in range(0, len(missing), per_request)])
    return [job for round_ in itertools.zip_longest(*queues) for job in round_ if job]


def parse_size(size: str) -> tuple[int, int]:
    """'1024x1024' -> (1024, 1024)."""
    try:
        width, height = (int(v) for v in size.lower().split("x"))
    except ValueError:
        raise ValueError(f"generation.size must look like 1024x1024, not {size!r}") from None
    return width, height


def run_cost(have: list[int], n_per_prompt: int, price: float) -> float:
    """Total cost of filling every prompt to n_per_prompt images, counting the `have` already on disk."""
    return price * sum(max(n_per_prompt, h) for h in have)


def images_within_budget(have: list[int], cap: int, price: float, budget: float) -> int:
    """The most images per prompt, up to `cap`, that a run can reach without costing more than `budget`.

    Every prompt gets the same number, so each country and place gets a composite and the composites
    stay comparable. A larger budget later tops every prompt up to a new, higher number.
    """
    n = 0
    while n < cap and run_cost(have, n + 1, price) <= budget + 1e-9:
        n += 1
    return n


def human_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1000:
            return f"{n:,.0f} {unit}"
        n /= 1000
    return f"{n:,.0f} PB"


def human_minutes(minutes: float) -> str:
    if minutes < 1:
        return f"{minutes * 60:.0f} seconds"
    if minutes < 120:
        return f"{minutes:,.0f} minutes"
    if minutes < 60 * 48:
        return f"{minutes / 60:,.1f} hours"
    return f"{minutes / 1440:,.1f} days"


def print_plan(g: dict, prompts: list[Prompt], jobs: list[Job], n_per_prompt: int, out: Path,
               budget: float, have: list[int], condition: str, template: str) -> None:
    todo = sum(len(j.indices) for j in jobs)
    target = len(prompts) * n_per_prompt
    price = g.get("price_per_image_usd") or 0
    rpm = g.get("requests_per_minute") or 0
    places = {p.place for p in prompts}
    countries = {p.iso3 for p in prompts} - {NO_COUNTRY}
    scope = f"{len(countries)} countries" if countries else "no country"
    total = run_cost(have, n_per_prompt, price)
    version = g.get("model_version") or ""
    seed_base = g.get("seed_base") or 0
    rows = [
        ("Condition", f"{condition}  ·  {template}"),
        ("Output folder", os.path.relpath(out, ROOT)),
        ("Model", f"{g.get('provider') or 'replicate'} · {g['model'] or '(not set)'} · {g['size']}"),
        ("Model version", f"{version[:12]}… (pinned)" if version
         else "not pinned; the first version seen must hold for the whole run"),
        ("Seeds", f"{seed_base + 1}–{seed_base + n_per_prompt} (seed_base + image number), "
                  f"the same for every prompt" if seed_base else "none (the model picks its own)"),
        ("Prompts", f"{len(prompts):,}  ({scope} × {len(places)} places)"),
        *([("Budget", f"${budget:,.2f} buys {n_per_prompt:,} per prompt · run total ${total:,.2f} "
                      f"· ${budget - total:,.2f} left over")] if budget else []),
        ("Target images", f"{target:,}  ({n_per_prompt:,} per prompt)"),
        ("Already on disk", f"{target - todo:,}"),
        ("To generate", f"{todo:,}  in {len(jobs):,} requests"),
        ("Est. cost", f"${todo * price:,.2f}  (@ ${price}/image)" if price
         else "unknown (set generation.price_per_image_usd)"),
        ("Est. time", f"at least {human_minutes(len(jobs) / rpm)}  (@ {rpm} requests/min)" if rpm
         else "unknown (no requests_per_minute limit)"),
        ("Est. disk", f"~{human_bytes(todo * TYPICAL_BYTES[g['save_format']])}  (as {g['save_format']})"),
        ("Example prompt", f'"{prompts[0].text}"' if prompts else "(none)"),
        ("Then measure it", f"python -m blurred_lens.analyze --run {out.name}"),
    ]
    width = max(len(label) for label, _ in rows)
    print("\n".join(f"  {label:<{width}}  {value}" for label, value in rows), flush=True)


class Throttle:
    """Spaces out request start times to stay under a requests-per-minute limit."""

    def __init__(self, requests_per_minute: float | None):
        self.interval = 60.0 / requests_per_minute if requests_per_minute else 0.0
        self.lock = threading.Lock()
        self.next_start = 0.0

    def wait(self) -> None:
        if not self.interval:
            return
        with self.lock:
            now = time.monotonic()
            start = max(now, self.next_start)
            self.next_start = start + self.interval
        time.sleep(start - now)


def api_key(g: dict) -> str:
    load_dotenv(ROOT / ".env")
    key = os.environ.get(g["api_key_env"], "").strip()
    if not key:
        raise SystemExit(f"{g['api_key_env']} is not set. Add it to .env (see .env.example).")
    return key


class ReplicateBackend:
    """Replicate's HTTP API: https://replicate.com/docs/reference/http

    Official models (e.g. black-forest-labs/flux-schnell) run at
    POST /v1/models/{owner}/{name}/predictions. `Prefer: wait` holds the request open until the
    prediction finishes, so a fast model usually needs no polling. Every model has its own input
    schema, so the inputs come from the [generation.input] table in config.toml rather than from
    this code; only the prompt, the number of images and the seed are filled in here.
    """

    def __init__(self, g: dict):
        self.model = g["model"]
        self.token = api_key(g)
        self.wait = max(1, min(int(g.get("wait_seconds") or 60), 60))  # Prefer: wait accepts 1-60
        self.count_param = g.get("count_param") or "num_outputs"
        self.seed_param = g.get("seed_param") or ""
        self.input = dict(g.get("input") or {})
        self.version = (g.get("model_version") or "").strip()
        self.seen_version: str | None = None
        self.version_lock = threading.Lock()

    def preflight(self) -> None:
        """Check the pinned version before anything is spent, not after.

        Reading a model's metadata is free and creates no prediction, so this is the cheap half of
        the guarantee: if Replicate would already serve a different version than this run is pinned
        to, say so now rather than after the first few hundred images. check_version below is the
        other half, for a model that changes while the run is in flight.
        """
        if not self.version:
            return
        current = (self.request(f"{REPLICATE_API}/models/{self.model}").get("latest_version") or {}).get("id")
        if current and current != self.version:
            raise SystemExit(
                f"\ngeneration.model_version pins {self.version[:12]}…, but Replicate now serves "
                f"{current[:12]}… for {self.model}.\nThe model was updated, and these images would "
                f"not match any already measured under the pin. Either keep the old run as it is "
                f"and start a new generation.run_name with model_version = \"{current}\", or clear "
                f"the pin to accept whatever Replicate serves.")

    def check_version(self, version: str | None) -> None:
        """Stop the run if Replicate answered with a model version other than this run's.

        Replicate can update a model under its own name, which would change what the numbers
        measure without changing anything visible on disk. generation.model_version pins the
        version this run is allowed to use; with no pin, the first version seen becomes the pin for
        the rest of the run. Either way a change is fatal rather than a warning, because a run that
        half predates an update is not one measurement.
        """
        if not version:
            return
        with self.version_lock:
            expected = self.version or self.seen_version
            if not expected:
                self.seen_version = version
                return
        if version != expected:
            raise FatalError(
                f"Replicate answered with model version {version}, not {expected}. The model was "
                f"updated, so these images would not be the ones already on disk. Start a new "
                f"generation.run_name for the new version, or set generation.model_version to the "
                f"one you mean to measure.")

    def generate(self, prompt: str, n: int, seed: int | None = None) -> Generated:
        body = {"input": {"prompt": prompt, **self.input, self.count_param: n}}
        if seed is not None and self.seed_param:
            body["input"][self.seed_param] = seed
        prediction = self.request(f"{REPLICATE_API}/models/{self.model}/predictions", body)
        deadline = time.monotonic() + POLL_TIMEOUT
        while prediction.get("status") in ("starting", "processing"):
            if time.monotonic() > deadline:
                raise RuntimeError(f"prediction {prediction.get('id')} never finished")
            time.sleep(POLL_INTERVAL)
            prediction = self.request(prediction["urls"]["get"])
        if prediction.get("status") != "succeeded":
            detail = str(prediction.get("error") or prediction.get("status"))[:300]
            if looks_like_refusal(detail):
                raise Refusal(detail)
            raise RuntimeError(f"prediction {prediction.get('status')}: {detail}")
        output = prediction.get("output") or []
        urls = [output] if isinstance(output, str) else [u for u in output if isinstance(u, str)]
        if not urls:
            raise RuntimeError("prediction succeeded but returned no image")
        self.check_version(prediction.get("version"))
        # Replicate deletes prediction outputs after an hour, so download them now.
        return Generated(
            images=[(self.download(url), None) for url in urls],
            info={
                "provider": "replicate",
                "model": prediction.get("model") or self.model,
                "version": prediction.get("version"),
                "prediction_id": prediction.get("id"),
                "predict_time": (prediction.get("metrics") or {}).get("predict_time"),
                "prediction_created_at": prediction.get("created_at"),
            },
        )

    def request(self, url: str, body: dict | None = None) -> dict:
        """POST (with a body) or GET, retrying rate limits, timeouts and server errors."""
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json",
                   "User-Agent": USER_AGENT}
        if data is not None:
            headers["Prefer"] = f"wait={self.wait}"
        for attempt in range(HTTP_RETRIES + 1):
            try:
                req = urllib.request.Request(url, data=data, headers=headers)
                with urllib.request.urlopen(req, timeout=self.wait + 120) as resp:
                    return json.load(resp)
            except urllib.error.HTTPError as exc:
                detail = exc.read()[:400].decode("utf-8", "replace")
                if exc.code in (401, 403):
                    raise FatalError(f"Replicate rejected the token (HTTP {exc.code}): {detail}") from None
                if exc.code == 404:
                    raise FatalError(f"no Replicate model {self.model!r} (HTTP 404): {detail}") from None
                if looks_like_refusal(detail):
                    raise Refusal(detail) from None
                if exc.code < 500 and exc.code != 429:
                    raise RuntimeError(f"Replicate HTTP {exc.code}: {detail}") from None
                failure = RuntimeError(f"Replicate HTTP {exc.code}: {detail}")
                delay = float(exc.headers.get("Retry-After") or 2 ** attempt)
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                failure, delay = RuntimeError(f"Replicate request failed: {exc}"), 2 ** attempt
            if attempt == HTTP_RETRIES:
                raise failure
            time.sleep(min(delay, 30))

    def download(self, url: str) -> bytes:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        for attempt in range(HTTP_RETRIES + 1):
            try:
                with urllib.request.urlopen(request, timeout=120) as resp:
                    return resp.read()
            except Exception as exc:
                if attempt == HTTP_RETRIES:
                    raise RuntimeError(f"could not download the image: {exc}") from None
                time.sleep(2 ** attempt)


class OpenAIBackend:
    """Any OpenAI-compatible /images/generations endpoint (OpenAI itself, a LiteLLM gateway, ...)."""

    FATAL = (openai.AuthenticationError, openai.PermissionDeniedError, openai.NotFoundError)

    def preflight(self) -> None:
        """Nothing to check: /images/generations has no version to pin."""

    def __init__(self, g: dict):
        self.g = g
        # The SDK itself retries rate limits (429), server errors and timeouts with backoff.
        self.client = openai.OpenAI(api_key=api_key(g), base_url=g.get("base_url"),
                                    max_retries=5, timeout=300)

    def generate(self, prompt: str, n: int, seed: int | None = None) -> Generated:
        """`seed` is accepted and ignored: /images/generations has no seed input."""
        g = self.g
        kwargs = {"model": g["model"], "prompt": prompt, "n": n, "size": g["size"]}
        if g.get("quality"):
            kwargs["quality"] = g["quality"]
        if g["model"].startswith("dall-e"):
            kwargs["response_format"] = "b64_json"  # gpt-image models always return base64 and reject this
        try:
            response = self.client.images.generate(**kwargs)
            items = response.data or []
        except self.FATAL as exc:
            raise FatalError(str(exc)) from None
        except openai.BadRequestError as exc:
            text = f"{getattr(exc, 'code', '')} {exc}"
            raise (Refusal(text) if looks_like_refusal(text) else RuntimeError(text)) from None
        results = []
        for item in items:
            if item.b64_json:
                data = base64.b64decode(item.b64_json)
            elif item.url:
                with urllib.request.urlopen(item.url, timeout=120) as resp:
                    data = resp.read()
            else:
                continue
            results.append((data, item.revised_prompt))
        usage = getattr(response, "usage", None)
        return Generated(images=results, info={
            "provider": "openai", "model": g["model"],
            "usage": usage.model_dump() if hasattr(usage, "model_dump") else usage,
        })


BACKENDS = {"replicate": ReplicateBackend, "openai": OpenAIBackend}


def make_backend(g: dict):
    provider = (g.get("provider") or "replicate").lower()
    if provider not in BACKENDS:
        raise SystemExit(f"generation.provider must be one of: {', '.join(BACKENDS)}")
    return BACKENDS[provider](g)


def save_image(data: bytes, path: Path, fmt: str, size: tuple[int, int]) -> str:
    """Decode (validating the bytes), fit to exactly `size`, re-encode as `fmt`, and write atomically.

    Returns the size the model actually returned, e.g. "1024x1024". An image at any other size is
    center-cropped to the target aspect ratio and resized, so every image of a run lines up pixel
    for pixel when it is averaged.
    """
    img = Image.open(io.BytesIO(data))
    returned = f"{img.width}x{img.height}"
    if img.size != size:
        img = ImageOps.fit(img, size, Image.Resampling.LANCZOS)
    if fmt == "jpeg":
        img = img.convert("RGB")
    tmp = path.with_name(path.name + ".tmp")
    img.save(tmp, format=fmt.upper(), **({} if fmt == "png" else {"quality": 90}))
    os.replace(tmp, path)
    return returned


def seeds_for(g: dict, indices: list[int]) -> list[int | None]:
    """The seed for each image number: seed_base + the number, so it is the same for every prompt.

    Image 7 of Norway's city, of Nigeria's city and of the no-country baseline then all start from
    the same noise, and the sentence is the only thing that differs between them.
    """
    base = g.get("seed_base") or 0
    return [base + index if base else None for index in indices]


def run(jobs: list[Job], backend, g: dict, out: Path, condition: str) -> None:
    out.mkdir(parents=True, exist_ok=True)
    fmt = g["save_format"]
    throttle = Throttle(g.get("requests_per_minute"))
    lock = threading.Lock()  # guards the job iterator, counters, progress bar and log appends
    stop = threading.Event()
    pending = iter(jobs)
    counts = {"saved": 0, "failed": 0, "skipped": 0, "consecutive_failures": 0}
    refusals: dict[Prompt, int] = {}
    bar = tqdm(total=sum(len(j.indices) for j in jobs), unit="img")

    def append_jsonl(path: Path, records: list[dict]) -> None:
        with lock, open(path, "a", encoding="utf-8") as f:
            f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in records)

    def do_job(job: Job) -> int:
        # A seed only reaches the model when the request is for a single image: a model handed one
        # seed for a batch picks the rest itself, so the number recorded would not be the one used.
        seeds = seeds_for(g, job.indices)
        result = backend.generate(job.prompt.text, len(job.indices),
                                  seeds[0] if len(job.indices) == 1 else None)
        folder = out / "images" / job.prompt.iso3 / job.prompt.place
        folder.mkdir(parents=True, exist_ok=True)
        created = datetime.now(timezone.utc).isoformat(timespec="seconds")
        records = []
        size = parse_size(g["size"])
        for (index, seed), (data, revised_prompt) in zip(zip(job.indices, seeds), result.images):
            name = f"{index:04d}.{EXTENSIONS[fmt]}"
            returned_size = save_image(data, folder / name, fmt, size)
            records.append({
                "index": index, "file": name, "country": job.prompt.iso3, "place": job.prompt.place,
                "condition": condition, "prompt": job.prompt.text, "revised_prompt": revised_prompt,
                "model": g["model"], "seed": seed if len(job.indices) == 1 else None,
                "size": g["size"], "returned_size": returned_size, "quality": g.get("quality"),
                "created_at": created,
            })
        append_jsonl(folder / "metadata.jsonl", records)
        append_jsonl(out / "predictions.jsonl", [{
            "at": created, "country": job.prompt.iso3, "place": job.prompt.place,
            "condition": condition, "indices": job.indices, "saved": len(records), **result.info,
        }])
        return len(records)

    def log_failure(job: Job, exc: Exception) -> None:
        append_jsonl(out / "failures.jsonl", [{
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "country": job.prompt.iso3, "place": job.prompt.place, "condition": condition,
            "prompt": job.prompt.text, "indices": job.indices, "error": type(exc).__name__, "status": getattr(exc, "status_code", None),
            "refusal": isinstance(exc, Refusal), "message": str(exc)[:500],
        }])

    def worker() -> None:
        while not stop.is_set():
            with lock:
                job = next(pending, None)
                if job is not None and refusals.get(job.prompt, 0) >= MAX_REFUSALS_PER_PROMPT:
                    counts["skipped"] += len(job.indices)
                    bar.update(len(job.indices))
                    continue
            if job is None:
                return
            throttle.wait()
            if stop.is_set():
                return
            try:
                saved, error = do_job(job), None
            except Exception as exc:  # refusals, budget and rate limits, bad responses, network trouble
                saved, error = 0, exc
                log_failure(job, exc)
            with lock:
                bar.update(len(job.indices))
                if error is None:
                    counts["saved"] += saved
                    counts["consecutive_failures"] = 0
                    continue
                counts["failed"] += len(job.indices)
                if isinstance(error, Refusal):
                    refusals[job.prompt] = refusals.get(job.prompt, 0) + 1
                    continue
                counts["consecutive_failures"] += 1
                give_up = not stop.is_set() and (
                    isinstance(error, FatalError)
                    or "budget" in str(error).lower()
                    or counts["consecutive_failures"] >= MAX_CONSECUTIVE_FAILURES
                )
                if give_up:
                    stop.set()
            if give_up:
                tqdm.write(f"Stopping: {type(error).__name__}: {str(error)[:300]}")

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(max(1, g["concurrency"]))]
    for t in threads:
        t.start()
    try:
        for t in threads:
            while t.is_alive():
                t.join(0.5)
    except KeyboardInterrupt:
        tqdm.write("Finishing in-flight requests... (press Ctrl+C again to quit now)")
        stop.set()
        for t in threads:
            t.join()
    bar.close()
    print(f"Saved {counts['saved']:,} images · {counts['failed']:,} failed · {counts['skipped']:,} skipped "
          f"(prompt refused {MAX_REFUSALS_PER_PROMPT}+ times). Re-run the same command to continue.")
    if counts["failed"]:
        print(f"Failure details: {os.path.relpath(out / 'failures.jsonl', ROOT)}")


def split_arg(value: str | None, normalize) -> list[str] | None:
    return [normalize(v.strip()) for v in value.split(",") if v.strip()] if value else None


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Generate images for every (country, place) prompt.")
    ap.add_argument("--dry-run", action="store_true", help="print the plan and exit")
    ap.add_argument("--countries", help="comma-separated ISO alpha-3 codes, e.g. FRA,NGA (default: all)")
    ap.add_argument("--places", help="comma-separated place ids, e.g. city,farm (default: all)")
    ap.add_argument("--n", type=int, help="images per prompt, or the most a budget may buy "
                                          "(default: generation.images_per_prompt)")
    ap.add_argument("--budget", type=float, help="most the whole run may cost in USD, counting images "
                                                 "already on disk (default: generation.budget_usd)")
    ap.add_argument("--prices", help="comma-separated prices per image to compare in the plan, "
                                     "e.g. 0.003,0.04,0.065")
    ap.add_argument("--condition", help="which prompt template to use, from [prompts.conditions] "
                                        "(default: prompts.condition)")
    ap.add_argument("--run", help="output folder under outputs/ "
                                  "(default: generation.run_name + '-' + the condition)")
    ap.add_argument("-y", "--yes", action="store_true", help="skip the confirmation prompt")
    args = ap.parse_args(argv)

    cfg = load_config()
    g = cfg["generation"]
    if g["save_format"] not in EXTENSIONS:
        raise SystemExit(f"generation.save_format must be one of: {', '.join(EXTENSIONS)}")
    if (g.get("seed_base") or 0) and g["images_per_request"] != 1:
        raise SystemExit(
            f"generation.seed_base is set, so generation.images_per_request must be 1, not "
            f"{g['images_per_request']}: a model given one seed for a batch chooses the rest of "
            f"the batch's seeds itself, and metadata.jsonl would record a seed that does not "
            f"reproduce the image. Set seed_base = 0 to batch requests instead.")
    try:
        parse_size(g["size"])
        condition, template = template_for(cfg, args.condition)
        prompts = load_prompts(cfg, split_arg(args.countries, str.upper),
                               split_arg(args.places, str.lower), condition)
        prices = [float(p) for p in split_arg(args.prices, str.strip) or []]
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    if args.countries and any(p.iso3 == NO_COUNTRY for p in prompts):
        print(f"Note: condition {condition!r} names no country, so --countries is ignored.")

    cap = args.n or g["images_per_prompt"]
    budget = (g.get("budget_usd") or 0) if args.budget is None else args.budget
    price = g.get("price_per_image_usd") or 0
    if budget and not price:
        raise SystemExit("A budget needs generation.price_per_image_usd: what one image costs.")
    out = run_dir(cfg, args.run or f"{g['run_name']}-{condition.replace('_', '-')}")
    have = [len(existing_indices(out / "images" / p.iso3 / p.place)) for p in prompts]
    n_per_prompt = images_within_budget(have, cap, price, budget) if budget else cap
    jobs = plan_jobs(prompts, out / "images", n_per_prompt, g["images_per_request"])

    print_plan(g, prompts, jobs, n_per_prompt, out, budget, have, condition, template)
    if prices:
        print("\n  The same run at other prices:")
        for other in prices:
            n = images_within_budget(have, cap, other, budget) if budget else cap
            print(f"    ${other:<6g}/image  {n:>6,} per prompt  ${run_cost(have, n, other):>10,.2f}")
    minimum = g.get("min_images_per_prompt") or 0
    if budget and n_per_prompt < minimum:
        print(f"\nThe budget buys {n_per_prompt:,} images per prompt; generation.min_images_per_prompt "
              f"is {minimum:,}, and {minimum:,} each would cost ${run_cost(have, minimum, price):,.2f}. "
              "Raise the budget, pick a cheaper model, or narrow the run with --countries/--places.")
        if not args.dry_run:
            raise SystemExit(1)
    if args.dry_run or not jobs:
        return
    if not g["model"]:
        raise SystemExit("\nSet generation.model in config.toml first, e.g. black-forest-labs/flux-schnell.")
    backend = make_backend(g)
    backend.preflight()
    if not args.yes:
        try:
            answer = input("\nStart generating? [y/N] ")
        except EOFError:  # not attached to a terminal
            answer = ""
        if answer.strip().lower() != "y":
            print("Cancelled. (Pass --yes to skip this question.)")
            return
    run(jobs, backend, g, out, condition)


if __name__ == "__main__":
    main()
