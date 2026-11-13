# KrillBench

How well do frontier models play Krillion? Scored against the official answer sheets:
350 prompts, dives #72 to #121 (Sep 25 to Nov 13, 2026). Standard library Python only.

## Setup

1. `cp models.example.json models.json` and fill in your deployments. Delete models you don't have.
   A model only runs the reasoning levels listed under its `levels`.
2. Keys, as needed: `export AZURE_API_KEY=...`, `export GEMINI_API_KEY=...`.
   Claude runs through your logged-in Claude Code (`claude` on PATH), no key.
3. Azure: deploy only models marked **Direct from Azure** (credits don't cover partner-billed models).
   Never deploy Claude on Azure; use Claude Code.
4. Claude Code check, once: `claude --help` should list `--system-prompt`, `--disallowedTools`,
   `--output-format`. If a flag name differs, edit `call_claude_code`. A personal `~/.claude/CLAUDE.md`
   still loads, so move it aside during runs.

## Run

```bash
python3 krillbench.py run --limit 20 --conditions rules-off --samples 1    # pilot: check every model works
python3 krillbench.py run                                                   # full plan, resumable
python3 krillbench.py score && python3 krillbench.py report                 # -> report.md, leaderboard.csv
```

Test without any keys: `python3 krillbench.py run --mock --models <file with {"name":"x","backend":"mock"}>`.

## Methodology

**Conditions** (each model, all 350 prompts):

| Condition | Prompt | Reasoning | Samples |
|---|---|---|---|
| rules-off (headline) | Game rules + scoring | off | 3 |
| rules-minimal / low / medium / high / xhigh | Game rules + scoring | each level the model supports | 1 each |
| naive-off | "Answer the prompt", no scoring rules | off | 1 |
| noillirk-off (optional) | "Most common answer" | off | 1 (112 prompts) |

Calls per model: 2,450 (2,562 with Noillirk), more for models with extra levels (minimal, xhigh). Models that can't turn reasoning off run every "off" condition at
their lowest supported level, marked "(at low)" on the leaderboard; their duplicate rules-low run is skipped. The model is asked for its answer only, nothing else.

**One call = one fresh context.** No conversation history, no tools, no web. Samples are independent
calls, not retries.

**Retry policy.** Only infrastructure failures are retried: HTTP 429/5xx, timeouts, connection errors,
Claude Code crashes. Up to 4 retries with backoff of 2, 4, 8, 16 s. A call that still fails is logged as
`infra_failed` and excluded from scoring (rerun to fill it in); it is never scored as 0. Model content is
never retried: an empty reply, a refusal, a list, a wrong answer all count as the model's one answer.
HTTP 4xx config errors stop the run. A prompt blocked by a provider content filter (Azure) is logged as
`filtered` and dropped from scoring for every model. A Claude subscription usage limit stops the run cleanly; rerun later.

**Answer extraction.** Last non-empty line of the reply; strip "Answer:", quotes, markdown, trailing
punctuation. Nothing else is repaired.

**Scoring.** Normalize (accents, case, leading the/a/an, punctuation) and match the sheet. If no exact
match, accept edit distance 1 (2 for 9+ letters) when it hits exactly one tier, like the game's typo
autocorrect. Otherwise 0. Untimed score is the headline; Timed zeroes answers over 25 s (provider
latency is noisy, so it's reported separately). Exact-only shows how much fuzzy matching adds.

**Stats.** Dive Score = mean points x 7, sample 0, 95% bootstrap CI over prompts. Model gaps use paired
bootstrap on shared prompts; a CI crossing zero is reported as a tie.

**Report sections.** Leaderboard; reasoning sweep (score and reasoning tokens per level); rules vs naive
(does knowing the scoring change behavior, and head rate); AI herd effect (how often two models give the
same answer vs chance, self-repetition across samples, overlap with the human crowd's top 10, the most
shared answers); difficulty bands set after the run by the share of models answering invalidly, plus the
hardest prompts; contamination split by model release date.

**Known limits.** The game accepts some unpublished aliases, so sheet scoring slightly undercounts.
Claude via Claude Code is "Claude inside Claude Code", not the raw API model, and its cost column is the
API-equivalent figure it reports, not what you pay.
