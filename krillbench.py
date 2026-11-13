#!/usr/bin/env python3
"""KrillBench: score LLMs at Krillion against the official answer sheets.

  run     query models, append to runs/<model>__<condition>.jsonl (resumable)
  score   score every run against the sheet -> scored.jsonl
  report  leaderboard, reasoning sweep, herd analysis, difficulty -> report.md

Backends (set per model in models.json): azure, claude_code, gemini, openrouter.
Standard library only. --mock runs the whole pipeline with a fake model.
See METHODOLOGY in README.md for the rules this file implements.
"""
import argparse, concurrent.futures as cf, csv, itertools, json, os, random, re, shutil
import statistics as st, subprocess, sys, tempfile, threading, time, unicodedata
import urllib.error, urllib.request
from pathlib import Path

TIER_PTS = {"plankton": 10, "too_clever": 15, "schooler": 30, "rare": 60, "deep_cut": 85, "gem": 100}
CLOCK_S = 25.0
LEVELS = ["off", "low", "medium", "high"]

# ------------------------------------------------------------------ conditions
RULES = """You are playing Krillion, a daily trivia game. Name ONE answer to the prompt.
An answer that is not on the game's accepted list scores 0. Accepted answers score by rarity:
Plankton 10 (what everyone says), Schooler 30, Rare 60, Deep Cut 85, One in a Krillion 100
(one designated gem). Rarer valid answers score more, but an invalid answer scores nothing.
Reply with only your answer: no explanation, no punctuation, no quotes."""

NAIVE = """Answer the prompt with ONE answer.
Reply with only your answer: no explanation, no punctuation, no quotes."""

NOILLIRK = """Name the ONE answer to the prompt that the largest number of other people would also give.
Reply with only your answer: no explanation, no punctuation, no quotes."""

# condition name -> (system prompt, reasoning level, default samples, prompt filter)
CONDITIONS = {
    "rules-off": (RULES, "off", 3, None),
    "rules-low": (RULES, "low", 1, None),
    "rules-medium": (RULES, "medium", 1, None),
    "rules-high": (RULES, "high", 1, None),
    "naive-off": (NAIVE, "off", 1, None),
    "noillirk-off": (NOILLIRK, "off", 1, "crowd"),   # optional, 112 prompts with player data
}
DEFAULT_PLAN = ["rules-off", "rules-low", "rules-medium", "rules-high", "naive-off"]


def headline_level(m):
    """The "off" conditions run at the model's lowest configured level (models that can't disable reasoning)."""
    return next((lv for lv in LEVELS if lv in m.get("levels", {})), "off")

# ------------------------------------------------------------------ data

def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower().strip()
    s = re.sub(r"^(the|a|an)\s+", "", s)
    return re.sub(r"[^a-z0-9]", "", s)


def edit_le(a, b, lim):
    """True if Levenshtein(a, b) <= lim (banded DP with early exit)."""
    if abs(len(a) - len(b)) > lim:
        return False
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [lim + 1] * (len(b) + 1)
        cur[0] = i
        for j in range(max(1, i - lim), min(len(b), i + lim) + 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != b[j - 1]))
        if min(cur) > lim:
            return False
        prev = cur
    return prev[-1] <= lim


class Sheet:
    """One prompt's accepted answers: normalized answer -> tier (higher tier wins on collisions)."""
    def __init__(self, p):
        self.tier = {}
        for t, x in p["tiers"].items():
            for a in x["answers"]:
                k = norm(a)
                if k and (k not in self.tier or TIER_PTS[t] > TIER_PTS[self.tier[k]]):
                    self.tier[k] = t
        for g in p["one_in_a_krillion"]["answers"]:
            self.tier[norm(g)] = "gem"
        self.by_len = {}
        for k in self.tier:
            self.by_len.setdefault(len(k), []).append(k)
        self.crowd = [(norm(a["answer"]), parse_typed(a["times_typed"]))
                      for a in p.get("most_common_player_answers") or []]

    def lookup(self, answer):
        """-> (tier | None, 'exact' | 'fuzzy' | 'ambiguous' | 'none')"""
        k = norm(answer)
        if not k:
            return None, "none"
        if k in self.tier:
            return self.tier[k], "exact"
        if len(k) < 5:
            return None, "none"
        lim = 1 if len(k) < 9 else 2
        hits = {self.tier[c] for L in range(len(k) - lim, len(k) + lim + 1)
                for c in self.by_len.get(L, ()) if edit_le(k, c, lim)}
        if len(hits) == 1:
            return hits.pop(), "fuzzy"
        return None, ("ambiguous" if hits else "none")


