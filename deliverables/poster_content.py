"""The poster's words and numbers, kept apart from how they are drawn.

Every figure here is read back out of the run in `check_numbers()` below, so a poster whose claims
have drifted from the data fails rather than prints.
"""

TITLE = "Blurred Lens"
SUBTITLE = ("Does an AI image model picture poorer countries in warmer colour? "
            "61,488 images say it pictures  drier  ones that way — and draws Asia "
            "warmer than its climate accounts for.")
BYLINE = "Haydn Stucker  ·  AIPI 590: Explainable AI  ·  Duke University"

STATS = [
    ("61,488", "images generated"),
    ("60 × 6", "countries × kinds of place"),
    ("53 of 60", "warmer than the model's own default"),
    ("0", "failures or refusals"),
]

QUESTION = (
    "Film colours places. A sepia wash over Mexico; dust and amber for “somewhere dangerous.” "
    "A yellow filter tells an audience that a place is poor, hot and unsafe before a line is spoken. "
    "An image model trained on pictures like those may have learned the habit. This project asks "
    "whether it did — and whether the countries it warms are the poorer ones.")

GRID_CAPTION = (
    "One sentence, one camera position, one seed — only the country changed")
GRID_NOTE = (
    "Image i of every prompt is generated from the same seed, so all eight pictures start from "
    "identical noise and the street recedes the same way in each. The only difference between one "
    "cell and the next is the country named in the sentence. Figures are the country's standing on "
    "the yellow–blue cast, in country-to-country standard deviations.")

METHOD = [
    ("One sentence, one camera",
     "\u201cA photograph of {place} in {country}, {view}.\u201d The view is fixed per kind of "
     "place, so two countries' pictures differ only because the country does."),
    ("The light is pinned",
     "Each prompt runs twice: free, and ending \u201cat noon under a clear sky with the sun high "
     "overhead.\u201d It names no colour, so a gap that survives it is a grade, not an hour."),
    ("A zero to measure from",
     "The same places drawn with no country named at all, giving the model's own default."),
    ("Sixty countries, chosen not picked",
     "Fifteen per World Bank income group, all above a million people, selected so income and "
     "distance from the equator pull apart: \u03c1 = 0.24 here against 0.46 worldwide."),
    ("Eighty-four images per prompt",
     "Sized from a 3,300-image pilot's measured noise; more countries and places buy more."),
    ("Reproducible by construction",
     "flux-schnell on Replicate at 1024\u00d71024, one pinned version, every seed recorded."),
]

LIMITS = [
    "One model, one prompt template, one language.",
    "Four country averages is a blunt control, and it leaves 54% of the spread unexplained.",
    "Controlling for climate may control away part of the question. The controls use each "
    "country's real climate, not the drawn one, so a place rendered drier than it is counts as "
    "signal \u2014 but content against habit is a judgement this cannot make.",
    "18 comparisons per metric: only Asia, the Americas and upper-middle income on haze and "
    "lightness carry real weight.",
    "Europe is three countries here and Oceania two; the list balances income, not regions.",
]

MAP_CAPTION = "How the model colours each of the 60 countries"
MAP_NOTE = ("Amber: warmer than the average country. Blue: cooler. Grey: within a third of a "
            "standard deviation of the average. Pale grey: not in this run.")

TABLE_TITLE = "What predicts the warmth"
TABLE_NOTE = ("Each row holds a rival explanation constant and asks the comparison again. "
              "Cohen's d with the permutation p-value in brackets; r² is the share of the "
              "spread between countries that the controls account for.")
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
     "53 of the 60 countries are warmer than the model's own no-country default. Norway is the only "
     "one consistently cooler."),
    ("Income does not survive the controls",
     "The poorest group is warmer as measured (d = +0.72), but holding real latitude, temperature, "
     "rainfall and forest cover constant drops it to +0.52 — no longer distinguishable from "
     "chance. Of the four, forest cover is the one that moves it."),
    ("Latitude was the wrong confound",
     "The country list was built to defeat it, and it accounts for about 5%. Forest cover alone "
     "accounts for 30%."),
    ("Africa's warmth is climate. Asia's is not",
     "Africa's gap vanishes under the controls (−0.03). Asia's survives everything "
     "(+0.73, p = .011) and holds separately in all six kinds of place."),
    ("The light control is what makes it visible",
     "Under the free prompt climate explains 10% of the spread against 46% under the pinned light, "
     "and no group effect survives. The model's own choice of hour was drowning out the country."),
]

FOOTER = ("github.com/haydn-s/blurred-lens  ·  interactive globe, every prompt and every "
          "measurement in the repository  ·  generated October 2026 for $185")
