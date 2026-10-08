# Blurred Lens — 5-minute presentation script

Bullets to speak from, not sentences to read out.

**535 spoken words.** At a normal 145 words a minute that is 3 minutes 40, which is deliberate:
the remaining minute and a bit is for pointing, for the pause at the photographs, and for not
rushing. The timings below are paced so no section needs more than about 145 wpm.

Every figure here is one the poster build verifies against the run (`python -m
deliverables.make_poster --check`), so if a number changes, the check fails before the poster
prints and this script needs the same edit.

*Italics are stage directions — where to point, not what to say.*

---

## The shape of it

| | | |
|---|---|---|
| **0:00 – 0:35** | Why anyone should care | the hook |
| **0:35 – 1:30** | What I built | method |
| **1:30 – 2:55** | What I found | the results |
| **2:55 – 3:55** | What it means | the argument |
| **3:55 – 4:35** | What it cannot show, and what is next | honesty |
| **4:35 – 5:00** | Close | the one sentence they keep |

---

## 0:00 – 0:35 · Why anyone should care

*Stand left of the poster. Do not point yet — let them look at you.*

- Film has a trick. A sepia wash over a scene says "poor, hot, dangerous" before anyone speaks a
  line. Critics call it the Mexico filter.
- Image models learn from pictures like those.
- So: **if a model inherited that habit, every picture it makes of a country carries a quiet
  judgement.** In a textbook, a travel page, a news illustration, a slide deck.
- Nobody chose it. And you cannot see it in any one image — which is exactly why it needs
  measuring rather than eyeballing.
- *Point to the title.* That is what Blurred Lens asks: does the model paint poorer countries
  warmer?

---

## 0:35 – 1:30 · What I built

*Move to the numbers strip.*

- **61,488 generated images.** 60 countries, six kinds of place — city, town, village, house,
  rural, market — 84 images of each.
- Every image from the same sentence: *"A photograph of a city in Nigeria, taken at eye level from
  the middle of a street."* Same camera position every time.
- *Point to section 2, the five steps.* Four things make it a measurement rather than a vibe:
  - **Pinned the light.** Ran every prompt again ending "at noon under a clear sky." It names no
    colour — so warmth that survives it is a grade, not an hour the model happened to pick.
  - **Gave it a zero.** The same places with no country named at all, so I can ask whether a
    country is being warmed, not just who is warmest.
  - **Picked countries that disagree.** Rich countries sit far from the equator and poor ones near
    it, so "poorer" and "nearer the equator" are normally the same sentence. I chose 15 per income
    group so those two pull apart.
  - **Made the rivals compete.** Held each country's real latitude, temperature, rainfall and
    forest cover constant, then asked again.

---

## 1:30 – 2:55 · What I found

*Point to the eight photographs.*

- These eight start from the **same random seed**, so the street recedes identically in all of
  them. The only thing that changed is the country in the sentence. *Pause — let them look.*
- **First finding: it really does grade countries.** 53 of 60 are warmer than the model's own
  no-country default. Norway is the only one consistently cooler.
- **Second: it is not the poor ones — it is the dry ones.** *Point to Saudi Arabia and Kuwait on
  the map, then Costa Rica.* Saudi Arabia and Kuwait are high-income and near the top. Costa Rica
  is high-income and near the bottom. Poverty is not what the warm end has in common.
- **Third, and this is the one that matters.** Measured as it stands, the poorest group really is
  warmer — effect size +0.72, p about .02. Hold climate constant and it drops to +0.52, which is
  no better than chance.
- *Point to the bars.* And of the four rivals, it is **forest cover** that does it — 30% on its
  own. Not heat, not dryness, not latitude.
- **Fourth: latitude was the wrong confound.** I built the entire country list to defeat it. It
  explains **5%**.
- **Fifth: one thing survives everything.** Asia stays warmer than its climate accounts for —
  +0.70, p about .01 — and it holds in all six kinds of place separately. Africa's gap, by
  contrast, vanishes completely once you account for climate.

---

## 2:55 – 3:55 · What it means

*Step back. This is the argument, not more results.*

- **The intuitive version of the claim is wrong.** The model is not warming poor countries. It is
  warming dry, bare ones — which is substantially what those places look like.
- But "substantially" is not "entirely." A regional residual outlives every control I could build.
  North Korea is humid and half forested and still the warmest thing on the map.