def parse_typed(s):
    s = str(s).strip().upper().replace(",", "")
    mult = 1e3 if s.endswith("K") else 1e6 if s.endswith("M") else 1
    try:
        return float(s.rstrip("KM")) * mult
    except ValueError:
        return 0.0


def load_prompts(path):
    d = json.load(open(path))
    return [{"id": f"{day['date']}#{p['n']}", "date": day["date"], "text": p["text"], "raw": p}
            for day in d["days"] for p in day["prompts"]]


def clean_answer(text):
    """Model reply -> one answer. Takes the last non-empty line (after any visible reasoning),
    strips 'Answer:' prefixes, quotes, trailing punctuation. Multi-answer lists are not split:
    they will simply fail to match the sheet."""
    lines = [l.strip() for l in (text or "").strip().splitlines() if l.strip()]
    if not lines:
        return None
    a = re.sub(r"^(final\s+)?answer\s*[:\-]\s*", "", lines[-1], flags=re.I)
    a = a.strip().strip("*`\"'“”‘’").strip().rstrip(".!")
    return a or None

# ------------------------------------------------------------------ backends


class InfraError(Exception):
    """Transport/provider failure: eligible for retry. Never raised for model content."""


class QuotaExhausted(Exception):
    """Subscription or daily quota hit: stop the run cleanly, resume later."""


def http_json(url, body, headers, timeout=300):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        msg = e.read().decode(errors="ignore")[:400]
        if e.code in (429, 500, 502, 503, 504, 529):
            raise InfraError(f"HTTP {e.code}: {msg}")
        raise RuntimeError(f"HTTP {e.code}: {msg}")   # 4xx config errors: fail loudly, don't retry
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        raise InfraError(repr(e))


def call_openai_compatible(url, headers, m, system, prompt, level_cfg):
    body = {"model": m.get("deployment") or m["model"],
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            **m.get("body", {}), **level_cfg}
    t0 = time.time()
    j = http_json(url, body, headers)
    dt = time.time() - t0
    u = j.get("usage") or {}
    det = u.get("completion_tokens_details") or {}
    return {"text": j["choices"][0]["message"].get("content") or "", "latency_s": dt,
            "in_tok": u.get("prompt_tokens"), "out_tok": u.get("completion_tokens"),
            "reasoning_tok": det.get("reasoning_tokens"), "cost": u.get("cost")}


def call_azure(m, system, prompt, level_cfg):
    return call_openai_compatible(m["endpoint"], {"api-key": os.environ[m.get("key_env", "AZURE_API_KEY")]},
                                  m, system, prompt, level_cfg)


def call_openrouter(m, system, prompt, level_cfg):
    return call_openai_compatible("https://openrouter.ai/api/v1/chat/completions",
                                  {"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"},
                                  {**m, "body": {"usage": {"include": True}, **m.get("body", {})}},
                                  system, prompt, level_cfg)


