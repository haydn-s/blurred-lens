from blurred_lens.generate import plan_jobs
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
