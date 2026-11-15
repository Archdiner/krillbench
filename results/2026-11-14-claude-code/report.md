# KrillBench results

Dive Score = mean points per prompt x 7 (0-700), sample 0, 95% bootstrap CI over prompts.
Timed = same answers, but any whose processing time (wall time minus measured network overhead) exceeds 25 s scores 0. Nothing is cut off. Reference: crowd's #1 answer 163, random valid answer 529.

## Leaderboard (rules, reasoning off)

| Model | n | Dive Score [95% CI] | Timed | Exact-only | Valid | Pts if valid | Head rate | Gems | proc p50 / p90 s | over 25 s | $/dive |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-opus | 350 | 369 [352, 386] | 369 | 364 | 95% | 55 | 30% | 2.3% | 3.0 / 4.4 | 0% | $0.212* |
| claude-sonnet | 350 | 274 [256, 293] | 274 | 265 | 89% | 44 | 50% | 0.0% | 1.5 / 2.5 | 0% | $0.097* |
| claude-haiku | 350 | 149 [134, 164] | 149 | 144 | 91% | 23 | 82% | 0.0% | 2.6 / 3.8 | 0% | $0.006* |

\* Claude Code cost is the API-equivalent figure it reports; your subscription is what you pay.

## Leaderboard, timed (25 s clock on processing time)

| Model | Timed Dive [95% CI] | Untimed | Lost to clock | over 25 s | proc p50 / p90 s |
|---|---|---|---|---|---|
| claude-opus | 369 [352, 386] | 369 | 0 | 0% | 3.0 / 4.4 |
| claude-sonnet | 274 [256, 293] | 274 | 0 | 0% | 1.5 / 2.5 |
| claude-haiku | 149 [134, 164] | 149 | 0 | 0% | 2.6 / 3.8 |
"(at X)": the model can't turn reasoning off, so its headline runs at its lowest supported level X.

### Paired gaps between neighbours (rules-off)

| A | B | A - B [95% CI] |
|---|---|---|
| claude-opus | claude-sonnet | 94 [73, 116] |
| claude-sonnet | claude-haiku | 126 [102, 148] |

## Reasoning sweep (rules)

| Model | off | minimal | low | medium | high | xhigh | reasoning tokens (off/minimal/low/medium/high/xhigh) | timed (off/minimal/low/medium/high/xhigh) |
|---|---|---|---|---|---|---|---|---|
| claude-haiku | 149 [134, 164] | - | 146 [131, 162] | 138 [124, 154] | 149 [134, 165] | - | 256 / - / 264 / 265 / 247 / - | 149 / - / 146 / 138 / 149 / - |
| claude-opus | 369 [352, 386] | - | 365 [348, 383] | 358 [340, 375] | 362 [344, 380] | - | 132 / - / 127 / 128 / 128 / - | 369 / - / 365 / 358 / 362 / - |
| claude-sonnet | 274 [256, 293] | - | 260 [240, 280] | 265 [247, 284] | 265 [246, 283] | - | 7 / - / 8 / 8 / 7 / - | 274 / - / 259 / 265 / 260 / - |

## Do the rules change behavior? (naive vs rules, both reasoning off)

| Model | Naive Dive | Rules Dive | Gain [95% CI] | Naive head rate | Rules head rate |
|---|---|---|---|---|---|
| claude-haiku | 102 | 149 | +47 [+29, +65] | 95% | 82% |
| claude-opus | 86 | 369 | +283 [+266, +300] | 99% | 30% |
| claude-sonnet | 90 | 274 | +184 [+165, +204] | 98% | 50% |

## AI herd effect (rules-off, valid answers)

- Two different models give the same answer: **10.3%** of model pairs per prompt (uniform chance from the sheet: 0.62%; 320 prompts, 3 models).
- A model repeats its own answer across samples: **48.2%**.
- Prompts where at least half the models gave the identical answer: **79** of 320.

| Model | Answers in the human crowd's top 10 | n |
|---|---|---|
| claude-haiku | 66% | 99 |
| claude-sonnet | 43% | 100 |
| claude-opus | 25% | 106 |

Most shared answers:

| Prompt | Answer (normalized) | Models |
|---|---|---|
| Name a shade of red (pinks don't count) | vermilion | 3 |
| Name a stand-up comedian | mitchhedberg | 3 |
| Name a hotel brand | kimpton | 3 |
| Name a vehicle that doesn't travel on wheels | hovercraft | 3 |
| Name a country that has been colonized by Spain or Port | equatorialguinea | 3 |
| Name an invention that existed before 1500 (no food or  | astrolabe | 3 |
| Name a country with three syllables (English pronunciat | tuvalu | 2 |
| Name an international airport (must say full name) | ninoyaquinointernationalairport | 2 |
| Name a deodorant brand | mitchum | 2 |
| Name a career in finance | actuary | 2 |
| Name a type of card (like a birthday card or a library  | tarotcard | 2 |
| Name a superpower Superman has in the comics or movies | heatvision | 2 |
| Name something used to block the sun | parasol | 2 |
| Name an item of formal wear (clothing and shoes, not je | cummerbund | 2 |
| Name a symbol or shape that appears on a national flag  | crescent | 2 |

## Difficulty (bands set by the share of models that answered invalidly)

| Model | easy | medium | hard |
|---|---|---|---|
| claude-haiku | 141 | 175 | 131 |
| claude-opus | 371 | 394 | 342 |
| claude-sonnet | 307 | 311 | 206 |

Hardest prompts:

| Prompt | Models invalid |
|---|---|
| Name a type of dress | 100% |
| Name a way to prepare potatoes | 100% |
| Name a type of table (the furniture) | 100% |
| Name a standard type of insurance policy (all vehicles count as one ty | 100% |
| Name a branch or denomination of Christianity, Islam, Hinduism, Judais | 67% |
| Name something players aim at to score in a sport (like a hoop). | 67% |
| Name a type of balloon (it's my birthday) | 67% |
| Name a food or drink that has an emoji | 67% |
| Name something traditionally expressed as a percentage (like body fat) | 67% |
| Name something you shake before using it | 67% |

## Contamination check (rules-off): dives before vs after release

| Model | Released | Older dives (n) | Post-release dives (n) |
|---|---|---|---|
| claude-opus | 2026-09-22 | - (0) | 369 (350) |
| claude-sonnet | 2026-09-28 | 321 (28) | 270 (322) |
| claude-haiku | 2026-10-07 | 139 (91) | 152 (259) |

Answers scored: 7350. Calls needing a retry: 18. Total spend (real, list price; n/a models excluded): $0.00.
