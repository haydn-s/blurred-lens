<!--
  This file is the text of the website's About page (web/about.html).
  Edit it like any Markdown document; the page shows your changes on the next reload.
-->

# About Blurred Lens

When you ask an AI image model to *"show me a city in Nigeria,"* what does it draw? How does that
compare with what it draws for *"a city in France,"* or *"a farm in Japan"*?

Blurred Lens asks one image model the same simple question about every country on Earth, collects
many answers to each question, and measures the color of every one. The result is a kind of blurred
lens: not any one picture the model made, but the habits behind all of them.

## The question

Film has a habit of coloring places. A sepia wash over Mexico, dust and amber for "somewhere
dangerous": a yellow filter tells an audience that a place is poor, hot and unsafe before anyone
speaks a line. An image model trained on pictures like those may have learned the habit too. This
project measures whether it did -- and whether the countries it warms are the poorer ones.

## How it works

1. **One prompt template, one camera position.** Every image comes from the same sentence, *"A
   photograph of {place} in {country}, {view}."* The place and the country change; the view is fixed
   for each kind of place (for a city, *"taken at eye level from the middle of a street, looking
   straight down the street"*). Every image is also the same size, so all the images of a prompt line
   up and can be compared pixel by pixel.
2. **Every country, eight kinds of place.** 197 countries (the 193 UN member states, the two UN
   observer states, Taiwan and Kosovo) times eight places (a city, a town, a village, a suburb, a
   rural area, a farm, a house and a market) makes 1,576 prompts.
3. **Many samples per prompt.** An image model gives a different answer every time, so each prompt
   is sent many times. The collection reflects the model's habits rather than one lucky or unlucky draw.
4. **Measuring.** Every image is measured the way a colorist would describe it: the color cast over
   the frame, its warmth in kelvin, how saturated, how dark, how hazy, how much of the picture sits in
   amber against how much sits in blue. Each country's numbers are then compared with every other
   country's for the same kind of place.

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
- **Ambiguous names are made unambiguous:** *the country of Georgia* rather than the US state,
  *Türkiye* rather than the bird, and *Côte d'Ivoire* and *Cabo Verde* so that "coast" and "cape"
  don't leak into the picture.
- **Some combinations have no real-world referent,** such as a farm in Vatican City or a village in
  Singapore. They stay in: what a model does with an impossible request is itself a finding.
- **Refusals are recorded, not hidden.** When the model declines a prompt, that is part of the result.

## Limitations

- **One model, one template, one language.** Other models, phrasings or languages could paint very
  different pictures.
- **A warm picture is not proof of a warm filter.** A sunset really in frame is warm content, and from
  one image it looks much like a grade laid over everything. What the numbers can say is that two
  countries' pictures of the same place, from the same prompt and the same camera position, differ --
  and that the country name is the only thing that changed.
- **Some places really are sunnier.** Lagos sits closer to the equator than Oslo. This project cannot
  separate a stereotype from a climate; it can show whether the pattern follows income more closely
  than it follows latitude.
- **The framing is chosen for the model.** Fixing the view makes images comparable, but the model
  never gets to show how it would frame a place on its own.
- **Color is not content.** These measurements describe light, not what is in the picture: who is
  present, what they are doing, whether the buildings are whole. That is the next question, not this one.
- **Many comparisons, small samples.** With a dozen countries and several metrics, some gap will look
  significant by chance. The report prints how many comparisons it made, for exactly that reason.

## Status

> Image generation has not started yet, so any images on the site are placeholders used to design it.
> Update this section as real results come in.

## Credits

Blurred Lens is a class project for AIPI 590: Explainable AI at Duke University. Country shapes come
from [Natural Earth](https://www.naturalearthdata.com/) via
[world-atlas](https://github.com/topojson/world-atlas), and the globe is built with
[globe.gl](https://globe.gl) and [three.js](https://threejs.org).
