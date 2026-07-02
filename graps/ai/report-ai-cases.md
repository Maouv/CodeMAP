# Bug Hunter Report — graps/ai

**Scope:** `graps/ai/cache.py`, `graps/ai/provider.py` (dan interaksi dengan caller `graps/server/app.py::post_summary`).
**Branch:** `phase1-scanner-core`
**Method:** Full source read → hypothesis collection → **execution-based verification** (setiap finding dijalankan, bukan spekulasi).
**Date:** 2026-07-01
**Note:** Beberapa finding di sini adalah varian/saudara dari `report-bug-finder.md` yang fokusnya beda; yang sudah ter-cover persis di sana ditandai. Yang baru di sini diuji sendiri.

---

## Summary

| # | Title | Severity | Likelihood | Confidence |
|---|-------|----------|------------|------------|
| 1 | `scrub_secrets` leaks secrets in multi-line assignments (keyword & secret on different lines) | Critical | High | High |
| 2 | `scrub_secrets` leaks dict-literal (colon-form) secrets when `detect-secrets` not installed (core install) | High | Medium | High |
| 3 | `write_cache` crashes (TypeError) when cache `entries` is a non-dict → HTTP 500 + billed AI result discarded | High | Medium | High |
| 4 | `_parse_summary` rejects common LLM response wrappers (```fences, prose) → `parse_failed`, billed result discarded | High | High | High |
| 5 | `is_valid` raises `AttributeError` on non-dict / `None` entry → 500 on cache-hit path | Medium | Low | High |
| 6 | `read_cache` raises on non-UTF-8 / directory (and `PermissionError` for non-root) — violates "never raise" contract → 500 | Medium | Medium | High |
| 7 | `is_valid` exact-string match on `modified_at` → cache bust on date-format drift → re-bill every request | Medium | High | High |
| 8 | `scrub_secrets` false-positive redaction of non-secret flag assignments (`auth = True`, `token = None`) → AI analyzes corrupted source | Medium | High | High |
| 9 | `_parse_summary` passes through truthy non-string types (`int`/`list`/`dict`) → violates string contract, downstream crash risk (residual of report-bug-finder Finding 8) | Medium | Low | High |
| 10 | `_cache_locks` dict grows unbounded — one `Lock` per distinct `cache_path`, never evicted (memory leak) | Low | Low | High |
| 11 | `write_cache` can leave orphan `.tmp` on mid-write failure (disk full) — resource leak, no cleanup | Low | Low | Medium |


# Finding 1

## Title
`scrub_secrets` leaks secrets in multi-line assignments where the keyword and the secret value are on different lines

## Severity
Critical

## Likelihood
High

## Confidence
High

## Category
Security / Secret Leakage / Validation Gap

## Scenario
A developer's source contains a multi-line assignment, e.g. a config builder or a tuple/list spread:
```python
password = (
    "hunter2-secret"
)
```
or
```python
api_key = [
    "sk-ant-xxx",
]
```
The user clicks "Generate AI Insight". `scrub_secrets` runs before the source is sent to the AI provider. The secret value is **not redacted** and is sent to the third-party LLM API.

## Description
`scrub_secrets` (provider.py:64-98) processes the source **line by line**:
- Layer 1 calls `detector.analyze_line(line=line, ...)` per line. `detect-secrets` analyzes each line independently, so on the line `password = (` there is no secret value to detect, and on the line `    "hunter2-secret"` there is no keyword context — neither line triggers redaction of the secret.
- Layer 2 regex `(?i)(password|...)\s*=\s*["']?.+` is applied to the **joined** string, but `.+` after `=` matches only the rest of *that same line* (`(`), so it redacts `password = (` → `password = "[REDACTED]"` while leaving `    "hunter2-secret"` untouched on the next line.

Result: the literal secret `hunter2-secret` survives into the prompt. This is the core security invariant of the module (BLUEPRINT §10 C-02, docstring line 14: "scrub_secrets selalu dijalankan terhadap source sebelum dimasukkan ke prompt") and it is silently broken for a common Python idiom.

## Evidence
```python
# Verified via execution (venv, detect-secrets installed):
from graps.ai.provider import scrub_secrets
src = 'password = (\n    "hunter2-secret"\n)\n'
out = scrub_secrets(src)
# out == 'password = "[REDACTED]"\n    "hunter2-secret"\n)\n'
assert "hunter2-secret" in out   # LEAKED
```
Output captured:
```
password = "[REDACTED]"
    "hunter2-secret"
)
```
The keyword line is redacted but the secret on the next line is intact.

## Steps to Reproduce
1. `pip install graps[ai]` (or any install where scrub_secrets is used).
2. Create a source file with a multi-line secret assignment as above.
3. Run graps, open the function, click "Generate AI Insight".
4. Observe: the prompt sent to the AI provider contains the un-redacted secret (inspect via network/log, or unit-test `scrub_secrets` directly as above).

## Expected Behavior
No secret value reaches the AI provider. Multi-line assignments spanning the keyword and the value must be redacted.

## Actual Behavior
The secret value on the line(s) after the keyword line is sent un-redacted to the LLM.

## Root Cause
The redaction model is **line-local**: both layers assume the keyword and the secret value live on the same line. Layer 1 (`detect-secrets`) is fundamentally per-line; Layer 2's regex `=\s*["']?.+` cannot span newlines (no `re.DOTALL`, and `.+` stops at `\n`). Multi-line value forms (parenthesized tuples, list literals, string concatenation across lines) are never considered.

## Blast Radius
System-wide — any source sent to any AI provider (Anthropic or OpenAI) can leak secrets. Affects every user with an API key configured.

## Impact
- **Security (Critical):** credentials (DB passwords, API keys, tokens) exfiltrated to a third-party LLM. This is the highest-impact failure mode the module exists to prevent.
- **Data:** secrets leave the user's machine and may be retained by the provider.
- **Business:** credential-leak incident; potential breach obligation.

## Recommendation
- **Fix:** after the per-line pass, run a second regex pass on the **full** source that matches a keyword followed (across newlines) by a quoted value, e.g. `re.compile(r'(?i)(password|passwd|pwd|api_key|apikey|secret|token|auth|credential)\s*=\s*.*?["\']([^"\']+)["\']', re.DOTALL)` and redact the captured value. Better: redact the *value* substring globally once detected, not the whole line.
- **Prevention:** add a regression test with multi-line assignment, tuple/list spread, and string-concatenation-across-lines cases. The current self-check (provider.py:292-300) only tests single-line `password = 'hunter2'`.
- **Long-term:** prefer a real AST-based secret scrubber or `detect-secrets` file-level scan (`analyze_file` / `scan`) instead of `analyze_line`, so cross-line context is visible.
- **Monitoring/metrics:** log a count of `scrub_secrets` redactions per request (without the value) so a sudden drop to 0 on a file known to contain secrets is visible.

## Test Cases
- `scrub_secrets('password = (\n    "hunter2-secret"\n)\n')` → `"hunter2-secret"` not in output.
- `scrub_secrets('api_key = [\n    "sk-abc",\n]\n')` → `"sk-abc"` not in output.
- `scrub_secrets('token = "a" + \\\n    "b-secret"\n')` → `"b-secret"` not in output.
- Negative: `scrub_secrets('x = 1\ny = 2')` unchanged (no over-redaction).

## Regression Risk
Medium. A broader regex risks over-redacting benign quoted strings on the next line; needs the keyword-anchored DOTALL form, not a blanket `["\']...["\']`.

## Related Code Path
`graps/ai/provider.py:64-98` — `scrub_secrets` (per-line `analyze_line` + line-local regex)  
`graps/ai/provider.py:165,219` — `scrub_secrets(file_content)` call sites before prompt build

---


# Finding 2

## Title
`scrub_secrets` leaks dict-literal (colon-form) secrets when `detect-secrets` is not installed (`pip install graps` core variant)

## Severity
High

## Likelihood
Medium

## Confidence
High

## Category
Security / Secret Leakage / Install-Variant Regression

## Scenario
A user installs the **core** package (`pip install graps`, without the `[ai]` extra) — `detect-secrets` is absent, so `_DETECTORS = []` (provider.py:46-52) and only the manual Layer-2 regex runs. Their source contains a dict-literal config:
```python
CONFIG = {"password": "hunter2-NOPLUG"}
d = {"api_key": "sk-leaked-12345"}
```
The colon form (`"password": "..."`) does not match Layer-2's `keyword\s*=\s*...` pattern, so the secret is sent to the AI provider un-redacted.

## Description
Layer-2 regexes (provider.py:57-61) require an `=` immediately after the keyword: `(password|...)\s*=\s*["']?.+`. Dict literals use `:` not `=`, so `"password": "secret"` never matches. When `detect-secrets` is installed (the `[ai]` extra), Layer-1's keyword/high-entropy detectors catch it; when it is **not** installed, there is no fallback for the colon form and the secret leaks.

The module is explicitly designed to be importable without `detect-secrets` (the `try/except ImportError` guard at provider.py:25-52 exists precisely so `pip install graps` core doesn't crash on import). That makes the no-plugin path a supported, reachable configuration — not a theoretical one.

## Evidence
```python
# Verified via execution:
# (a) WITH detect-secrets installed -> caught (leaked=False):
#     CONFIG = {"password": "[REDACTED]"}
# (b) WITHOUT detect-secrets (_DETECTORS=[]) -> LEAKED:
from graps.ai import provider as prov
prov._DETECTORS = []                      # simulate core install
out = prov.scrub_secrets('CONFIG = {"password": "hunter2-NOPLUG"}\n')
assert "hunter2-NOPLUG" in out            # LEAKED
```
Output captured (no-plugin path):
```
CONFIG = {"password": "hunter2-NOPLUG"}
```

## Steps to Reproduce
1. `pip install graps` (core, no `[ai]`).
2. Set an AI API key, run graps, generate an insight on a function whose source contains `{"api_key": "..."}`.
3. The secret reaches the provider un-redacted.

## Expected Behavior
Secrets are redacted regardless of whether `detect-secrets` is installed — the no-plugin fallback must cover the colon form too.

## Actual Behavior
With the core install, colon-form dict-literal secrets pass through to the LLM.

## Root Cause
Layer-2 was written to mirror only the `keyword = value` assignment form. The colon form (`"key": value`) was implicitly delegated to `detect-secrets` Layer-1, but Layer-1 is optional and absent on the core install. The fallback therefore has a coverage hole exactly when it is the *only* layer running.

## Blast Radius
Module → Service. Affects every user on the core install (the default `pip install graps`).

## Impact
- **Security (High):** secrets in dict-literal configs leak to the LLM on the most common install path.
- **Reliability:** the security guarantee silently degrades based on which extras were installed — a user has no signal that scrubbing is weaker.

## Recommendation
- **Fix:** extend Layer-2 with a colon-form pattern, e.g. `re.compile(r'(?i)["\']?(password|passwd|pwd|api_key|apikey|secret|token|auth|credential)["\']?\s*:\s*["\']([^"\']+)["\']')` and redact the captured value.
- **Prevention:** the self-check / test suite must run scrub tests with `_DETECTORS = []` (simulating core install), not only with plugins present. Currently `tests/test_provider.py` runs in an env where detect-secrets is installed, so this path is untested.
- **Long-term:** make `detect-secrets` a hard dependency for the AI feature, or document the degraded mode loudly and refuse to call the provider when `_DETECTORS == []` (fail-closed on security).
- **Logging:** emit a startup warning when `_DETECTORS == []` so the degraded mode is visible.

## Test Cases
- With `_DETECTORS = []`: `scrub_secrets('d = {"api_key": "sk-x"}')` → `"sk-x"` not in output.
- With `_DETECTORS = []`: `scrub_secrets('c = {"password": "p", "host": "h"}')` → `"p"` not in output, `"h"` preserved.
- With plugins: same cases pass (regression guard).

## Regression Risk
Low. Adding a colon-form regex is additive; the existing `=`-form behavior is unchanged.

## Related Code Path
`graps/ai/provider.py:25-52` — optional `_DETECTORS` guard  
`graps/ai/provider.py:57-61` — `_SENSITIVE_PATTERNS` (only `=` form)  
`graps/ai/provider.py:64-98` — `scrub_secrets` Layer-2 fallback

---

# Finding 3

## Title
`write_cache` crashes with `TypeError` when the on-disk cache has `entries` as a non-dict (string/null) — caller returns HTTP 500 and the already-billed AI summary is discarded

## Severity
High

## Likelihood
Medium

## Confidence
High

## Category
Reliability / Error Handling / Data Loss / Robustness

## Scenario
The cache file (`~/.graps/cache.json` or a custom path) becomes half-corrupt: a prior crash, a hand-edit, a different/older graps version, or an external tool wrote `{"version": "1", "entries": "garbage"}` or `{"version": "1", "entries": null}`. `read_cache` returns this without complaint (it only `setdefault`s, never coerces existing wrong-typed `entries`). The next `POST /api/ai/summary` that is a cache miss calls the AI provider (cost incurred), then `write_cache` does `data["entries"][key] = entry` → `TypeError: 'str' object does not support item assignment`. `post_summary` (app.py:187) is **outside** the `try/except AIError` block (deliberately, per the comment at app.py:183-185), so the exception bubbles to a 500. The freshly-computed, already-billed summary is lost and never cached.

## Description
`read_cache` (cache.py:38-48) validates only that the top-level JSON is a dict, then `data.setdefault("entries", {})`. `setdefault` does **not** replace an existing key whose value is the wrong type — so `entries` stays a string/`None`/list. `write_cache` (cache.py:82-95) then assumes `data["entries"]` is a dict and does item assignment, which raises `TypeError` for str/None and (silently) corrupts for list. There is no shape validation of `entries` and no defensive coercion.

Worse, the caller (`post_summary`) intentionally does **not** catch generic `Exception` around `write_cache` ("SENGAJA tidak catch Exception … bug nyata harus bubble jadi 500"). So this is treated as a "real bug" → 500, but the consequence is that a one-time cache corruption permanently breaks AI summarization *and* wastes every subsequent API call (compute → crash → discard → repeat).

## Evidence
```python
# Verified via execution:
import json, tempfile
from pathlib import Path
from graps.ai import cache as cm

# entries is a string
with tempfile.TemporaryDirectory() as d:
    p = Path(d)/"c.json"
    p.write_text(json.dumps({"version":"1","entries":"I_AM_A_STRING"}))
    cm.read_cache(p)                       # OK, returns entries="I_AM_A_STRING"
    cm.write_cache(p,"f::g",{"file_modified_at":"x","summary":{}})
    # -> TypeError: 'str' object does not support item assignment

# entries is null
with tempfile.TemporaryDirectory() as d:
    p = Path(d)/"c.json"
    p.write_text(json.dumps({"version":"1","entries":None}))
    cm.write_cache(p,"f::g",{"file_modified_at":"x","summary":{}})
    # -> TypeError: 'NoneType' object does not support item assignment
```
Both raise as shown.

## Steps to Reproduce
1. Put a cache file with `{"version":"1","entries":"oops"}` at the configured cache path.
2. Configure an AI API key, run graps, request an insight for any function (cache miss path).
3. The AI provider is called (billed), then `write_cache` raises `TypeError` → HTTP 500, summary not returned, not cached.
4. Every subsequent request repeats the bill-and-discard cycle (the corrupt file is never repaired).


## Expected Behavior
`read_cache`/`write_cache` should treat a wrong-typed `entries` as corrupt and reset it to `{}` (or `write_cache` should coerce), so a stale cache never breaks the live path. A single corrupt cache file should self-heal, not brick the feature.

## Actual Behavior
`TypeError` propagates → 500; the billed AI result is discarded; the corrupt cache is never fixed, so the failure is permanent until manual intervention.

## Root Cause
`read_cache` uses `setdefault` (which only fills missing keys) instead of a type check. The docstring (cache.py:44-45) explicitly skips deeper shape validation ("ponytail: tidak validasi shape lebih dalam … Tambahkan kalau ada bug nyata") — this is that bug. Combined with the caller's intentional non-catch of generic exceptions around `write_cache`, a cache-shape problem escalates from "stale cache" to "permanent 500 + recurring API spend".

## Blast Radius
Service — every AI insight request once the cache is corrupt; persists across restarts (the file is not auto-repaired).

## Impact
- **Reliability (High):** AI insight endpoint hard-fails with 500 until the cache file is manually deleted/fixed.
- **Cost (High):** every retry bills the provider and throws the result away — direct monetary loss scaling with retries.
- **Data:** valid summaries computed but never persisted or shown.
- **UX:** user sees server error with no actionable hint.

## Recommendation
- **Fix (root cause, one place):** in `read_cache`, coerce `entries` to `{}` when it is not a dict:
  ```python
  if not isinstance(data.get("entries"), dict):
      data["entries"] = {}
  ```
  Do the same for `version` if needed. This single guard covers all callers of `read_cache` (both the hit-check and `write_cache`).
- **Defense-in-depth:** wrap `write_cache` in `post_summary` so a cache write failure degrades to "return summary, skip cache" rather than 500 (the summary was already paid for). Log the cache write failure.
- **Prevention:** add a test: pre-seed `entries` as string/null/list → `read_cache` returns a usable dict, `write_cache` succeeds.
- **Monitoring:** count `cache_write_failed` events; alert if non-zero.

## Test Cases
- Pre-seed `{"version":"1","entries":"x"}` → `read_cache` returns `entries={}`; `write_cache` succeeds; file now valid.
- Pre-seed `{"version":"1","entries":null}` → same.
- Pre-seed `{"version":"1","entries":[1,2]}` → same (list is not a dict).
- Pre-seed `{"version":"1","entries":{"k":{}}}` → preserved (valid case unchanged).

## Regression Risk
Low. Coercion only fires on wrong-typed `entries`; valid caches are untouched.

## Related Code Path
`graps/ai/cache.py:38-48` — `read_cache` (`setdefault` without type check)  
`graps/ai/cache.py:82-95` — `write_cache` (`data["entries"][key] = entry`)  
`graps/server/app.py:160-203` — `post_summary` (read_cache + write_cache outside AIError catch)

---


# Finding 4

## Title
`_parse_summary` rejects common LLM response wrappers (```code fences, leading/trailing prose) → `parse_failed`, billed result discarded

## Severity
High

## Likelihood
High

## Confidence
High

## Category
Reliability / Error Handling / AI Correctness / Cost

## Scenario
Despite the prompt instructing "Reply with a single JSON object", real LLMs (Claude/GPT) frequently wrap JSON in ```` ```json ```` fences or add conversational prose: `Sure! Here is the summary:\n{...}` or `{...}\n\nLet me know if you need more.` `_parse_summary` calls `json.loads(text)` directly with no fence-stripping or JSON-extraction, so all of these raise `AIError("parse_failed")`. The API call was already made and billed; the summary is thrown away and the user sees an error.

## Description
`_parse_summary` (provider.py:256-273) does a strict `json.loads(text)`. There is no tolerance for:
- ```` ```json\n{...}\n``` ```` (labeled fence)
- ```` ```\n{...}\n``` ```` (unlabeled fence)
- leading prose (`Sure! Here is ...:\n{...}`)
- trailing prose (`{...}\n\nLet me know...`)

All produce `json.JSONDecodeError` → `AIError("parse_failed")`. The Anthropic path uses no `response_format` JSON mode, and even OpenAI's `response_format={"type":"json_object"}` only constrains the *content* to valid JSON — many models still prepend/append text or fences in practice, especially smaller models like `gpt-4o-mini` / `claude-haiku`.

The caller (`post_summary`) maps `parse_failed` to `{"enabled": True, "error_type": "parse_failed"}` — no retry, no fallback extraction, no salvage. The billed call yields nothing.

## Evidence
```python
# Verified via execution:
from graps.ai.provider import _parse_summary
cases = {
  "labeled-fence":   '```json\n{"role":"r","importance":"i","hidden_assumption":"h"}\n```',
  "unlabeled-fence": '```\n{"role":"r","importance":"i","hidden_assumption":"h"}\n```',
  "leading-prose":   'Sure! Here is the summary:\n{"role":"r","importance":"i","hidden_assumption":"h"}',
  "trailing-prose":  '{"role":"r","importance":"i","hidden_assumption":"h"}\n\nLet me know if you need more.',
}
for k, t in cases.items():
    try: _parse_summary(t)
    except Exception as e: print(k, "->", type(e).__name__, e)
# All four -> AIError parse_failed
```
Result: all four variants raise `AIError: parse_failed`.

## Steps to Reproduce
1. Configure an AI key; monkeypatch or use a model that wraps JSON in fences/prose.
2. Request an insight.
3. Response is `{"enabled": true, "error_type": "parse_failed"}`; the API call was billed; no summary returned or cached.

## Expected Behavior
Common JSON wrappers are stripped and the embedded JSON object is parsed. Only genuinely unparseable content should yield `parse_failed`.

## Actual Behavior
Any non-bare-JSON wrapper → `parse_failed`, billed call discarded.

## Root Cause
`json.loads` is strict about the whole string being JSON. No fence removal, no `re.search` for the first `{...}` object, no retry. The prompt's "single JSON object" instruction is treated as a guarantee rather than a best-effort contract.

## Blast Radius
Service — affects every AI insight request whenever the model adds wrappers (frequent with small models, prompts, or temperature > 0).

## Impact
- **Reliability (High):** a large fraction of successful, billed AI calls produce no usable result.
- **Cost (High):** paid tokens discarded; users retry, multiplying spend.
- **UX:** users see `parse_failed` with no recovery.

## Recommendation
- **Fix:** before `json.loads`, normalize: strip leading/trailing ```` ```...``` ```` fences and surrounding prose, then extract the first balanced `{...}`:
  ```python
  m = re.search(r"\{.*\}", text, re.DOTALL)
  if m: text = m.group(0)
  ```
  (A balanced-brace scan is safer than greedy `.*` if the prose itself contains braces.)
- **Retry-once:** on `parse_failed`, optionally retry the provider call once with a stricter prompt; or at minimum log the raw text (redacted) for debugging.
- **Prevention:** test `_parse_summary` against fenced and prose-wrapped fixtures (see Test Cases).
- **Monitoring:** count `parse_failed` per provider/model; a high rate signals a prompt/model mismatch.

## Test Cases
- `_parse_summary('```json\n{...}\n```')` → returns the dict.
- `_parse_summary('```\n{...}\n```')` → returns the dict.
- `_parse_summary('Sure!\n{...}')` → returns the dict.
- `_parse_summary('{...}\n\nmore text')` → returns the dict.
- `_parse_summary('not json at all')` → `AIError("parse_failed")` (genuine failure still raises).

## Regression Risk
Low. Extraction is additive; bare-JSON still parses identically. Edge: if prose contains a `{...}`-like fragment before the real object, naive greedy regex grabs the wrong span — use a brace-balanced extractor.

## Related Code Path
`graps/ai/provider.py:256-273` — `_parse_summary`  
`graps/ai/provider.py:175,229` — `text = resp.content[0].text` / `resp.choices[0].message.content` fed to `_parse_summary`  
`graps/server/app.py:175-182` — `parse_failed` handling (no retry/salvage)

---


# Finding 5

## Title
`is_valid` raises `AttributeError` on a non-dict / `None` cache entry → HTTP 500 on the cache-hit path

## Severity
Medium

## Likelihood
Low

## Confidence
High

## Category
Reliability / Error Handling / Robustness

## Scenario
A cache entry stored under a key is not a dict — e.g. an older graps version stored a bare string, a hand-edit set `"f::foo": "some summary"`, or a corrupt write left `"f::foo": null`. On the next request, `post_summary` does `hit = cache["entries"].get(key)` (returns the non-dict), then `cache_module.is_valid(hit, req.modified_at)` → `hit.get("file_modified_at")` → `AttributeError` (str/None/list have no `.get`). This is on the cache-hit fast path, outside the AIError try/except → HTTP 500.

## Description
`is_valid` (cache.py:98-100) is `entry.get("file_modified_at") == current_modified_at` with no type guard. The docstring implies `entry` is a dict, but nothing enforces it, and `read_cache`/`write_cache` do not validate per-entry shape (see Finding 3). So a single malformed entry poisons the hit-check.

In `post_summary`, the in-memory cache check (app.py:152-153) and the on-disk check (app.py:161-162) both call `is_valid` directly on the retrieved value. A 500 here is especially bad because it happens *before* any AI call — a corrupt entry breaks retrieval of *other* valid entries too (the exception aborts the whole request).

## Evidence
```python
# Verified via execution:
from graps.ai import cache as cm
cm.is_valid("not_a_dict", "2026")   # -> AttributeError: 'str' object has no attribute 'get'
cm.is_valid(None, "2026")           # -> AttributeError: 'NoneType' object has no attribute 'get'
```

## Steps to Reproduce
1. Seed the cache: `{"version":"1","entries":{"f::foo": "i am a string not a dict"}}`.
2. Request an insight for `f::foo` (matches the key).
3. `is_valid("i am a string not a dict", ...)` → `AttributeError` → 500.

## Expected Behavior
A malformed entry is treated as invalid (cache miss) and re-computed, never as a crash.

## Actual Behavior
`AttributeError` → 500; the request fails even though re-computation would have fixed the entry.

## Root Cause
`is_valid` trusts its input type. There is no `isinstance(entry, dict)` guard, and no caller-side normalization. Same class of "skipped shape validation" as Finding 3.

## Blast Radius
Module → Service (the one request). Does not corrupt other entries, but the bad entry is never self-healed (each matching request 500s).

## Impact
- **Reliability:** a single bad entry → repeated 500s for that key.
- **UX:** error with no recovery; the entry stays broken.

## Recommendation
- **Fix (one place):** guard in `is_valid`:
  ```python
  def is_valid(entry, current_modified_at):
      return isinstance(entry, dict) and entry.get("file_modified_at") == current_modified_at
  ```
- **Prevention:** test `is_valid` with str/None/list/dict inputs.
- **Defense-in-depth:** in `post_summary`, treat a non-dict `hit` as a miss (skip and recompute) instead of calling `is_valid` blindly.

## Test Cases
- `is_valid("x", "2026")` → `False` (no raise).
- `is_valid(None, "2026")` → `False`.
- `is_valid([], "2026")` → `False`.
- `is_valid({"file_modified_at":"2026"}, "2026")` → `True` (unchanged).

## Regression Risk
Low. The guard only changes behavior for malformed inputs (from raise to `False`).

## Related Code Path
`graps/ai/cache.py:98-100` — `is_valid`  
`graps/server/app.py:152-153,161-162` — `is_valid` call sites (in-memory + on-disk hit check)

---


# Finding 6

## Title
`read_cache` raises on non-UTF-8 / directory (and `PermissionError` for non-root) — violates its "never raise" docstring contract → HTTP 500

## Severity
Medium

## Likelihood
Medium

## Confidence
High

## Category
Reliability / Error Handling / Contract Violation

## Scenario
The cache path is a directory, or the file contains non-UTF-8 bytes (a half-written/corrupt file from a killed process or a tool that wrote bytes), or (for non-root deployments) the file is unreadable. `read_cache`'s docstring (cache.py:34-37) states "Tidak pernah raise — caller yang putuskan mau log atau tidak", but its `except` only catches `(FileNotFoundError, json.JSONDecodeError)`. `Path.read_text` raises `UnicodeDecodeError` for bad bytes, `IsADirectoryError` for a directory, and `PermissionError` for an unreadable file — none are caught. In `post_summary` this is outside the AIError try/except → HTTP 500.

## Description
`read_cache` (cache.py:38-41):
```python
try:
    data = json.loads(cache_path.read_text())
except (FileNotFoundError, json.JSONDecodeError):
    return {"version": "1", "entries": {}}
```
`read_text()` (called before `json.loads`) can raise `UnicodeDecodeError`, `IsADirectoryError`, `PermissionError`, `OSError`. The narrow except lets them propagate, contradicting the documented contract. `post_summary` calls `read_cache` (app.py:160) on the cache-miss path and on the on-disk-hit path — both 500 on these conditions.

Note on `PermissionError`: under the test environment (running as root), `chmod 0o000` does **not** block root reads, so `PermissionError` could not be reproduced here; but the code path is identical — for any non-root graps deployment an unreadable cache file raises. Marked as confirmed-by-code-reading for that sub-case.

## Evidence
```python
# Verified via execution:
from graps.ai import cache as cm
from pathlib import Path
import tempfile

# non-UTF-8 bytes -> UnicodeDecodeError (RAISES, contradicts "never raise")
with tempfile.TemporaryDirectory() as d:
    p = Path(d)/"c.json"; p.write_bytes(b"{\xff\xfe not utf8")
    cm.read_cache(p)   # -> UnicodeDecodeError

# path is a directory -> IsADirectoryError (RAISES)
with tempfile.TemporaryDirectory() as d:
    p = Path(d)/"adir"; p.mkdir()
    cm.read_cache(p)   # -> IsADirectoryError

# PermissionError: not reproducible as root (root bypasses 0o000),
# but the except tuple does not include PermissionError, so a non-root
# deployment with an unreadable cache file WILL raise.
```

## Steps to Reproduce
1. Replace the cache file with a directory of the same name, OR write non-UTF-8 bytes to it.
2. Request any AI insight (triggers `read_cache`).
3. `UnicodeDecodeError` / `IsADirectoryError` → HTTP 500.

## Expected Behavior
`read_cache` returns the default empty cache (and ideally logs) for any unreadable/unparseable file, honoring "never raise".

## Actual Behavior
It raises for non-UTF-8 / directory / unreadable, breaking the endpoint.

## Root Cause
The except tuple was written for the "missing or JSON-corrupt" cases only. The I/O failure modes of `read_text` (`UnicodeDecodeError`, `IsADirectoryError`, `PermissionError`, generic `OSError`) were not enumerated. The contract claim outlived the implementation.

## Blast Radius
Service — the AI insight endpoint 500s until the cache path is fixed; persists across requests.

## Impact
- **Reliability:** a corrupt/odd cache file bricks AI insights with a 500.
- **Contract:** callers relying on "never raise" (and the module's own design) are misled.

## Recommendation
- **Fix:** broaden the except to cover I/O failures:
  ```python
  except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError,
          IsADirectoryError, PermissionError, OSError):
      return {"version": "1", "entries": {}}
  ```
  Log a warning so silent corruption is visible.
- **Prevention:** test `read_cache` against: missing file, corrupt JSON, non-UTF-8 bytes, directory path, unreadable file (non-root CI user).
- **Monitoring:** count `cache_read_failed` by reason.

## Test Cases
- `read_cache(<dir>)` → default, no raise.
- `read_cache(<non-utf8 file>)` → default, no raise.
- `read_cache(<unreadable file>)` (non-root) → default, no raise.
- `read_cache(<missing>)` → default (existing behavior unchanged).
- `read_cache(<valid>)` → parsed dict (unchanged).

## Regression Risk
Low. Broadening the except only converts raises into defaults for already-broken inputs.

## Related Code Path
`graps/ai/cache.py:38-48` — `read_cache` (narrow except)  
`graps/server/app.py:160` — `read_cache` call outside AIError catch

---


# Finding 7

## Title
`is_valid` uses exact-string comparison on `modified_at` → cache busts on date-format drift → every request re-bills the provider

## Severity
Medium

## Likelihood
High

## Confidence
High

## Category
Performance / Cost / Reliability / Cache Correctness

## Scenario
`modified_at` is a free-form string passed from the frontend (`SummaryRequest.modified_at: str`, app.py:64) and stored verbatim as `file_modified_at` in the cache. `is_valid` compares with `==`. If the frontend ever changes how it formats the timestamp (adds microseconds, switches `T`→space, adds/expands a timezone offset, changes precision), the **same unchanged file** produces a different string → `==` is `False` → cache miss → the provider is called again and billed, even though the file content is identical and the cached summary is still valid.

## Description
`is_valid` (cache.py:98-100): `return entry.get("file_modified_at") == current_modified_at`. There is no normalization (parse to `datetime`, compare by epoch, or canonical ISO format). The cache key is `{file}::{function}` and validity is gated purely by this string. Any drift in timestamp formatting between the writer (frontend/scanner) and the reader (next request) invalidates all entries.

## Evidence
```python
# Verified via execution:
from graps.ai import cache as cm
cached = "2026-01-01T00:00:00"
cm.is_valid({"file_modified_at": cached}, "2026-01-01T00:00:00.000000")  # False (micros added)
cm.is_valid({"file_modified_at": cached}, "2026-01-01 00:00:00")          # False (T -> space)
cm.is_valid({"file_modified_at": cached}, "2026-01-01T00:00:00+00:00")    # False (tz notation)
```
All three semantically-identical timestamps return `False` → cache miss → re-bill.

## Steps to Reproduce
1. Generate an insight (cache stored with `file_modified_at="2026-01-01T00:00:00"`).
2. Change the frontend to send `modified_at="2026-01-01T00:00:00.000000"` (a trivial format tweak) — or run two frontends/scanners that format differently.
3. Request the same function again → cache miss → provider called and billed again.

## Expected Behavior
Semantically equal timestamps (same instant) are treated as equal; the cache hit survives benign format differences.

## Actual Behavior
Any format difference → miss → re-bill. The cache effectively never hits across a format change, defeating the cache and multiplying API cost.

## Root Cause
String identity is used where semantic equality is required. No canonicalization or parsing layer. The contract for `modified_at` is unspecified ("str"), so producers are free to drift.

## Blast Radius
Service — every cached entry invalidated on a format change; cost scales with the number of functions × requests.

## Impact
- **Cost (Medium-High):** redundant provider calls; budget blown on re-summarizing unchanged code.
- **Performance:** cache becomes useless; latency returns to cold-path on every request.
- **Reliability:** more API calls → more exposure to rate limits (ties into `rate_limited` handling).

## Recommendation
- **Fix:** normalize before compare — parse both sides to `datetime` (or epoch) and compare instants; fall back to string `==` only if parsing fails (backward compat with non-ISO values). Or, more robustly, define `modified_at` as a canonical ISO-8601 UTC string at the contract boundary (frontend + scanner) and validate it.
- **Prevention:** contract test that the scanner and frontend emit the same canonical format; test `is_valid` across equivalent formats.
- **Monitoring:** track cache-hit ratio per `(file,function)`; a sudden drop signals a format drift.

## Test Cases
- `is_valid` True for `2026-01-01T00:00:00` vs `2026-01-01T00:00:00.000000`.
- `is_valid` True for `...T...` vs `... ...` (space).
- `is_valid` True for `...+00:00` vs `...Z`.
- `is_valid` False for a genuinely different instant.
- Non-ISO legacy value: falls back to string `==` (no regression).

## Regression Risk
Medium. Normalization must not accidentally equate distinct instants (timezone handling) — parse to UTC before comparing. Add a fallback to string compare for unparseable values to avoid invalidating existing non-ISO caches.

## Related Code Path
`graps/ai/cache.py:98-100` — `is_valid` (string `==`)  
`graps/server/app.py:64` — `SummaryRequest.modified_at: str` (unvalidated format)  
`graps/server/app.py:152-153,161-162,192,200` — `modified_at` written/read into cache

---


# Finding 8

## Title
`scrub_secrets` false-positive redaction of non-secret flag assignments (`auth = True`, `token = None`) → AI analyzes corrupted source, produces wrong summaries

## Severity
Medium

## Likelihood
High

## Confidence
High

## Category
Correctness / Over-Redaction / AI Input Integrity

## Scenario
Source contains boolean/flag-style assignments using a sensitive-looking keyword as a *name*, not a secret:
```python
auth = True
token = None
is_authenticated = False
use_secret = False
```
Layer-2 regex `(?i)(auth|credential)\s*=\s*["']?.+` and `(api_key|...|secret|token)\s*=\s*["']?.+` match these and rewrite them to `auth = "[REDACTED]"`, `token = "[REDACTED]"`. The AI then receives source where a boolean flag has been turned into a redacted string literal — semantically wrong code — and bases its `role`/`importance`/`hidden_assumption` on corrupted input.

## Description
The Layer-2 patterns (provider.py:57-61) match any `keyword = <anything>` regardless of whether the RHS is a quoted secret or a literal/boolean/name. `.+` is greedy and unanchored to quotes, so `auth = True`, `token = None`, `secret = False`, `api_key = self.key` (attribute access, not a literal) all get mangled into `keyword = "[REDACTED]"`. This is the inverse failure of Finding 1/2: over-redaction that corrupts non-secret code rather than under-redaction that leaks secrets.

The AI summary is then computed on altered source, so the result can be misleading (e.g. "this function sets auth to a redacted secret" when it actually toggles a boolean), and the cached summary is wrong for the life of the cache.

## Evidence
```python
# Verified via execution:
from graps.ai.provider import scrub_secrets
out = scrub_secrets('auth = True\ntoken = None\nretry = 0\n')
# out == 'auth = "[REDACTED]"\ntoken = "[REDACTED]"\nretry = 0\n'
assert 'auth = "[REDACTED]"' in out
assert 'token = "[REDACTED]"' in out
```
`retry = 0` is untouched only because `retry` is not a keyword; `auth`/`token` are corrupted despite holding no secret.

## Steps to Reproduce
1. Generate an insight on a function containing `auth = True` or `token = None`.
2. The prompt sent to the AI contains `auth = "[REDACTED]"` instead of `auth = True`.
3. The AI summarizes corrupted code; the (wrong) summary is cached.

## Expected Behavior
Only quoted/secret-like RHS values are redacted; bare booleans, `None`, numbers, and attribute accesses are preserved.

## Actual Behavior
Any `keyword = <anything>` is rewritten to `keyword = "[REDACTED]"`, corrupting non-secret code.

## Root Cause
The regex matches on the keyword + `=` without requiring a quoted/literal secret on the RHS. `.+` is too permissive. There is no "is the RHS actually a secret?" gate.

## Blast Radius
Module — every insight for source using these keywords as flag/attribute names. Common in auth middleware, token caches, credential managers.

## Impact
- **Correctness (Medium):** AI summaries are based on altered source → wrong `role`/`importance`/`hidden_assumption`.
- **Data:** wrong summaries cached; persist until `modified_at` changes.
- **Trust:** users may act on misleading AI insights.

## Recommendation
- **Fix:** require a quoted value on the RHS, e.g. `(?i)(password|...)\s*=\s*["']([^"']+)["']` and redact only the captured quoted value (not the whole line). Leave bare names/booleans/`None`/numbers untouched.
- **Prevention:** test scrub with `auth = True`, `token = None`, `secret = False`, `api_key = self.key` → all preserved; and `password = "x"` → value redacted.
- **Long-term:** an AST-aware scrubber distinguishes string-literal assignments from other expressions cleanly.

## Test Cases
- `scrub_secrets('auth = True')` → unchanged.
- `scrub_secrets('token = None')` → unchanged.
- `scrub_secrets('secret = False')` → unchanged.
- `scrub_secrets('api_key = self.key')` → unchanged (attribute access).
- `scrub_secrets('password = "real"')` → `"real"` redacted (still works).

## Regression Risk
Medium. Tightening the regex to require quotes could let through some single-quoted/adjacent-secret forms Finding 1 covers — coordinate both fixes; prefer redacting the captured *value* rather than the whole line.

## Related Code Path
`graps/ai/provider.py:57-61` — `_SENSITIVE_PATTERNS` (greedy `.+` RHS)  
`graps/ai/provider.py:93-98` — Layer-2 `.sub` application

---


# Finding 9

## Title
`_parse_summary` passes through truthy non-string types (`int`/`list`/`dict`) for the three fields → violates the "string fields" contract, downstream crash risk (residual of report-bug-finder Finding 8)

## Severity
Medium

## Likelihood
Low

## Confidence
High

## Category
Type Contract Violation / Correctness / Downstream Crash Risk

## Scenario
The AI returns a JSON object where a field is a non-string truthy value, e.g. `{"role": 123, "importance": ["a","b"], "hidden_assumption": {"x":1}}` or `{"role": 0, "importance": false, ...}`. `_parse_summary` returns these as-is (or coerces only falsy ones to `""`). The documented contract (provider.py:126-130, "exactly these string fields") and every downstream consumer (cache JSON write, frontend `esc()`, future `len()`/concat) assume strings.

## Description
`_parse_summary` (provider.py:269-273):
```python
return {
    "role": data.get("role") or "",
    "importance": data.get("importance") or "",
    "hidden_assumption": data.get("hidden_assumption") or "",
}
```
`or ""` converts *falsy* values (`None`, `0`, `False`, `""`, `[]`, `{}`) to `""` — this fixed the explicit-`null` case from report-bug-finder Finding 8. But **truthy** non-strings (`123`, `["a"]`, `{"x":1}`) are returned unchanged. So:
- `role: 123` → `123` (int) in the result.
- `importance: [1,2]` → `list`.
- `hidden_assumption: {"x":1}` → `dict`.

These then get written into the cache (fine for JSON) but break any string-typed consumer and produce confusing UI (`esc(123)` → "123", `esc([...])` → "1,2"). The type contract is silently broken for truthy non-strings.

Additionally, `or ""` is *lossy*: a legitimate `role: 0` or `importance: false` (if those were ever meaningful) becomes `""` — but since the contract is "string", that is arguably acceptable; the real issue is the truthy-non-string pass-through.

## Evidence
```python
# Verified via execution:
from graps.ai.provider import _parse_summary
r = _parse_summary('{"role": 123, "importance": [1,2], "hidden_assumption": {"x":1}}')
# r == {"role": 123, "importance": [1, 2], "hidden_assumption": {"x": 1}}
type(r["role"])            # <class 'int'>
type(r["importance"])      # <class 'list'>
type(r["hidden_assumption"])  # <class 'dict'>
# falsy coercion:
r2 = _parse_summary('{"role": 0, "importance": false, "hidden_assumption": ""}')
# r2 == {"role": "", "importance": "", "hidden_assumption": ""}  (0/False -> "" via `or`)
```

## Steps to Reproduce
1. Monkeypatch `generate_summary` to return `{"role": 123, "importance": [1], "hidden_assumption": {"x":1}}` (or use a model that emits non-string fields).
2. Call `post_summary`; the returned/cached `summary` has non-string fields.
3. Any downstream string op (`len`, concatenation, strict frontend) misbehaves.

## Expected Behavior
All three fields are coerced to `str` (or rejected as `parse_failed`) so the "string fields" contract holds for every value, not just falsy ones.

## Actual Behavior
Truthy non-strings pass through unchanged; falsy non-strings become `""`.

## Root Cause
`or ""` only handles falsy. There is no `str(...)` coercion or type validation. The ponytail comment (provider.py:265-266) explicitly defers per-field type validation ("tambahkan kalau ada bug nyata") — this is that bug.

## Blast Radius
Module — `_parse_summary` output; affects all consumers (cache, frontend, future backend code).

## Impact
- **Correctness:** contract violation; downstream string-typed code can crash (`len(123)` → `TypeError`) or render garbage.
- **Frontend:** `esc(123)` renders "123"; `esc([1,2])` renders "1,2" — confusing but not a crash.
- **Cache:** non-string values persist; no auto-recovery.

## Recommendation
- **Fix:** coerce explicitly: `"role": str(data["role"]) if data.get("role") is not None else ""` — or simpler, validate and `raise AIError("parse_failed")` when a field is present but not a string, since the prompt asks for strings. Rejecting is safer than silently coercing (coercion can hide a malformed model response that should be retried).
- **Prevention:** test `_parse_summary` with int/list/dict/bool/null/missing for each field.
- **Monitoring:** count `parse_failed`/`non_string_field` events.

## Test Cases
- `role: 123` → either `parse_failed` or `"123"` (per chosen fix; document the choice).
- `role: [1]` → same.
- `role: null` → `""` (existing behavior preserved).
- `role` missing → `""` (preserved).
- `role: "valid"` → `"valid"` (preserved).

## Regression Risk
Low–Medium. Rejecting non-strings turns previously-"successful" malformed responses into `parse_failed` (more honest, but increases the parse-failure rate Finding 4 also raises — coordinate so legitimate summaries still succeed).

## Related Code Path
`graps/ai/provider.py:256-273` — `_parse_summary` (`or ""` coercion)  
`graps/server/app.py:194,202` — `summary` stored to cache / returned

---


# Finding 10

## Title
`_cache_locks` dict grows unbounded — one `threading.Lock` per distinct `cache_path`, never evicted (slow memory leak)

## Severity
Low

## Likelihood
Low

## Confidence
High

## Category
Performance / Resource Leak / Maintainability

## Scenario
`_get_lock` (cache.py:62-64) does `_cache_locks.setdefault(cache_path, threading.Lock())` under a guard lock, but no path is ever removed from `_cache_locks`. In the normal graps deployment `cache_path` is fixed per app, so the dict holds one entry — harmless. But any caller that varies `cache_path` (tests creating temp caches, a future multi-project/multi-cache feature, a CLI that scans many roots with per-root caches) adds one `Lock` + one `Path` key per distinct path, permanently. Over a long-lived process with many distinct paths this is a slow leak.

## Description
The lock registry (cache.py:58-64) is a module-global `dict[Path, Lock]` with insert-only semantics. There is no eviction (LRU/weakref/expire). `Path` objects and `Lock` objects accumulate. Each is small, but unbounded growth in a long-running process is a resource leak.

## Evidence
```python
# Verified by code reading + execution:
from graps.ai import cache as cm
import tempfile
from pathlib import Path
n0 = len(cm._cache_locks)
with tempfile.TemporaryDirectory() as d:
    cm._get_lock(Path(d)/"a.json"); cm._get_lock(Path(d)/"b.json")
n1 = len(cm._cache_locks)
assert n1 == n0 + 2          # entries added, never removed
# (paths under the tempdir are now gone on disk but still referenced in _cache_locks)
```

## Steps to Reproduce
1. In a long-lived process, call `write_cache`/`read_cache` with N distinct `cache_path` values.
2. `len(_cache_locks) == N` and never decreases.

## Expected Behavior
Locks for paths no longer in use are evicted (or the registry is bounded), or the dict is documented as fixed-scope.

## Actual Behavior
Unbounded insert-only growth.

## Root Cause
Insert-only registry with no eviction policy. The "one lock per path" design is fine for a fixed cache_path; the leak only manifests when paths vary, which the current design doesn't anticipate.

## Blast Radius
Local — the leaking process only. No correctness impact.

## Impact
- **Performance (Low):** slow memory growth in processes that vary cache paths; negligible for the single-path deployment.
- **Maintainability:** a hidden global with unbounded growth is a footgun for future features.

## Recommendation
- **Fix (lazy):** since the lock is only needed while a write is in flight, a simpler model is a single module-level `Lock` serializing all writes (the ponytail comment at cache.py:77-79 already notes multi-process is unsupported; a single lock is acceptable for in-process). Or keep per-path locks but evict when the set of writers drops to zero (refcount).
- **Prevention:** test that `_cache_locks` does not grow without bound across many temp paths (or document the fixed-scope assumption).
- **Long-term:** if multi-cache ever ships, use `weakref` or an LRU bound.

## Test Cases
- 1000 distinct temp paths → `_cache_locks` bounded (after fix) or documented as expected growth (before fix).
- Repeated same path → one entry (existing behavior preserved).

## Regression Risk
Low. Switching to a single global lock slightly reduces write concurrency but the current per-path lock only matters for concurrent writes to *different* caches, which is not a supported use case today.

## Related Code Path
`graps/ai/cache.py:58-64` — `_cache_locks` / `_get_lock`

---


# Finding 11

## Title
`write_cache` can leave an orphan `.tmp` file on mid-write failure (disk full / error between `write_text` and `replace`) — no cleanup, resource leak

## Severity
Low

## Likelihood
Low

## Confidence
Medium

## Category
Reliability / Resource Leak / Error Handling

## Scenario
`write_cache` (cache.py:86-95) creates a uniquely-named `.tmp` (`<stem>.<pid>.<ident>.tmp`), writes it, `chmod`s it, then `replace`s it onto the cache path. If a failure occurs **after** `tmp.write_text(...)` starts but **before** `replace` (e.g. disk full mid-`write_text`, `chmod` fails, process killed), the `.tmp` file is left on disk and never cleaned up. There is no `try/finally` to remove it.

## Description
The write sequence has no cleanup path:
```python
tmp = cache_path.with_name(f"{cache_path.stem}.{os.getpid()}.{threading.get_ident()}.tmp")
tmp.write_text(json.dumps(data, indent=2))   # can fail mid-write (disk full)
os.chmod(tmp, 0o600)                          # can fail
tmp.replace(cache_path)                       # can fail
```
A failure at any of these leaves the `.tmp` behind. Because the name includes `pid`+`ident`, subsequent writes use a different name, so orphans accumulate (one per failed write) rather than being reused. The common in-process serialization failure (`json.dumps` raising on a non-serializable entry) happens *before* `write_text`, so no orphan is created in that case — but I/O failures during/after `write_text` do leave orphans.

Note: I could **not** reproduce an orphan via the `json.dumps` failure path (it raises before `write_text`, so no `.tmp` is created). The orphan risk is real for the I/O-mid-write path, which is harder to trigger deterministically; hence Confidence = Medium.

## Evidence
```python
# Verified via execution (json.dumps failure path -> NO orphan, because
# write_text is never reached):
import tempfile
from pathlib import Path
from graps.ai import cache as cm
with tempfile.TemporaryDirectory() as d:
    p = Path(d)/"c.json"
    cm.write_cache(p,"k",{"file_modified_at":"x","summary":{}})
    class Bad: pass
    try: cm.write_cache(p,"k2",{"s": Bad()})
    except TypeError: pass
    assert not list(Path(d).glob("*.tmp"))   # no orphan in THIS path
# The orphan risk remains for write_text/chmod/replace I/O failures,
# which are not exercised here.
```

## Steps to Reproduce
1. Fill the disk (or mock `write_text`/`chmod`/`replace` to raise) so a failure occurs after `tmp` is created.
2. Call `write_cache`.
3. A `<stem>.<pid>.<ident>.tmp` file remains in the cache directory and is never removed.

## Expected Behavior
A failed write cleans up its `.tmp` (e.g. `try/finally: tmp.unlink(missing_ok=True)`), so the cache directory does not accumulate orphan temp files.

## Actual Behavior
Orphan `.tmp` files accumulate on mid-write I/O failures.

## Root Cause
No `try/finally` cleanup around the tmp lifecycle. The unique-per-call naming (good for avoiding cross-write collisions, per the report-bug-finder Finding 3 fix) means orphans are never overwritten by later writes.

## Blast Radius
Local — the cache directory only. No correctness impact (the real cache file is untouched on failure since `replace` didn't happen).

## Impact
- **Resource leak (Low):** orphan files consume disk; in a long-running process with repeated failures (e.g. chronic disk pressure) they accumulate.
- **Hygiene:** clutter in the cache dir; no signal to the user.

## Recommendation
- **Fix:** wrap the write in `try/finally`: set `tmp = None` after a successful `replace`, and in `finally` unlink `tmp` if it is still set and exists (`missing_ok=True`).
- **Prevention:** test that a forced failure between write and replace leaves no `.tmp`.
- **Monitoring:** alert on `.tmp` files older than N minutes in the cache dir.

## Test Cases
- Mock `tmp.replace` to raise → after `write_cache` raises, no `.tmp` remains.
- Mock `os.chmod` to raise → same.
- Disk-full simulation on `write_text` → same.

## Regression Risk
Low. Cleanup only runs on the failure path; success path unchanged.

## Related Code Path
`graps/ai/cache.py:86-95` — `write_cache` tmp lifecycle (no finally)

---


## Coverage Checklist (graps/ai)

| Dimension | Status | Notes |
|-----------|--------|-------|
| Happy Path | Evaluated | `read_cache`/`write_cache` roundtrip, `scrub_secrets` single-line, `get_provider` selection, `_parse_summary` bare JSON — covered by existing self-checks; no new bug. |
| Unhappy Path | Evaluated | Findings 3,4,5,6 (corrupt cache, parse wrapper, malformed entry, unreadable file). |
| Edge Case | Evaluated | Findings 1,2,8 (multi-line/dict-literal/flag-form scrub). |
| Corner Case | Evaluated | Findings 9,11 (truthy non-string parse, orphan tmp). |
| Use Case | Evaluated | Normal AI insight flow end-to-end via `post_summary`. |
| Misuse Case | Evaluated | Hand-edited/corrupt cache (F3,5,6); oddly-formatted AI response (F4,9). |
| Boundary Conditions | Evaluated | Empty source already covered by report-bug-finder Finding 7 (+ server guard now present app.py:144). Timestamp format boundary → F7. |
| Failure Modes | Evaluated | Findings 3,4,5,6,11. |
| Error Handling | Evaluated | Narrow `read_cache` except (F6); no salvage on `parse_failed` (F4); no `try/finally` (F11). |
| Concurrency | Evaluated | Lost-update already fixed (report-bug-finder Finding 3 → per-path lock). Residual: lock registry unbounded (F10). Multi-process still unsupported (documented). No new race in stateless `scrub_secrets`/`_parse_summary`. |
| Security | Evaluated | Findings 1,2 (secret leakage); F8 (over-redaction correctness). API key handling (env-read, no instance attr) — no new issue. |
| Performance | Evaluated | In-memory cache already added (report-bug-finder Finding 13). Residual: F7 (cache bust → redundant provider calls), F10 (lock leak). |
| Scalability | Evaluated | F10 (lock registry growth). No per-request unbounded work otherwise. |
| Reliability | Evaluated | Findings 3,4,5,6,7,11. |
| Maintainability | Evaluated | F10 (hidden global); F9 deferred validation acknowledged in code; shared `scrub` assumptions across two layers (F1,2,8). |
| Architecture | Evaluated | No SPOF beyond the single cache file (acceptable for local-first tool). Optional-dep degraded mode (F2) is an architecture-level security cliff. |
| Regression Risk | Evaluated per finding | All Low–Medium except where noted (F7 Medium, F9 Low–Medium). |
| Breaking Change Risk | Evaluated per finding | All fixes additive/guard-based; no API signature changes. F9's "reject non-string" option would increase parse-failure rate (coordinate with F4). |

**Categories that could not be fully evaluated:**
- «Network instability / retry-storm / circuit-breaker at the provider level»: the SDKs (`anthropic`/`openai`) own HTTP retry; graps wraps them with a single `timeout=30.0` and maps exceptions to `AIError` with no app-level retry/backoff. Behavior under sustained 429/5xx with SDK internal retries was not executed (no live API key in this environment). The `rate_limited` path surfaces `retry_after` but the caller (`post_summary`) does not honor it (no backoff/sleep/cache-short-circuit) — a reliability gap worth a follow-up, but not executed/confirmed here.
- «Cold start / warm start»: «Not enough information to evaluate» (deployment model unspecified).
- «Multi-process cache access»: documented as unsupported (cache.py:77-79); «Not enough information to evaluate» beyond the documented limitation.

---

*Report generated by Bug Hunter agent. All findings verified by execution unless marked «could not be fully evaluated». No source code was modified.*