def call_gemini(m, system, prompt, level_cfg):
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/{m['model']}:generateContent"
           f"?key={os.environ[m.get('key_env', 'GEMINI_API_KEY')]}")
    body = {"systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {**m.get("generation", {}), **level_cfg}}
    t0 = time.time()
    j = http_json(url, body, {})
    dt = time.time() - t0
    cand = (j.get("candidates") or [{}])[0]
    parts = (cand.get("content") or {}).get("parts") or []
    text = "\n".join(p.get("text", "") for p in parts if not p.get("thought"))
    u = j.get("usageMetadata") or {}
    return {"text": text, "latency_s": dt, "in_tok": u.get("promptTokenCount"),
            "out_tok": u.get("candidatesTokenCount"), "reasoning_tok": u.get("thoughtsTokenCount"), "cost": None}


CLAUDE_DENY = "Bash,Edit,Write,MultiEdit,Read,Glob,Grep,WebSearch,WebFetch,Task,TodoWrite,NotebookEdit"


def call_claude_code(m, system, prompt, level_cfg):
    """One headless Claude Code call = one fresh session (isolated). Runs in an empty temp dir
    so no project CLAUDE.md loads. Thinking budget via MAX_THINKING_TOKENS."""
    exe = shutil.which("claude") or "claude"
    cmd = [exe, "-p", prompt, "--model", m["model"], "--output-format", "json",
           "--system-prompt", system, "--max-turns", "1", "--disallowedTools", CLAUDE_DENY,
           *m.get("extra_args", [])]
    env = {**os.environ, **{k: str(v) for k, v in level_cfg.items()}}
    with tempfile.TemporaryDirectory() as cwd:
        t0 = time.time()
        try:
            p = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=600)
        except subprocess.TimeoutExpired:
            raise InfraError("claude timeout")
        wall = time.time() - t0
    out = (p.stdout or "").strip()
    try:
        j = json.loads(out.splitlines()[-1]) if out else {}
    except json.JSONDecodeError:
        j = {}
    blob = (out + p.stderr).lower()
    if ("usage limit" in blob or "limit reached" in blob) and (j.get("is_error") or p.returncode != 0):
        raise QuotaExhausted(blob[:300])
    if p.returncode != 0 or j.get("is_error") or "result" not in j:
        raise InfraError(f"claude rc={p.returncode}: {blob[:300]}")
    u = j.get("usage") or {}
    api_s = (j.get("duration_api_ms") or 0) / 1000
    return {"text": j["result"], "latency_s": api_s or wall, "in_tok": u.get("input_tokens"),
            "out_tok": u.get("output_tokens"),
            # Claude Code reports no separate thinking count; output tokens = thinking + a few answer tokens
            "reasoning_tok": u.get("output_tokens"),
            "cost": j.get("total_cost_usd"), "cost_is_notional": True}


def call_mock(m, system, prompt_raw, level):
    """Fake model for pipeline tests: more thinking -> more valid, rarer; naive -> head-heavy."""
    rng = random.Random(hash((m["name"], prompt_raw["text"], level, time.time_ns())) & 0xFFFFFFFF)
    lvl = LEVELS.index(level)
    if rng.random() < 0.16 - 0.03 * lvl:
        return {"text": "Zxqvbnm", "latency_s": 0.5, "in_tok": 0, "out_tok": 0, "reasoning_tok": 0, "cost": 0.0}
    head = system is not RULES
    w = [0.45, 0.3, 0.15, 0.1] if head else [0.3 - 0.06 * lvl, 0.3, 0.2 + 0.03 * lvl, 0.2 + 0.03 * lvl]
    t = rng.choices(["plankton", "schooler", "rare", "deep_cut"], w)[0]
    pool = prompt_raw["tiers"][t]["answers"] or prompt_raw["tiers"]["deep_cut"]["answers"]
    ans = rng.choice(pool[:30])
    if rng.random() < 0.05 and len(ans) > 6:
        ans = ans[:-1]   # occasional typo, exercises fuzzy matching
    return {"text": f"Answer: {ans}.", "latency_s": 2 + 8 * lvl * rng.random(), "in_tok": 0,
            "out_tok": 0, "reasoning_tok": 0, "cost": 0.0}


BACKENDS = {"azure": call_azure, "openrouter": call_openrouter, "gemini": call_gemini,
            "claude_code": call_claude_code}

# ------------------------------------------------------------------ run (with retry policy)

RETRIES = 4            # infra errors only; backoff 2, 4, 8, 16 s (+ jitter)


