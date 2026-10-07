"""The poster's words and numbers, kept apart from how they are drawn.

Written to poster length, which is much shorter than it feels while writing it. A 24x36 sheet read
from four feet away needs body text at 24pt, and 24pt eats the page -- so every section here is a
headline a passer-by can take in standing up, not a paragraph. The detail lives in the repository,
and the footer says so.

Every figure is read back out of the run by `check_numbers()` in make_poster.py, so a poster whose
claims have drifted from the data fails rather than prints.
"""

TITLE = "Blurred Lens"
SUBTITLE = ("An AI image model pictures drier countries in warmer colour — "
            "not poorer ones. And it draws Asia warmer than any climate explains.")
BYLINE = "Haydn Stucker  ·  AIPI 590: Explainable AI  ·  Duke University"

STATS = [
    ("61,488", "images generated"),
    ("60 × 6", "countries × places"),
    ("53 of 60", "warmer than the model's own default"),
    ("0", "failures or refusals"),
]

QUESTION_HEAD = "The question"
QUESTION = ("Film colours places: a sepia wash over Mexico, dust and amber for “somewhere "
            "dangerous.” A model trained on those pictures may have learned the habit. Does it "
            "warm the countries that are poorer?")

GRID_CAPTION = "Only the country changed"
GRID_NOTE_HEAD = "What you are looking at"
GRID_NOTE = ("Image 1 of every prompt uses the same seed, so all eight start from identical noise "
             "and the street recedes the same way. Only the country in the sentence differs. "
             "Figures are standard deviations from the average country.")

MAP_CAPTION = "How the model colours each of the 60 countries"
MAP_NOTE = ("Amber: warmer than the average country. Blue: cooler. "
            "Grey: the middle of the pack. Pale: not in this run.")

TABLE_TITLE = "What predicts the warmth"
TABLE_NOTE = ("Each row holds a rival explanation constant and asks again. "
              "Cohen's d, permutation p in brackets.")
TABLE = [
    ["held constant", "r²", "low income", "Africa", "Asia"],
    ["nothing", "—", "+0.72 (.018)", "+0.62 (.030)", "+0.60 (.026)"],
    ["|latitude|", "5%", "+0.62 (.041)", "+0.47 (.097)", "+0.79 (.005)"],
    ["log rainfall", "18%", "+0.73 (.017)", "+0.51 (.073)", "+0.42 (.114)"],
    ["mean temperature", "25%", "+0.72 (.018)", "+0.33 (.228)", "+0.88 (.003)"],
    ["forest cover", "30%", "+0.48 (.116)", "+0.23 (.404)", "+0.44 (.110)"],
    ["all four together", "46%", "+0.52 (.091)", "−0.03 (.919)", "+0.73 (.011)"],
]

FINDINGS = [
    ("Naming a country warms the picture",
     "53 of 60 beat the model's no-country default. Norway alone is cooler."),
    ("Income does not survive the controls",
     "d = +0.72 falls to +0.52, no better than chance. Forest cover is what moves it — "
     "not heat, not dryness, not latitude."),
    ("Latitude was the wrong confound",
     "The country list was built to defeat it. It explains 5%. Forest cover explains 30%."),
    ("Africa's warmth is climate. Asia's is not",
     "Africa's gap vanishes (−0.03). Asia's survives everything (+0.73, p = .011) and holds "
     "in all six kinds of place."),
]

METHOD_HEAD = "How it was measured"
METHOD = [
    "“A photograph of {place} in {country}, {view}.” One camera per kind of place.",
    "Run twice: free, and again pinned to noon under a clear sky. The pin names no colour.",
    "The same places with no country named, giving the model's own default to measure from.",
    "60 countries, 15 per income group, chosen so income and latitude pull apart "
    "(ρ = 0.25 here against 0.49 worldwide).",
    "84 images per prompt, sized from a 3,300-image pilot's measured noise.",
    "flux-schnell on Replicate, one pinned version, 1024×1024, every seed recorded.",
]

LIMITS_HEAD = "What it cannot show"
LIMITS = [
    "One model, one prompt template, one language.",
    "Four country averages is a blunt control; 54% of the spread is unexplained.",
    "Controlling for climate may control away part of the question.",
    "18 comparisons per metric, and Europe is three countries here against Oceania’s two "
    "— only the strongest results carry weight.",
]

FOOTER = ("Every prompt, image and measurement — github.com/haydn-s/blurred-lens  ·  "
          "October 2026  ·  $185 of compute")
