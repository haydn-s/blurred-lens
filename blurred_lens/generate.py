"""Generate images for every (country, place) prompt through an image-generation API.

    python -m blurred_lens.generate --dry-run      # plan only: counts, cost, time, disk
    python -m blurred_lens.generate --countries FRA,NGA,JPN --places city,farm --n 5
    python -m blurred_lens.generate --budget 1000  # spread $1,000 evenly over every prompt
    python -m blurred_lens.generate                # everything in config.toml

Resumable: images already on disk are skipped, so re-running continues where the last
run stopped. Requests go out breadth-first (image 1 of every prompt, then image 2, ...),
so a run cut short by a budget or rate limit leaves every prompt with about the same
number of images instead of a few finished prompts and many empty ones.

A budget (generation.budget_usd, or --budget) decides how many images each prompt gets:
it is split evenly, so every country and place ends up with a composite built from the
same number of images. Every image is saved at exactly generation.size, and each place
fixes the camera position, so one prompt's images line up when they are averaged.
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
from .prompts import Prompt, load_prompts

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
               budget: float, have: list[int]) -> None:
    todo = sum(len(j.indices) for j in jobs)
    target = len(prompts) * n_per_prompt
    price = g.get("price_per_image_usd") or 0
    rpm = g.get("requests_per_minute") or 0
    n_countries, n_places = len({p.iso3 for p in prompts}), len({p.place for p in prompts})
    total = run_cost(have, n_per_prompt, price)
    rows = [
        ("Output folder", os.path.relpath(out, ROOT)),
        ("Model", f"{g.get('provider') or 'replicate'} · {g['model'] or '(not set)'} · {g['size']}"),
        ("Prompts", f"{len(prompts):,}  ({n_countries} countries × {n_places} places)"),
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
    this code; only the prompt and the number of images are filled in here.
    """

    def __init__(self, g: dict):
        self.model = g["model"]
        self.token = api_key(g)
        self.wait = max(1, min(int(g.get("wait_seconds") or 60), 60))  # Prefer: wait accepts 1-60
        self.count_param = g.get("count_param") or "num_outputs"
        self.input = dict(g.get("input") or {})

    def generate(self, prompt: str, n: int) -> list[tuple[bytes, str | None]]:
        body = {"input": {"prompt": prompt, **self.input, self.count_param: n}}
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
        # Replicate deletes prediction outputs after an hour, so download them now.
        return [(self.download(url), None) for url in urls]

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

    def __init__(self, g: dict):
        self.g = g
        # The SDK itself retries rate limits (429), server errors and timeouts with backoff.
        self.client = openai.OpenAI(api_key=api_key(g), base_url=g.get("base_url"),
                                    max_retries=5, timeout=300)

    def generate(self, prompt: str, n: int) -> list[tuple[bytes, str | None]]:
        g = self.g
        kwargs = {"model": g["model"], "prompt": prompt, "n": n, "size": g["size"]}
        if g.get("quality"):
            kwargs["quality"] = g["quality"]
        if g["model"].startswith("dall-e"):
            kwargs["response_format"] = "b64_json"  # gpt-image models always return base64 and reject this
        try:
            items = self.client.images.generate(**kwargs).data or []
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
        return results


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


def run(jobs: list[Job], backend, g: dict, out: Path) -> None:
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
        images = backend.generate(job.prompt.text, len(job.indices))
        folder = out / "images" / job.prompt.iso3 / job.prompt.place
        folder.mkdir(parents=True, exist_ok=True)
        created = datetime.now(timezone.utc).isoformat(timespec="seconds")
        records = []
        size = parse_size(g["size"])
        for index, (data, revised_prompt) in zip(job.indices, images):
            name = f"{index:04d}.{EXTENSIONS[fmt]}"
            returned_size = save_image(data, folder / name, fmt, size)
            records.append({
                "index": index, "file": name, "country": job.prompt.iso3, "place": job.prompt.place,
                "prompt": job.prompt.text, "revised_prompt": revised_prompt, "model": g["model"],
                "size": g["size"], "returned_size": returned_size, "quality": g.get("quality"),
                "created_at": created,
            })
        append_jsonl(folder / "metadata.jsonl", records)
        return len(records)

    def log_failure(job: Job, exc: Exception) -> None:
        append_jsonl(out / "failures.jsonl", [{
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "country": job.prompt.iso3, "place": job.prompt.place, "prompt": job.prompt.text,
            "indices": job.indices, "error": type(exc).__name__, "status": getattr(exc, "status_code", None),
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
    ap.add_argument("--run", help="output folder under outputs/ (default: generation.run_name)")
    ap.add_argument("-y", "--yes", action="store_true", help="skip the confirmation prompt")
    args = ap.parse_args(argv)

    cfg = load_config()
    g = cfg["generation"]
    if g["save_format"] not in EXTENSIONS:
        raise SystemExit(f"generation.save_format must be one of: {', '.join(EXTENSIONS)}")
    try:
        parse_size(g["size"])
        prompts = load_prompts(cfg, split_arg(args.countries, str.upper), split_arg(args.places, str.lower))
        prices = [float(p) for p in split_arg(args.prices, str.strip) or []]
    except ValueError as exc:
        raise SystemExit(str(exc)) from None

    cap = args.n or g["images_per_prompt"]
    budget = (g.get("budget_usd") or 0) if args.budget is None else args.budget
    price = g.get("price_per_image_usd") or 0
    if budget and not price:
        raise SystemExit("A budget needs generation.price_per_image_usd: what one image costs.")
    out = run_dir(cfg, args.run)
    have = [len(existing_indices(out / "images" / p.iso3 / p.place)) for p in prompts]
    n_per_prompt = images_within_budget(have, cap, price, budget) if budget else cap
    jobs = plan_jobs(prompts, out / "images", n_per_prompt, g["images_per_request"])

    print_plan(g, prompts, jobs, n_per_prompt, out, budget, have)
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
    if not args.yes:
        try:
            answer = input("\nStart generating? [y/N] ")
        except EOFError:  # not attached to a terminal
            answer = ""
        if answer.strip().lower() != "y":
            print("Cancelled. (Pass --yes to skip this question.)")
            return
    run(jobs, backend, g, out)


if __name__ == "__main__":
    main()