def call_with_retry(m, system, p, level, level_cfg, mock):
    attempts, last = 0, None
    for attempts in range(1, RETRIES + 2):
        try:
            if mock:
                return call_mock(m, system, p["raw"], level), attempts, None
            return BACKENDS[m["backend"]](m, system, p["text"], level_cfg), attempts, None
        except InfraError as e:
            last = str(e)
            if attempts <= RETRIES:
                time.sleep(2 ** attempts + random.random())
    return None, attempts, last


class Budget:
    def __init__(self, cap):
        self.cap, self.spent, self.lock = cap, 0.0, threading.Lock()

    def add(self, x):
        with self.lock:
            self.spent += x or 0.0

    def over(self):
        return self.cap is not None and self.spent >= self.cap


def cmd_run(a):
    prompts = load_prompts(a.data)
    if a.limit:
        prompts = random.Random(0).sample(prompts, min(a.limit, len(prompts)))
    models = json.load(open(a.models))
    if a.only:
        models = [m for m in models if m["name"] in a.only.split(",")]
    plan = a.conditions.split(",") if a.conditions else DEFAULT_PLAN
    budget, stop = Budget(a.max_usd), threading.Event()
    Path(a.out).mkdir(exist_ok=True)
    for m in models:
        for cond in plan:
            system, level, samples, filt = CONDITIONS[cond]
            if a.samples is not None:
                samples = a.samples if cond == "rules-off" else 1
            levels = m.get("levels", {})
            floor = headline_level(m)
            if level == "off":
                level = floor
            elif cond.startswith("rules-") and level == floor:
                print(f"skip {m['name']} / {cond}: same config as its rules-off headline")
                continue
            if not a.mock and level not in levels:
                print(f"skip {m['name']} / {cond}: model has no '{level}' level configured")
                continue
            ps = [p for p in prompts if not filt or p["raw"].get("most_common_player_answers")]
            f = Path(a.out) / f"{m['name']}__{cond}.jsonl"
            done = set()
            if f.exists():
                for line in open(f):
                    r = json.loads(line)
                    if r["status"] == "ok":
                        done.add((r["prompt_id"], r["sample"]))
            jobs = [(p, s) for p in ps for s in range(samples) if (p["id"], s) not in done]
            print(f"{m['name']} / {cond}: {len(jobs)} calls ({len(done)} done)")
            lock = threading.Lock()
            workers = m.get("workers", a.workers)

            def work(job):
                if stop.is_set() or budget.over():
                    return
                p, s = job
                try:
                    res, attempts, err = call_with_retry(m, system, p, level, levels.get(level, {}), a.mock)
                except QuotaExhausted as e:
                    stop.set()
                    print(f"  quota exhausted for {m['name']}: stopping. Rerun later to resume.\n  {e}")
                    return
                rec = {"model": m["name"], "condition": cond, "level": level, "prompt_id": p["id"],
                       "sample": s, "attempts": attempts, "ts": time.time()}
                if res is None:
                    rec.update(status="infra_failed", error=err)
                else:
                    budget.add(res.get("cost"))
                    rec.update(status="ok", raw=res["text"], answer=clean_answer(res["text"]),
                               **{k: v for k, v in res.items() if k != "text"})
                with lock, open(f, "a") as fh:
                    fh.write(json.dumps(rec) + "\n")

            with cf.ThreadPoolExecutor(workers) as ex:
                for i, _ in enumerate(ex.map(work, jobs), 1):
                    if i % 100 == 0:
                        print(f"  {i}/{len(jobs)}  spent ${budget.spent:.2f}")
            if stop.is_set() or budget.over():
                print(f"Stopped (spent ${budget.spent:.2f}). Rerun the same command to resume.")
                return
    print(f"Done. Spent ${budget.spent:.2f} (Claude Code costs are notional API-equivalent).")

# ------------------------------------------------------------------ score


