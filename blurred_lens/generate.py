"""Generate images for every (country, place) prompt through an OpenAI-compatible images API.

    python -m blurred_lens.generate --dry-run      # plan only: counts, cost, time, disk
    python -m blurred_lens.generate --countries FRA,NGA,JPN --places city,farm --n 5
    python -m blurred_lens.generate                # everything in config.toml

Resumable: images already on disk are skipped, so re-running continues where the last
run stopped. Requests go out breadth-first (image 1 of every prompt, then image 2, ...),
so a run cut short by a budget or rate limit leaves every prompt with about the same
number of images instead of a few finished prompts and many empty ones.
"""

import argparse
import base64
import io
import itertools
import json
import os
import threading
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import openai
from dotenv import load_dotenv
from PIL import Image
from tqdm import tqdm

from .config import IMAGE_RE, ROOT, load_config, run_dir
from .prompts import Prompt, load_prompts

EXTENSIONS = {"jpeg": "jpg", "webp": "webp", "png": "png"}
TYPICAL_BYTES = {"jpeg": 250_000, "webp": 150_000, "png": 1_600_000}  # rough size of one 1024x1024 image

# Errors that retrying won't fix: bad key, no access to the model, wrong endpoint.
FATAL_ERRORS = (openai.AuthenticationError, openai.PermissionDeniedError, openai.NotFoundError)
MAX_CONSECUTIVE_FAILURES = 10
MAX_REFUSALS_PER_PROMPT = 3  # content-policy refusals before a prompt is skipped for this run


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


