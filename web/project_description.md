<!--
  This file is the text of the website's About page (web/about.html).
  Edit it like any Markdown document; the page shows your changes on the next reload.
-->

# About Blurred Lens

When you ask an AI image model to *"show me a city in Nigeria,"* what does it draw? How does that
compare with what it draws for *"a city in France,"* or *"a farm in Japan"*?

Blurred Lens asks one image model the same simple question about country after country, collects many
answers to each question, and measures the color of every one. The result is a kind of blurred lens:
not any one picture the model made, but the habits behind all of them. So far that is 61,488 images
of 60 countries.

## The question

Film has a habit of coloring places. A sepia wash over Mexico, dust and amber for "somewhere
dangerous": a yellow filter tells an audience that a place is poor, hot and unsafe before anyone
speaks a line. An image model trained on pictures like those may have learned the habit too. This
project measures whether it did -- and whether the countries it warms are the poorer ones.

The short answer, from 61,488 images: the model does warm some countries far more than others, and
very few countries escape it. But the countries it warms are mostly the dry, sparsely vegetated ones
rather than the poor ones, and once you account for how green a country actually is, the income
pattern largely dissolves. What does not dissolve is a regional one -- the numbers are under
**What it found**, below.

## How it works

1. **One prompt template, one camera position.** Every image comes from the same sentence, *"A
   photograph of {place} in {country}, {view}."* The place and the country change; the view is fixed
   for each kind of place (for a city, *"taken at eye level from the middle of a street, looking
   straight down the street"*). Every image is also the same size, so all the images of a prompt line
   up and can be compared pixel by pixel.
2. **The light is pinned, too.** The sentence above fixes where the camera stands but not what time
   of day it is -- so a country that measures warm might simply be one the model chose to draw at
   golden hour. Every prompt is therefore run twice: once free, and once ending *"at noon under a
   clear sky with the sun high overhead."* That names no color on purpose. A warmth gap that survives
   it is a grade laid over the frame, not an hour the model picked. This turned out to matter more
   than expected: under the free prompt the country differences are mostly drowned out by the model's
   own choice of hour, and only with the light pinned do they come clear.
3. **There is a zero to measure from.** The same places are also drawn with no country named at all
   -- *"A photograph of a city, taken at eye level..."* -- which gives the model's own default picture
   of a city, a village, a house. A country can then be read as a deviation from that default, and
   not only from the average of the other countries.
4. **Sixty countries, chosen rather than picked.** Fifteen in each World Bank income group. Across
   the world the rich countries sit far from the equator and the poor ones near it, so "warmer because
   poorer" and "warmer because nearer the equator" would be one sentence. This list deliberately
   breaks that: hot rich countries (Singapore, Panama, the Gulf states) against cool or highland poor
   ones (North Korea, Syria, Afghanistan, Uzbekistan, the Ethiopian highlands). Six kinds of place
   each -- a city, a town, a village, a house, a rural area and a market.
5. **Many samples per prompt.** An image model gives a different answer every time, so each prompt is
   sent 84 times. That number comes from measuring how noisy the answers actually are, not from a
   guess. The collection reflects the model's habits rather than one lucky or unlucky draw.
6. **Measuring.** Every image is measured the way a colorist would describe it: the color cast over
   the frame, its warmth in kelvin, how saturated, how dark, how hazy, how much of the picture sits in
   amber against how much sits in blue. Each country's numbers are then compared with every other
   country's for the same kind of place.
7. **Then the obvious objections are tested.** A dry country really does look dustier and a forested
   one greener, so every comparison between groups of countries is run twice: once as measured, and
   once with each country's real latitude, temperature, rainfall and forest cover held constant. A
   pattern that keeps its gap needs more than climate to explain it. One that loses it was tracking
   climate all along.

On the globe, click a country to see how its pictures compare, the exact prompt behind each one, and
some of the individual images the numbers came from.

## How to read a country

- **The figure in σ** says how far this country sits from the average country, measured in
  country-to-country standard deviations. +1.5 is far out; ±0.3 is the middle of the pack.
- **Warmer is lower in kelvin.** 4,000 K is the amber of a late afternoon; 7,000 K is an overcast
  noon. A country graded a thousand kelvin below the rest is being lit differently by the model.
- **Haze** rises with dust, smog and lifted blacks -- the look a film reaches for when it wants a
  place to feel hot and tired.
- **Comparisons stay inside one kind of place.** Cities are compared with cities, never with farms:
  places differ in color for reasons that have nothing to do with which country they are in.
- **"Against the default"** is the same distance measured from the model's picture of that place with
  no country named at all, rather than from the average country. It answers a different question:
  not *who is warmest* but *is this country being warmed at all*.

## Why this is an Explainable AI project

Explainable AI usually asks why a model produced a particular output. Blurred Lens asks a
complementary question: what does a model assume when it is given almost nothing to go on? A prompt
like *"a house in {country}"* leaves nearly everything unspecified, so whatever fills the gap
(architecture, weather, wealth, crowds) comes from the model and its training data, not from the
prompt. Measuring many samples turns those assumptions into something you can count, rather than
something you have to take on faith from a handful of striking examples.

## Decisions that shape the results

- **Country names are written the way people say them,** with articles where English needs them:
  *the Netherlands*, *the Philippines*.
- **The country list is built, not browsed.** Fifteen countries per income group, every one with at
  least a million people, and chosen so that income and distance from the equator pull apart rather
  than together. The population floor matters: without it, the arithmetic that balances latitude best
  fills the rich group with tropical micro-states -- Nauru, Palau, Tuvalu -- which carry none of the
  stereotypes this project is about. Twenty-six countries a reader will look for (the United States,
  Germany, Japan, Brazil, Mexico, China, India, Nigeria, Egypt, Ethiopia, North Korea and others) are
  fixed in the list, and the rest chosen around them.
- **Every image is reproducible.** Image *i* of every prompt is generated from the seed *1000 + i*,
  recorded alongside it. The seed depends on the image number alone, so image 7 of Norway's city,
  Nigeria's city and the no-country baseline all start from the same noise -- the country name is then
  the only thing that differs between them, in the sampling as well as in the sentence. The model
  version is pinned too, so an update part-way through a run stops it rather than quietly changing
  what is being measured.
- **How many images is measured, not guessed.** A pilot of 3,300 images established how noisy one
  country's measurement is against how much countries differ from each other, and the sample size
  follows from that. It also showed that more countries and more kinds of place buy far more than
  more images per prompt do, which is where the budget went.
- **Ambiguous names are made unambiguous:** *the country of Georgia* rather than the US state,
  *Türkiye* rather than the bird, and *Côte d'Ivoire* and *Cabo Verde* so that "coast" and "cape"
  don't leak into the picture.
- **Some combinations have no real-world referent,** such as a farm in Vatican City or a village in
  Singapore. They stay in: what a model does with an impossible request is itself a finding.
- **Refusals are recorded, not hidden.** When the model declines a prompt, that is part of the result.

## What it found

From 61,488 images -- 60 countries, six kinds of place, 84 images each, generated both free and with
the light pinned, plus the no-country baselines. On the yellow-blue cast over the whole frame:

- **Naming a country warms the picture.** 53 of the 60 countries are warmer than the model's own
  no-country default. Norway is the only one consistently cooler. Whatever else is going on, adding a
  country name to *"a photograph of a city"* reliably pushes the result toward amber.
- **The warmest countries are the dry ones.** Niger, Nigeria, Chad, Mali, Saudi Arabia, Somalia,
  Kuwait, India, Bangladesh and Egypt lead; Norway, Australia, Costa Rica, the United States and
  South Africa trail. Saudi Arabia and Kuwait are high-income countries sitting near the top, which
  is the first sign that poverty is not what the top of this list has in common.
- **It is a grade, not a scene choice.** The gaps are much the same in all six kinds of place and
  move together, which is what a cast laid over a whole frame looks like rather than one odd scene.
- **Income does not survive the controls.** Measured as it stands, the poorest group is warmer than
  the rest (effect size +0.72). Hold each country's real latitude, temperature, rainfall and forest
  cover constant and that falls to +0.52, which is no longer distinguishable from chance. Of those
  four, **forest cover is the one that does the work** -- not dryness, not heat, not latitude. The
  income pattern was largely standing on how green a country is.
- **Latitude, the objection we built the whole country list to defeat, turned out to be nearly
  irrelevant** -- it accounts for about 5% of the differences between countries. Forest cover alone
  accounts for 30%, mean temperature 25%, rainfall 18%, and the four together 46%.
- **Africa's warmth is climate. Asia's is not.** Africa's gap disappears completely under the
  controls. Asia's survives everything, holds separately in all six kinds of place, and is the one
  effect in this data that climate cannot account for. The largest individual residuals are North
  Korea, China, Nigeria, India and Bangladesh -- and North Korea is a humid, half-forested country,
  so nothing about its climate explains why it is drawn the way it is. Japan is the subtlest case: it
  is cool in absolute terms, yet warmer than a country that wet and wooded should be.

So the honest headline is not *the model grades poor countries warmer*. It is *the model grades dry,
bare countries warmer -- and Asian countries warmer than their climate accounts for*.

## Limitations

- **One model, one template, one language.** Other models, phrasings or languages could paint very
  different pictures.
- **A warm picture is not proof of a warm filter.** A sunset really in frame is warm content, and from
  one image it looks much like a grade laid over everything. Pinning the light and finding the gaps
  still there, in all six kinds of place at once, is the strongest answer available here -- but it is
  circumstantial, not a look inside the model.
- **Some places really are sunnier, and the controls are blunt.** Holding real latitude, temperature,
  rainfall and forest cover constant is a straight-line fit on four country averages. It cannot tell
  a stereotype from a climate; it can only say whether a pattern needs more than climate to describe
  it. Those four leave 54% of the differences between countries unexplained, and a better climate
  measure might absorb more of what is left -- including the Asia effect.
- **Controlling for climate may control away part of the question.** If drawing a country drier than
  it is *is* the stereotype, then holding climate constant removes some of what we came to find. The
  controls use each country's *real* climate, not the drawn one, precisely so that a place rendered
  more barren than it is counts as signal -- but the line between "legitimate content" and "learned
  habit" is a judgement this method cannot make for you.
- **The groups are not clean.** Income group and world region overlap: most of the upper-middle-income
  countries here are in the Americas, so an "income" result and a "region" result are hard to tell
  apart. The regional findings should be read as the more solid of the two.
- **The framing is chosen for the model.** Fixing the view makes images comparable, but the model
  never gets to show how it would frame a place on its own.
- **Color is not content.** These measurements describe light, not what is in the picture: who is
  present, what they are doing, whether the buildings are whole. That is the next question, not this one.
- **Many comparisons.** Sixty countries is enough to detect a large effect about three times in four,
  not enough to be confident about a modest one. And each metric is tested against both income and
  region, before and after the controls -- 18 comparisons per metric. At that rate a p-value around
  0.05 means very little, so only the strongest results here (Asia, the Americas, and the
  upper-middle-income group on haze and lightness) carry real weight. The report prints its own
  comparison count for exactly this reason.
- **One region's result rests on three countries.** Europe is represented by three countries in this
  list and Oceania by two, because the list was built to balance income against latitude rather than
  to cover regions evenly. Treat those two rows as decoration.

## Status

> **Generation is complete.** 61,488 images were made in October 2026 with
> `black-forest-labs/flux-schnell` on [Replicate](https://replicate.com), pinned to one model
> version, at 1024x1024, with a recorded seed for every image so any single one can be made again.
> 60 countries x 6 places x 84 images, under both the free and the light-controlled prompt, plus a
> no-country baseline for each. Not one request failed and not one prompt was refused.
>
> The findings above come from that run, and are a first pass: the measurements are final, the
> interpretation is not. **The globe and galleries have not been rebuilt from it yet** -- the images
> and figures they show are still the synthetic placeholders used to design the site, and will be
> replaced when `export_site` is next run.

## Credits

Blurred Lens is a class project for AIPI 590: Explainable AI at Duke University. Country shapes come
from [Natural Earth](https://www.naturalearthdata.com/) via
[world-atlas](https://github.com/topojson/world-atlas), and the globe is built with
[globe.gl](https://globe.gl) and [three.js](https://threejs.org).