def cmd_score(a):
    prompts = {p["id"]: p for p in load_prompts(a.data)}
    sheets, n, failed = {}, 0, 0
    with open(a.scored, "w") as out:
        for f in sorted(Path(a.out).glob("*.jsonl")):
            for line in open(f):
                r = json.loads(line)
                if r["status"] != "ok":
                    failed += 1     # infra failures are excluded, never scored as 0 (see README)
                    continue
                pid = r["prompt_id"]
                sh = sheets.setdefault(pid, Sheet(prompts[pid]["raw"]))
                tier, kind = sh.lookup(r["answer"])
                pts = TIER_PTS[tier] if tier else 0
                crowd = None
                if r["condition"].startswith("noillirk") and sh.crowd:
                    top = sh.crowd[0][1] or 1
                    crowd = next((round(100 * c / top, 1) for k, c in sh.crowd if k == norm(r["answer"])), 0.0)
                out.write(json.dumps({
                    "model": r["model"], "condition": r["condition"], "level": r["level"], "prompt_id": pid,
                    "date": prompts[pid]["date"], "sample": r["sample"], "answer": r["answer"],
                    "key": norm(r["answer"]), "tier": tier, "match": kind, "points": pts,
                    "points_timed": 0 if (r.get("latency_s") or 0) > CLOCK_S else pts,
                    "noillirk": crowd, "latency_s": r.get("latency_s"), "attempts": r["attempts"],
                    "reasoning_tok": r.get("reasoning_tok"), "out_tok": r.get("out_tok"),
                    "cost": r.get("cost") or 0.0, "notional": bool(r.get("cost_is_notional"))}) + "\n")
                n += 1
    print(f"Scored {n} answers -> {a.scored}  ({failed} infra failures excluded)")

# ------------------------------------------------------------------ report


def boot_ci(vals, B=4000, seed=0):
    rng, n = random.Random(seed), len(vals)
    ms = sorted(sum(vals[rng.randrange(n)] for _ in range(n)) / n for _ in range(B))
    return ms[int(0.025 * B)], ms[int(0.975 * B)]