def print_plan(g: dict, prompts: list[Prompt], jobs: list[Job], n_per_prompt: int, out: Path) -> None:
    todo = sum(len(j.indices) for j in jobs)
    target = len(prompts) * n_per_prompt
    price = g.get("price_per_image_usd") or 0
    rpm = g.get("requests_per_minute") or 0
    n_countries, n_places = len({p.iso3 for p in prompts}), len({p.place for p in prompts})
    rows = [
        ("Output folder", os.path.relpath(out, ROOT)),
        ("Model", f"{g['model'] or '(not set)'} · {g['size']} · quality {g.get('quality') or 'default'}"),
        ("Prompts", f"{len(prompts):,}  ({n_countries} countries × {n_places} places)"),
        ("Target images", f"{target:,}  ({n_per_prompt:,} per prompt)"),
        ("Already on disk", f"{target - todo:,}"),
        ("To generate", f"{todo:,}  in {len(jobs):,} requests"),
        ("Est. cost", f"${todo * price:,.2f}  (@ ${price}/image)" if price
         else "unknown (set generation.price_per_image_usd)"),
        ("Est. time", f"at least {human_minutes(len(jobs) / rpm)}  (@ {rpm} requests/min)" if rpm
         else "unknown (no requests_per_minute limit)"),
        ("Est. disk", f"~{human_bytes(todo * TYPICAL_BYTES[g['save_format']])}  (as {g['save_format']})"),
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


def make_client(g: dict) -> openai.OpenAI:
    load_dotenv(ROOT / ".env")
    key = os.environ.get(g["api_key_env"], "").strip()
    if not key:
        raise SystemExit(f"{g['api_key_env']} is not set. Add it to .env (see .env.example).")
    # The SDK itself retries rate limits (429), server errors and timeouts with backoff.
    return openai.OpenAI(api_key=key, base_url=g["base_url"], max_retries=5, timeout=300)


def request_images(client: openai.OpenAI, g: dict, prompt: str, n: int) -> list[tuple[bytes, str | None]]:
    """(image bytes, revised prompt) for each image the API returns."""
    kwargs = {"model": g["model"], "prompt": prompt, "n": n, "size": g["size"]}
    if g.get("quality"):
        kwargs["quality"] = g["quality"]
    if g["model"].startswith("dall-e"):
        kwargs["response_format"] = "b64_json"  # gpt-image models always return base64 and reject this
    results = []
    for item in client.images.generate(**kwargs).data or []:
        if item.b64_json:
            data = base64.b64decode(item.b64_json)
        elif item.url:
            with urllib.request.urlopen(item.url, timeout=120) as resp:
                data = resp.read()
        else:
            continue
        results.append((data, item.revised_prompt))
    return results


def save_image(data: bytes, path: Path, fmt: str) -> None:
    """Decode (validating the bytes), re-encode as `fmt`, and write atomically."""
    img = Image.open(io.BytesIO(data))
    if fmt == "jpeg":
        img = img.convert("RGB")
    tmp = path.with_name(path.name + ".tmp")
    img.save(tmp, format=fmt.upper(), **({} if fmt == "png" else {"quality": 90}))
    os.replace(tmp, path)


def is_refusal(exc: Exception) -> bool:
    """A content-policy rejection: a result worth recording, not a transient error."""
    text = f"{getattr(exc, 'code', '')} {exc}".lower()
    return isinstance(exc, openai.BadRequestError) and any(w in text for w in ("content_policy", "moderation", "safety"))


def run(jobs: list[Job], client: openai.OpenAI, g: dict, out: Path) -> None:
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
        images = request_images(client, g, job.prompt.text, len(job.indices))
        folder = out / "images" / job.prompt.iso3 / job.prompt.place
        folder.mkdir(parents=True, exist_ok=True)
        created = datetime.now(timezone.utc).isoformat(timespec="seconds")
        records = []
        for index, (data, revised_prompt) in zip(job.indices, images):
            name = f"{index:04d}.{EXTENSIONS[fmt]}"
            save_image(data, folder / name, fmt)
            records.append({
                "index": index, "file": name, "country": job.prompt.iso3, "place": job.prompt.place,
                "prompt": job.prompt.text, "revised_prompt": revised_prompt, "model": g["model"],
                "size": g["size"], "quality": g.get("quality"), "created_at": created,
            })
        append_jsonl(folder / "metadata.jsonl", records)
        return len(records)

    def log_failure(job: Job, exc: Exception) -> None:
        append_jsonl(out / "failures.jsonl", [{
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "country": job.prompt.iso3, "place": job.prompt.place, "prompt": job.prompt.text,
            "indices": job.indices, "error": type(exc).__name__, "status": getattr(exc, "status_code", None),
            "refusal": is_refusal(exc), "message": str(exc)[:500],
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
                if is_refusal(error):
                    refusals[job.prompt] = refusals.get(job.prompt, 0) + 1
                    continue
                counts["consecutive_failures"] += 1
                give_up = not stop.is_set() and (
                    isinstance(error, FATAL_ERRORS)
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
    ap.add_argument("--n", type=int, help="images per prompt (default: generation.images_per_prompt)")
    ap.add_argument("--run", help="output folder under outputs/ (default: generation.run_name)")
    ap.add_argument("-y", "--yes", action="store_true", help="skip the confirmation prompt")
    args = ap.parse_args(argv)

    cfg = load_config()
    g = cfg["generation"]
    if g["save_format"] not in EXTENSIONS:
        raise SystemExit(f"generation.save_format must be one of: {', '.join(EXTENSIONS)}")
    try:
        prompts = load_prompts(cfg, split_arg(args.countries, str.upper), split_arg(args.places, str.lower))
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    n_per_prompt = args.n or g["images_per_prompt"]
    out = run_dir(cfg, args.run)
    jobs = plan_jobs(prompts, out / "images", n_per_prompt, g["images_per_request"])

    print_plan(g, prompts, jobs, n_per_prompt, out)
    if args.dry_run or not jobs:
        return
    if not g["model"]:
        raise SystemExit("\nSet generation.model in config.toml first. "
                         "(The Duke gateway has no image models yet: see README.)")
    client = make_client(g)
    if not args.yes:
        try:
            answer = input("\nStart generating? [y/N] ")
        except EOFError:  # not attached to a terminal
            answer = ""
        if answer.strip().lower() != "y":
            print("Cancelled. (Pass --yes to skip this question.)")
            return
    run(jobs, client, g, out)


if __name__ == "__main__":
    main()
