<!--
  This file is the text of the website's About page (web/about.html).
  Edit it like any Markdown document; the page shows your changes on the next reload.
-->

# About Blurred Lens

When you ask an AI image model to *"show me a city in Nigeria,"* what does it draw? How does that
compare with what it draws for *"a city in France,"* or *"a farm in Japan"*?

Blurred Lens asks one image model the same simple question about every country on Earth, collects
many answers to each question, and blends them into a single averaged image. The result is a kind of
blurred lens: not any one picture the model made, but the picture it tends to make.

## How it works

1. **One prompt template.** Every image comes from the same sentence, *"Show me {place} in
   {country}."* Only the place and the country change.
2. **Every country, eight kinds of place.** 197 countries (the 193 UN member states, the two UN
   observer states, Taiwan and Kosovo) times eight places (a city, a town, a village, a suburb, a
   rural area, a farm, a house and a market) makes 1,576 prompts.
3. **Many samples per prompt.** An image model gives a different answer every time, so each prompt
   is sent many times. The collection reflects the model's habits rather than one lucky or unlucky draw.
4. **Averaging.** The images for each prompt are resized and combined pixel by pixel into two composites:
   - the **mean**, the literal average, which looks soft and ghostly;
   - the **median**, which keeps what most images agree on and is usually sharper.

On the globe, click a country to see its composites, the exact prompt behind each one, and some of
the individual images that went into it.

## How to read a composite

- **Sharp shapes and strong colors** mean the model drew the same thing again and again: a skyline,
  a horizon, a dominant palette.
- **Blur and gray** mean the model varied, with different layouts and different subjects.
- **Differences between countries** are the interesting part. When the same prompt yields glass towers
  for one country and dirt roads for another, the composites make that default visible at a glance.

## Why this is an Explainable AI project

Explainable AI usually asks why a model produced a particular output. Blurred Lens asks a
complementary question: what does a model assume when it is given almost nothing to go on? A prompt
like *"a house in {country}"* leaves nearly everything unspecified, so whatever fills the gap
(architecture, weather, wealth, crowds) comes from the model and its training data, not from the
prompt. Averaging many samples turns those assumptions into something you can see and compare.

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
- **Pixel averages ignore meaning.** The same street photographed from two angles averages into a
  blur, so composites show agreement in layout and color rather than in content.
- **A finite sample.** Each composite is built from a limited number of images, so details can shift
  as more are added.
- **Averages flatten variety.** A composite can make a diverse set of images look uniform, which is
  why the individual images are shown next to it.

## Status

> Image generation has not started yet, so any images on the site are placeholders used to design it.
> Update this section as real results come in.

## Credits

Blurred Lens is a class project for AIPI 590: Explainable AI at Duke University. Country shapes come
from [Natural Earth](https://www.naturalearthdata.com/) via
[world-atlas](https://github.com/topojson/world-atlas), and the globe is built with
[globe.gl](https://globe.gl) and [three.js](https://threejs.org).