def cmd_report(a):
    rows = [json.loads(l) for l in open(a.scored)]
    prompts = {p["id"]: p for p in load_prompts(a.data)}
    L = ["# KrillBench results", "",
         "Dive Score = mean points per prompt x 7 (0-700), sample 0, 95% bootstrap CI over prompts.",
         "Timed = answers over 25 s score 0. Reference: crowd's #1 answer 163, random valid answer 529.", ""]
    g = {}
    for r in rows:
        g.setdefault((r["model"], r["condition"]), []).append(r)

    # ---- leaderboard (rules-off, the headline)
    def summary(rs):
        s0 = [r for r in rs if r["sample"] == 0]
        pts = [r["points"] for r in s0]
        lo, hi = boot_ci(pts)
        valid = [r for r in s0 if r["tier"]]
        lat = sorted(r["latency_s"] or 0 for r in s0)
        return {"n": len(s0), "dive": 7 * st.mean(pts), "lo": 7 * lo, "hi": 7 * hi,
                "timed": 7 * st.mean(r["points_timed"] for r in s0),
                "exact": 7 * st.mean(0 if r["match"] == "fuzzy" else r["points"] for r in s0),
                "valid": len(valid) / len(s0),
                "ppv": st.mean(r["points"] for r in valid) if valid else 0,
                "head": sum(r["tier"] in ("plankton", "schooler") for r in valid) / max(1, len(valid)),
                "gem": sum(r["tier"] == "gem" for r in s0) / len(s0),
                "p50": lat[len(lat) // 2], "usd": 7 * sum(r["cost"] for r in s0) / len(s0),
                "notional": any(r["notional"] for r in s0),
                "rtok": st.mean(r["reasoning_tok"] for r in s0 if r["reasoning_tok"] is not None)
                if any(r["reasoning_tok"] is not None for r in s0) else None}

    head = [(m, summary(rs)) for (m, c), rs in g.items() if c == "rules-off"]
    head.sort(key=lambda x: -x[1]["dive"])
    L += ["## Leaderboard (rules, reasoning off)", "",
          "| Model | n | Dive Score [95% CI] | Timed | Exact-only | Valid | Pts if valid | Head rate | Gems | p50 s | $/dive |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for m, s in head:
        usd = f"${s['usd']:.3f}" + ("*" if s["notional"] else "")
        lv = g[(m, "rules-off")][0]["level"]
        label = m if lv == "off" else f"{m} (at {lv})"
        L.append(f"| {label} | {s['n']} | {s['dive']:.0f} [{s['lo']:.0f}, {s['hi']:.0f}] | {s['timed']:.0f} | "
                 f"{s['exact']:.0f} | {100*s['valid']:.0f}% | {s['ppv']:.0f} | {100*s['head']:.0f}% | "
                 f"{100*s['gem']:.1f}% | {s['p50']:.1f} | {usd} |")
    L.append("\n\\* Claude Code cost is the API-equivalent figure it reports; your subscription is what you pay.")
    L.append("\"(at X)\": the model can't turn reasoning off, so its headline runs at its lowest supported level X.")

    # ---- paired gaps between neighbours
    by = {m: {r["prompt_id"]: r["points"] for r in g[(m, "rules-off")] if r["sample"] == 0} for m, _ in head}
    L += ["", "### Paired gaps between neighbours (rules-off)", "", "| A | B | A - B [95% CI] |", "|---|---|---|"]
    for (A, _), (B, _) in zip(head, head[1:]):
        sh = sorted(set(by[A]) & set(by[B]))
        if len(sh) >= 10:
            d = [by[A][p] - by[B][p] for p in sh]
            lo, hi = boot_ci(d)
            L.append(f"| {A} | {B} | {7*st.mean(d):.0f} [{7*lo:.0f}, {7*hi:.0f}]{'' if lo > 0 or hi < 0 else ' tie'} |")

    # ---- reasoning sweep
    L += ["", "## Reasoning sweep (rules)", "",
          "| Model | off | low | medium | high | reasoning tokens (off/low/med/high) | timed (off/low/med/high) |",
          "|---|---|---|---|---|---|---|"]
    for m in sorted({k[0] for k in g}):
        cells, toks, timed = [], [], []
        off = g.get((m, "rules-off"))
        off_lv = off[0]["level"] if off else "off"
        for lv in LEVELS:
            rs = off if lv == off_lv else None if lv == "off" else g.get((m, f"rules-{lv}"))
            if rs:
                s = summary(rs)
                cells.append(f"{s['dive']:.0f} [{s['lo']:.0f}, {s['hi']:.0f}]")
                toks.append("-" if s["rtok"] is None else f"{s['rtok']:.0f}")
                timed.append(f"{s['timed']:.0f}")
            else:
                cells.append("-"); toks.append("-"); timed.append("-")
        L.append(f"| {m} | " + " | ".join(cells) + f" | {' / '.join(toks)} | {' / '.join(timed)} |")

    # ---- rules vs behavior
    L += ["", "## Do the rules change behavior? (naive vs rules, both reasoning off)", "",
          "| Model | Naive Dive | Rules Dive | Gain [95% CI] | Naive head rate | Rules head rate |",
          "|---|---|---|---|---|---|"]
    for m in sorted({k[0] for k in g}):
        if (m, "naive-off") in g and (m, "rules-off") in g:
            nv = {r["prompt_id"]: r for r in g[(m, "naive-off")] if r["sample"] == 0}
            ru = {r["prompt_id"]: r for r in g[(m, "rules-off")] if r["sample"] == 0}
            sh = sorted(set(nv) & set(ru))
            d = [ru[p]["points"] - nv[p]["points"] for p in sh]
            lo, hi = boot_ci(d)
            sn, sr = summary(list(nv.values())), summary(list(ru.values()))
            L.append(f"| {m} | {sn['dive']:.0f} | {sr['dive']:.0f} | {7*st.mean(d):+.0f} [{7*lo:+.0f}, {7*hi:+.0f}] | "
                     f"{100*sn['head']:.0f}% | {100*sr['head']:.0f}% |")

    # ---- herd analysis
    L += herd_section(g, prompts)
    # ---- difficulty
    L += difficulty_section(g, prompts)
    # ---- contamination
    rel = {}
    if a.models and Path(a.models).exists():
        rel = {m["name"]: m.get("released") for m in json.load(open(a.models)) if m.get("released")}
    if rel:
        L += ["", "## Contamination check (rules-off): dives before vs after release", "",
              "| Model | Released | Older dives (n) | Post-release dives (n) |", "|---|---|---|---|"]
        for m, _ in head:
            if m in rel:
                rs = [r for r in g[(m, "rules-off")] if r["sample"] == 0]
                old = [r["points"] for r in rs if r["date"] <= rel[m]]
                new = [r["points"] for r in rs if r["date"] > rel[m]]
                f = lambda v: f"{7*st.mean(v):.0f} ({len(v)})" if v else "- (0)"
                L.append(f"| {m} | {rel[m]} | {f(old)} | {f(new)} |")
    nl = [(m, [r["noillirk"] for r in rs if r["noillirk"] is not None]) for (m, c), rs in g.items() if c == "noillirk-off"]
    if nl:
        L += ["", "## Noillirk (optional): typed count of the answer as % of the crowd's #1", "", "| Model | n | Score |", "|---|---|---|"]
        for m, v in sorted(nl, key=lambda x: -st.mean(x[1] or [0])):
            if v:
                L.append(f"| {m} | {len(v)} | {st.mean(v):.1f} |")
    att = [r["attempts"] for r in rows]
    L += ["", f"Answers scored: {len(rows)}. Calls needing a retry: {sum(x > 1 for x in att)}. "
          f"Total spend (real): ${sum(r['cost'] for r in rows if not r['notional']):.2f}."]
    Path(a.md).write_text("\n".join(L) + "\n")
    with open(a.csv, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["model", "n", "dive", "lo", "hi", "timed", "exact", "valid", "pts_if_valid", "head_rate", "gem_rate", "p50_s", "usd_per_dive"])
        for m, s in head:
            w.writerow([m, s["n"], round(s["dive"], 1), round(s["lo"], 1), round(s["hi"], 1), round(s["timed"], 1),
                        round(s["exact"], 1), round(s["valid"], 3), round(s["ppv"], 1), round(s["head"], 3),
                        round(s["gem"], 4), round(s["p50"], 2), round(s["usd"], 4)])
    print("\n".join(L))


def herd_section(g, prompts):
    """AI herd effect on rules-off. Across models: how often two different models give the same
    valid answer, vs how often a model repeats itself, vs overlap with the human crowd's top 10."""
    models = sorted(m for m, c in g if c == "rules-off")
    if len(models) < 2:
        return ["", "## AI herd effect", "", "Needs 2+ models."]
    ans = {m: {} for m in models}           # model -> prompt -> [keys of valid answers by sample]
    for m in models:
        for r in g[(m, "rules-off")]:
            if r["tier"]:
                ans[m].setdefault(r["prompt_id"], {})[r["sample"]] = r["key"]
    pids = sorted(set.intersection(*[set(v) for v in ans.values()]))
    cross, self_rep = [], []
    for p in pids:
        for A, B in itertools.combinations(models, 2):
            a0, b0 = ans[A][p].get(0), ans[B][p].get(0)
            if a0 and b0:
                cross.append(a0 == b0)
        for m in models:
            s = ans[m][p]
            if 0 in s and 1 in s:
                self_rep.append(s[0] == s[1])
    # chance agreement if models picked uniformly from the sheet
    chance = st.mean(1 / max(1, sum(len(x["answers"]) for x in prompts[p]["raw"]["tiers"].values())) for p in pids) if pids else 0
    herd_ans = []
    for p in pids:
        c = {}
        for m in models:
            k = ans[m][p].get(0)
            if k:
                c[k] = c.get(k, 0) + 1
        k, n = max(c.items(), key=lambda kv: kv[1]) if c else (None, 0)
        if n >= max(2, (len(models) + 1) // 2):
            herd_ans.append((prompts[p]["text"][:55], k, n))
    human = []
    for m in models:
        hits = [ans[m][p].get(0) in {k for k, _ in Sheet(prompts[p]["raw"]).crowd}
                for p in ans[m] if prompts[p]["raw"].get("most_common_player_answers") and ans[m][p].get(0)]
        if hits:
            human.append((m, sum(hits) / len(hits), len(hits)))
    L = ["", "## AI herd effect (rules-off, valid answers)", "",
         f"- Two different models give the same answer: **{100*st.mean(cross):.1f}%** of model pairs per prompt "
         f"(uniform chance from the sheet: {100*chance:.2f}%; {len(pids)} prompts, {len(models)} models)."
         if cross else "- Not enough overlapping prompts.",
         f"- A model repeats its own answer across samples: **{100*st.mean(self_rep):.1f}%**." if self_rep else
         "- Self-repeat needs 2+ samples on rules-off.",
         f"- Prompts where at least half the models gave the identical answer: **{len(herd_ans)}** of {len(pids)}.", "",
         "| Model | Answers in the human crowd's top 10 | n |", "|---|---|---|"]
    L += [f"| {m} | {100*h:.0f}% | {n} |" for m, h, n in sorted(human, key=lambda x: -x[1])]
    if herd_ans:
        L += ["", "Most shared answers:", "", "| Prompt | Answer (normalized) | Models |", "|---|---|---|"]
        L += [f"| {t} | {k} | {n} |" for t, k, n in sorted(herd_ans, key=lambda x: -x[2])[:15]]
    return L


def difficulty_section(g, prompts):
    """Empirical difficulty: share of models whose rules-off answer was invalid, then terciles."""
    inval = {}
    for (m, c), rs in g.items():
        if c == "rules-off":
            for r in rs:
                if r["sample"] == 0:
                    inval.setdefault(r["prompt_id"], []).append(r["tier"] is None)
    if not inval:
        return []
    diff = {p: st.mean(v) for p, v in inval.items()}
    order = sorted(diff, key=lambda p: diff[p])
    k = len(order) // 3
    bands = {"easy": set(order[:k]), "medium": set(order[k:2 * k]), "hard": set(order[2 * k:])}
    L = ["", "## Difficulty (bands set by the share of models that answered invalidly)", "",
         "| Model | easy | medium | hard |", "|---|---|---|---|"]
    for m in sorted(m for m, c in g if c == "rules-off"):
        rs = [r for r in g[(m, "rules-off")] if r["sample"] == 0]
        cells = []
        for b in ("easy", "medium", "hard"):
            v = [r["points"] for r in rs if r["prompt_id"] in bands[b]]
            cells.append(f"{7*st.mean(v):.0f}" if v else "-")
        L.append(f"| {m} | " + " | ".join(cells) + " |")
    L += ["", "Hardest prompts:", "", "| Prompt | Models invalid |", "|---|---|"]
    L += [f"| {prompts[p]['text'][:70]} | {100*diff[p]:.0f}% |" for p in order[::-1][:10]]
    return L

# ------------------------------------------------------------------ main


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data/krillion_answers.json")
    ap.add_argument("--out", default="runs")
    sp = ap.add_subparsers(dest="cmd", required=True)
    r = sp.add_parser("run")
    r.add_argument("--models", default="models.json")
    r.add_argument("--only", help="comma-separated model names")
    r.add_argument("--conditions", help=f"comma-separated; default {','.join(DEFAULT_PLAN)}; also noillirk-off")
    r.add_argument("--samples", type=int, help="override rules-off samples (others always 1)")
    r.add_argument("--limit", type=int, help="fixed random subset of N prompts (seed 0), for pilots")
    r.add_argument("--workers", type=int, default=6)
    r.add_argument("--max-usd", type=float, default=50.0, help="hard cap on real spend this invocation")
    r.add_argument("--mock", action="store_true")
    s = sp.add_parser("score"); s.add_argument("--scored", default="scored.jsonl")
    rp = sp.add_parser("report"); rp.add_argument("--scored", default="scored.jsonl")
    rp.add_argument("--md", default="report.md"); rp.add_argument("--csv", default="leaderboard.csv")
    rp.add_argument("--models", default="models.json")
    a = ap.parse_args()
    {"run": cmd_run, "score": cmd_score, "report": cmd_report}[a.cmd](a)


if __name__ == "__main__":
    main()
