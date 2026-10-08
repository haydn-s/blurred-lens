"""The poster's words and numbers, kept apart from how they are drawn.

A story in five beats -- the problem, how we looked, what we found, what it means, what is next --
so a passer-by can follow it standing up and leave knowing why it matters. The statistics are
evidence for the story, not the subject of it; the detail lives in the repository.

Written to poster length. A 24x36 sheet read from four feet needs 24pt body text, and 24pt eats the
page, so each entry is a headline that carries the point and a line or two that lands it.

Every figure is read back out of the run by `check_numbers()` in make_poster.py, so a poster whose
claims have drifted from the data fails rather than prints.
"""

TITLE = "Blurred Lens"
SUBTITLE = ("Does an AI image model paint poorer countries in warmer colour? "
            "61,488 generated photographs say the honest answer is more interesting than yes.")
BYLINE = "Haydn Stucker  ·  AIPI 590: Explainable AI  ·  Duke University"

STATS = [
    ("61,488", "images generated"),
    ("60 × 6", "countries × kinds of place"),
    ("53 of 60", "warmer than the model's own default"),
    ("0", "failures or refusals"),
]

PROBLEM_HEAD = "The problem"
PROBLEM = (
    "Film colours places. A sepia wash over Mexico; dust and amber for “somewhere "
    "dangerous.” A yellow filter tells an audience a place is poor, hot and unsafe before a "
    "word is spoken.\n\n"
    "Image models learn from pictures like those. If one inherited the habit, every picture it "
    "makes of a country carries a quiet judgement — and no single image can show you.")

GRID_CAPTION = "Only the country changed"
GRID_NOTE_HEAD = "What you are looking at"
GRID_NOTE = ("Image 1 of every prompt uses the same seed, so all eight start from identical "
             "noise and the street recedes the same way. Only the country named differs. "
             "Figures are standard deviations from the average country.")

PROCESS_HEAD = "How we looked"
PROCESS = [
    ("Ask everyone the same thing",
     "One sentence, one fixed camera, 84 times per prompt."),
    ("Take away the easy excuse",
     "Run it again pinned to noon under a clear sky. The pin names no colour."),
    ("Give it a zero",
     "The same places with no country named — the model's own default."),
    ("Pick countries that disagree",
     "15 per income group, so income and latitude pull apart (ρ = 0.25 against 0.49)."),
    ("Make the rivals compete",
     "Hold real latitude, temperature, rainfall and forest cover constant. Ask again."),
]

FINDINGS_HEAD = "What we found"
MAP_CAPTION = "Every country, coloured by its warmth"
MAP_NOTE = "Amber: warmer than average. Blue: cooler. Pale: not in this run."

FINDINGS = [
    ("It really does grade countries",
     "53 of 60 beat its own no-country default. Norway alone is cooler."),
    ("But not the poor ones — the dry ones",
     "Saudi Arabia and Kuwait are high-income and near the top."),
    ("Income looks real until climate is held constant",
     "d = +0.72 (p = .02) falls to +0.52, no better than chance."),
    ("Latitude was the wrong confound",
     "It accounts for 5%. Forest cover accounts for 30%."),
    ("Asia survives everything",
     "+0.70 (p = .01) after every control, in all six kinds of place. Africa's gap vanishes."),
]

EXPLAINS_HEAD = "What accounts for the warmth"
EXPLAINS = [("forest cover", 30), ("mean temperature", 25), ("rainfall", 18), ("latitude", 5)]
EXPLAINS_NOTE = ("What each rival explanation accounts for alone. Latitude — the confound the "
                 "country list was built to defeat — was the wrong one.")

MEANS_HEAD = "What it means"
MEANS = [
    ("The intuitive claim is wrong",
     "It is not warming poor countries but dry, bare ones — substantially what they look like."),
    ("“Substantially” is not “entirely”",
     "A regional residual outlives every control. North Korea is humid and half forested, and the "
     "warmest thing on the map."),
    ("The method mattered more than the result",
     "Naively measured, income was there at p = .02. It did not survive. An audit without "
     "that control would have published it."),
    ("A measurement needs a zero",
     "Ranking countries says who is warmest. Only a no-country baseline says whether anyone is "
     "warmed at all."),
]

NEXT_HEAD = "What is next"
NEXT = [
    "Why Asia? The residual now needs a mechanism.",
    "A better climate measure — four country averages leave 54% unexplained.",
    "Other models and languages: this is one model's habit, not the industry's.",
    "Content, not just colour: who is in frame and what they are doing.",
]

LIMITS_HEAD = "What it cannot show"
LIMITS = ("Straight-line controls on four country averages cannot separate a stereotype from "
          "a climate, only say whether a pattern needs more than climate to describe it. "
          "18 comparisons per metric: lean on the strongest results only.")

FOOTER = ("Every prompt, image and measurement — github.com/haydn-s/blurred-lens  ·  "
          "flux-schnell on Replicate, one pinned version  ·  October 2026  ·  $185 of compute")
