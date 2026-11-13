# KrillBench results

Dive Score = mean points per prompt x 7 (0-700), sample 0, 95% bootstrap CI over prompts.
Timed = answers over 25 s score 0. Reference: crowd's #1 answer 163, random valid answer 529.

## Leaderboard (rules, reasoning off)

| Model | n | Dive Score [95% CI] | Timed | Exact-only | Valid | Pts if valid | Head rate | Gems | p50 s | $/dive |
|---|---|---|---|---|---|---|---|---|---|---|
| gpt-6-astra (at low) | 20 | 474 [390, 542] | 474 | 474 | 90% | 75 | 0% | 0.0% | 3.3 | $0.032 |
| gpt-6.1-sol (at low) | 20 | 439 [359, 508] | 439 | 439 | 90% | 70 | 0% | 0.0% | 3.6 | $0.007 |
| grok-4.7 (at minimal) | 20 | 429 [336, 509] | 343 | 429 | 85% | 72 | 0% | 10.0% | 16.0 | $0.040 |
| gpt-6.1-terra | 20 | 340 [234, 436] | 340 | 310 | 80% | 61 | 25% | 0.0% | 1.5 | $0.001 |
| kimi-k3.1-pro | 20 | 282 [187, 378] | 282 | 210 | 70% | 58 | 21% | 0.0% | 4.7 | n/a |
| mistral-large-4 (at low) | 20 | 186 [119, 262] | 186 | 186 | 95% | 28 | 68% | 0.0% | 4.7 | n/a |
| deepseek-v4-pro | 20 | 126 [84, 175] | 126 | 126 | 100% | 18 | 90% | 0.0% | 2.3 | $0.002 |
| deepseek-v4.1-flash | 20 | 126 [80, 178] | 126 | 126 | 90% | 20 | 89% | 0.0% | 2.0 | $0.000 |

\* Claude Code cost is the API-equivalent figure it reports; your subscription is what you pay.
"(at X)": the model can't turn reasoning off, so its headline runs at its lowest supported level X.

### Paired gaps between neighbours (rules-off)

| A | B | A - B [95% CI] |
|---|---|---|
| gpt-6-astra | gpt-6.1-sol | 35 [9, 70] |
| gpt-6.1-sol | grok-4.7 | 10 [-89, 112] tie |
| grok-4.7 | gpt-6.1-terra | 89 [-52, 234] tie |
| gpt-6.1-terra | kimi-k3.1-pro | 58 [-72, 189] tie |
| kimi-k3.1-pro | mistral-large-4 | 96 [0, 192] tie |
| mistral-large-4 | deepseek-v4-pro | 60 [-28, 147] tie |
| deepseek-v4-pro | deepseek-v4.1-flash | 0 [-63, 63] tie |

## Reasoning sweep (rules)

| Model | off | minimal | low | medium | high | xhigh | reasoning tokens (off/minimal/low/medium/high/xhigh) | timed (off/minimal/low/medium/high/xhigh) |
|---|---|---|---|---|---|---|---|---|
| deepseek-v4-pro | 126 [84, 175] | - | - | - | - | - | - / - / - / - / - / - | 126 / - / - / - / - / - |
| deepseek-v4.1-flash | 126 [80, 178] | - | - | - | - | - | - / - / - / - / - / - | 126 / - / - / - / - / - |
| gpt-6-astra | - | - | 474 [390, 542] | - | - | - | - / - / 53 / - / - / - | - / - / 474 / - / - / - |
| gpt-6.1-sol | - | - | 439 [359, 508] | - | - | - | - / - / 57 / - / - / - | - / - / 439 / - / - / - |
| gpt-6.1-terra | 340 [234, 436] | - | - | - | - | - | 0 / - / - / - / - / - | 340 / - / - / - / - / - |
| grok-4.7 | - | 429 [336, 509] | - | - | - | - | - / 898 / - / - / - / - | - / 343 / - / - / - / - |
| kimi-k3.1-pro | 282 [187, 378] | - | - | - | - | - | 0 / - / - / - / - / - | 282 / - / - / - / - / - |
| mistral-large-4 | - | - | 186 [119, 262] | - | - | - | - / - / 507 / - / - / - | - / - / 186 / - / - / - |

## Do the rules change behavior? (naive vs rules, both reasoning off)

| Model | Naive Dive | Rules Dive | Gain [95% CI] | Naive head rate | Rules head rate |
|---|---|---|---|---|---|

## AI herd effect (rules-off, valid answers)

- Two different models give the same answer: **8.0%** of model pairs per prompt (uniform chance from the sheet: 0.37%; 8 prompts, 8 models).
- Self-repeat needs 2+ samples on rules-off.
- Prompts where at least half the models gave the identical answer: **1** of 8.

| Model | Answers in the human crowd's top 10 | n |
|---|---|---|
| deepseek-v4.1-flash | 71% | 7 |
| deepseek-v4-pro | 62% | 8 |
| mistral-large-4 | 57% | 7 |
| kimi-k3.1-pro | 50% | 4 |
| gpt-6-astra | 14% | 7 |
| gpt-6.1-sol | 14% | 7 |
| gpt-6.1-terra | 0% | 7 |
| grok-4.7 | 0% | 6 |

Most shared answers:

| Prompt | Answer (normalized) | Models |
|---|---|---|
| Name a part of a fruit | endocarp | 4 |

## Difficulty (bands set by the share of models that answered invalidly)

| Model | easy | medium | hard |
|---|---|---|---|
| deepseek-v4-pro | 93 | 70 | 192 |
| deepseek-v4.1-flash | 117 | 117 | 140 |
| gpt-6-astra | 478 | 537 | 424 |
| gpt-6.1-sol | 449 | 508 | 381 |
| gpt-6.1-terra | 321 | 438 | 280 |
| grok-4.7 | 525 | 309 | 446 |
| kimi-k3.1-pro | 443 | 414 | 61 |
| mistral-large-4 | 210 | 268 | 105 |

Hardest prompts:

| Prompt | Models invalid |
|---|---|
| Name a recurring household bill | 62% |
| Name a driving or traffic offence | 38% |
| Name a villain from Star Wars, DC, or Lord of the Rings | 25% |
| Name a high-protein food ingredient—at least 8g of protein per 100g. | 25% |
| Name a city south of the equator with over 100,000 people (by metro ar | 12% |
| Name an animal whose name ends in Y | 12% |
| Name a word that starts with “boo” | 12% |
| Name an animal whose name is exactly four letters long | 12% |
| Name a music release type or format (like an album or CD) | 12% |
| Name a shampoo brand | 12% |

## Contamination check (rules-off): dives before vs after release

| Model | Released | Older dives (n) | Post-release dives (n) |
|---|---|---|---|
| gpt-6-astra | 2026-09-03 | - (0) | 474 (20) |
| gpt-6.1-sol | 2026-09-29 | 420 (1) | 440 (19) |
| grok-4.7 | 2026-10-05 | 420 (3) | 430 (17) |
| gpt-6.1-terra | 2026-10-26 | 280 (12) | 429 (8) |
| kimi-k3.1-pro | 2026-11-04 | 331 (17) | 0 (3) |
| mistral-large-4 | 2026-10-19 | 175 (8) | 192 (12) |
| deepseek-v4-pro | 2026-04-23 | - (0) | 126 (20) |
| deepseek-v4.1-flash | 2026-10-17 | 96 (8) | 146 (12) |

Answers scored: 160. Calls needing a retry: 0. Total spend (real, list price; n/a models excluded): $0.23.