- **The method mattered more than the result, and that is the Responsible AI point.** Measured
  naively, the income effect was there at p ≈ .02. It did not survive a control for how green a
  country is. **An audit without that control would have published it** — and "AI model is biased
  against poor countries" is a headline that travels.
- Second methodological point: **a measurement needs a zero.** Ranking countries against each
  other tells you who is warmest. Only the no-country baseline tells you whether anyone is being
  warmed at all — and 53 of 60 are.
- So the contribution is not only the finding. It is a reproducible way to ask the question: fixed
  prompt, pinned light, a baseline, and rival explanations that have to compete.

---

## 3:55 – 4:35 · What it cannot show, and what is next

*Point to section 5. Say this plainly — it is not a disclaimer, it is part of the work.*

- **One model, one prompt template, one language.** This is one model's habit, not the industry's.
- **The controls are blunt.** Straight lines on four country averages cannot separate a stereotype
  from a climate — only say whether a pattern needs more than climate to describe it. They leave
  **54% unexplained**, and a better climate measure might absorb the Asia effect too.
- **Controlling for climate may control away part of the question.** If drawing a country barer
  than it is *is* the stereotype, the control absorbs some of what I came to find. I used each
  country's *real* climate, not the drawn one, so a place rendered drier than it is still counts
  as signal — but that line is a judgement this method cannot make for you.
- **Next:** why Asia. That residual is the finding that now needs a mechanism. After that: other
  models and languages, and content rather than colour — who is in the frame, what they are doing.

---

## 4:35 – 5:00 · Close

- So the honest headline is not *the model grades poor countries warmer*.
- It is: **the model grades dry, bare countries warmer — and it draws Asia warmer than any climate
  explains.**
- Everything is reproducible: every prompt, every seed, every measurement is in the repository.
  61,488 images for $185.
- *Point to the footer.* Happy to take questions.

---

## If you only get 90 seconds

Poster sessions are interruptions. The compressed version:

- Film uses a yellow filter to say "poor and dangerous." I asked whether an image model learned it.
- 61,488 images, 60 countries, same sentence, same camera.
- It does grade countries — 53 of 60 come out warmer than its own default picture of a place.
- But it tracks how dry and bare a country is, not how poor. Saudi Arabia is high-income and near
  the top.
- The income effect was there at p ≈ .02 until I controlled for vegetation. An audit without that
  control would have published it.
- What survives everything is regional: Asia is drawn warmer than its climate explains.

---

## Questions to expect

**"Isn't it just drawing deserts accurately?"**
Substantially, yes — and that is the finding. It is why the income claim does not hold up. But
climate does not explain all of it: Asia keeps its gap after latitude, temperature, rainfall and
forest cover are held constant, and North Korea is humid and half forested.

**"Why only 60 countries?"**
Countries are the unit of the statistical test, so more is better for power — but the supply of hot
rich countries and cool poor ones runs out. Past 60, income and latitude re-entangle and I would be
buying power by giving back the thing the design exists to establish.

**"Why this model?"**
Cost. flux-schnell is $0.003 an image, which is what made 61,488 of them affordable on a student
budget. The method is not specific to it — that is the point of pinning the model version and
recording every seed.

**"Could the prompt be causing it?"**
That is what the fixed sentence and the no-country baseline are for. Every country gets the same
words in the same order, and the baseline shows what the sentence produces with no country at all.

**"How do you know it is a filter and not the content?"**
Strictly, I do not — a dry place genuinely looks dry, and I say so on the poster. What I can say is
that the gaps survive pinning the light, hold across six different kinds of scene at once, and in
Asia's case survive the climate controls too.

---

## Delivery notes

- The photographs do the persuading. Give them a real pause — three or four seconds of silence
  while people look is worth more than another sentence.
- Say the numbers that are memorable (53 of 60, 5%, 30%) and skip the rest. Nobody retains a
  p-value from a talk; they retain "the thing I designed against turned out to explain 5%."
- If you are running long, cut the *second* methodological point at 2:55 (the zero) and the Costa
  Rica example at 1:30. Do not cut the limitations — they are a scoring requirement and they make
  the rest more credible.
- If you are running short, expand on why forest cover beats aridity: a dry country and a bare
  country are not the same thing, and it is bareness that tracks the warmth.
