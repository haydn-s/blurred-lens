import io

import pytest
from PIL import Image

from blurred_lens import generate
from blurred_lens.generate import (ReplicateBackend, images_within_budget, parse_size, plan_jobs,
                                   run_cost, save_image)
from blurred_lens.prompts import Prompt


def test_plan_skips_existing_images_and_runs_breadth_first(tmp_path):
    a, b = Prompt("AAA", "city", "a"), Prompt("BBB", "city", "b")
    (tmp_path / "AAA" / "city").mkdir(parents=True)
    (tmp_path / "AAA" / "city" / "0001.jpg").touch()

    jobs = plan_jobs([a, b], tmp_path, n_per_prompt=3, per_request=1)

    assert [(j.prompt.iso3, j.indices) for j in jobs] == [
        ("AAA", [2]), ("BBB", [1]),
        ("AAA", [3]), ("BBB", [2]),
        ("BBB", [3]),
    ]


def test_plan_batches_images_per_request(tmp_path):
    jobs = plan_jobs([Prompt("AAA", "city", "a")], tmp_path, n_per_prompt=5, per_request=2)
    assert [j.indices for j in jobs] == [[1, 2], [3, 4], [5]]


def test_budget_buys_the_same_number_of_images_for_every_prompt():
    # 2 prompts at $1/image: $5 buys 2 each ($4); a third round would cost $6.
    assert images_within_budget([0, 0], cap=10, price=1.0, budget=5.0) == 2


def test_budget_counts_images_already_on_disk():
    # The first prompt already has 3: two each costs $3 + $2, three each would cost $6.
    assert run_cost([3, 0], 2, price=1.0) == 5.0
    assert images_within_budget([3, 0], cap=10, price=1.0, budget=5.0) == 2


def test_budget_is_capped_and_exact_at_real_prices():
    assert images_within_budget([0] * 1576, cap=1000, price=0.003, budget=10**6) == 1000
    assert images_within_budget([0] * 1576, cap=1000, price=0.003, budget=472.8) == 100


def test_parse_size():
    assert parse_size("1536x1024") == (1536, 1024)
    with pytest.raises(ValueError, match="1024x1024"):
        parse_size("auto")


def test_images_at_the_wrong_size_are_fitted_to_the_run_size(tmp_path):
    buf = io.BytesIO()
    Image.new("RGB", (300, 200), "red").save(buf, format="PNG")

    returned = save_image(buf.getvalue(), tmp_path / "0001.jpg", "jpeg", (64, 64))

    assert returned == "300x200"
    with Image.open(tmp_path / "0001.jpg") as img:
        assert img.size == (64, 64)


def replicate_backend(monkeypatch):
    """A ReplicateBackend whose network calls the caller replaces with `request` and `download`."""
    monkeypatch.setenv("REPLICATE_API_TOKEN", "r8_not_a_real_token")
    return ReplicateBackend({
        "model": "owner/model", "api_key_env": "REPLICATE_API_TOKEN",
        "count_param": "num_outputs", "input": {"aspect_ratio": "1:1"},
    })


def test_replicate_sends_the_prompt_with_the_model_inputs_and_keeps_every_image(monkeypatch):
    sent = []
    backend = replicate_backend(monkeypatch)
    backend.request = lambda url, body=None: sent.append((url, body)) or {
        "status": "succeeded", "output": ["https://out/1.jpg", "https://out/2.jpg"]}
    backend.download = lambda url: f"bytes of {url}".encode()

    images = backend.generate("a city in Nigeria", 2)

    url, body = sent[0]
    assert url.endswith("/models/owner/model/predictions")
    assert body["input"] == {"prompt": "a city in Nigeria", "aspect_ratio": "1:1", "num_outputs": 2}
    assert [data for data, _ in images] == [b"bytes of https://out/1.jpg", b"bytes of https://out/2.jpg"]


def test_replicate_polls_until_the_prediction_finishes(monkeypatch):
    monkeypatch.setattr(generate.time, "sleep", lambda _: None)
    backend = replicate_backend(monkeypatch)
    replies = iter([
        {"status": "processing", "urls": {"get": "https://api/predictions/1"}},
        {"status": "processing", "urls": {"get": "https://api/predictions/1"}},
        {"status": "succeeded", "output": "https://out/1.jpg"},  # one URL, not a list
    ])
    backend.request = lambda url, body=None: next(replies)
    backend.download = lambda url: b"image"

    assert backend.generate("a city in Nigeria", 1) == [(b"image", None)]


def test_replicate_safety_rejection_is_a_refusal_but_other_failures_are_not(monkeypatch):
    backend = replicate_backend(monkeypatch)

    backend.request = lambda url, body=None: {"status": "failed", "error": "NSFW content detected"}
    with pytest.raises(generate.Refusal):
        backend.generate("a city in Nigeria", 1)

    backend.request = lambda url, body=None: {"status": "failed", "error": "CUDA out of memory"}
    with pytest.raises(RuntimeError) as failure:
        backend.generate("a city in Nigeria", 1)
    assert not isinstance(failure.value, generate.Refusal)


def test_replicate_sends_a_user_agent_and_the_wait_header(monkeypatch):
    """Cloudflare answers urllib's default agent with HTTP 403 (code 1010), so the agent is required."""
    captured = []

    def fake_urlopen(request, timeout=None):
        captured.append(request)
        return io.BytesIO(b'{"status": "succeeded", "output": ["https://out/1.jpg"]}')

    monkeypatch.setattr(generate.urllib.request, "urlopen", fake_urlopen)
    backend = replicate_backend(monkeypatch)

    backend.generate("a city in Nigeria", 1)

    for request in captured:
        headers = {name.lower(): value for name, value in request.headers.items()}
        assert headers["user-agent"] == generate.USER_AGENT
    assert {name.lower() for name in captured[0].headers}.issuperset({"authorization", "prefer"})
    assert captured[0].headers["Prefer"] == "wait=60"
