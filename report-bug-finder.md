# Bug Hunter Report — graps
**Branch:** `phase1-scanner-core` (includes Phase 1, 2, 3)  
**Reviewed:** All source modules — `graps/scanner/`, `graps/ai/`, `graps/server/`, `graps/frontend/`, `graps/cli.py`  
**Method:** Full source read → hypothesis collection → execution-based verification  
**Date:** 2026-07-01

---

## Summary

| # | Title | Severity | Likelihood | Confidence |
|---|-------|----------|------------|------------|
| 1 | constants wiring silently ignores ParsedFile.constants | High | High | High |
| 2 | CSRF guard bypass via missing Origin header | High | Medium | High |
| 3 | write_cache concurrent lost-update + shared tmp filename race | High | Medium | High |
| 4 | TOCTOU race in _port_free → late startup crash | Medium | Medium | High |
| 5 | _warn_if_cache_not_ignored crashes on non-UTF-8 .gitignore | Medium | Medium | High |
| 6 | threading.Timer not daemon → process may hang on startup failure | Medium | Low | High |
| 7 | AI called with empty source="" — no server-side guard | Medium | High | High |
| 8 | _parse_summary returns None for explicit-null AI fields | Medium | Medium | High |
| 9 | sanitize_constant_value docstring example misleads about detection layer | Low | High | High |
| 10 | resolve_import called twice per import — no caching | Low | High | High |
| 11 | validate_host case-sensitive comparison may reject legitimate clients | Low | Low | High |
| 12 | Dead-code filter silently hides files with zero functions | Low | High | High |
| 13 | cache.read_cache full file I/O on every POST /api/ai/summary request | Low | High | High |
| 14 | basename() defined identically in graph.js and panel.js | Informational | — | High |

---

# Finding 1

## Title
`graph_builder._build_node` hardcodes `_sanitized_constants([])` — ignores `ParsedFile.constants` permanently

## Severity
High

## Likelihood
High

## Confidence
High

## Category
Functional Bug / Silent Data Loss / Maintainability

## Scenario
Phase 2 parser begins extracting constants and populates `ParsedFile.constants`. Developer runs graps expecting constants to appear in the graph JSON and UI. They never appear. No error. No warning.

## Description
`graph_builder.py` line 93 calls `_sanitized_constants([])` with a hardcoded empty list literal instead of `result.constants`. The field exists on the dataclass (`ParsedFile.constants: list[dict]`, defined in `__init__.py` line 63), and `C-01` sanitization is wired — but the input is always `[]`, unconditionally, regardless of what the parser provides.

The HANDOFF comment says "C-01 wired here so it cannot be bypassed once data arrives" — but arrival of data from the parser does NOT automatically wire through. A code change at this exact line is required, meaning the wiring claim is misleading.

## Evidence
```
# Verified via execution:
file_with_consts = ParsedFile(
    constants=[{"name": "DB_HOST", "value": "localhost", "line": 1}]
)
graph = build_graph([file_with_consts], root)
graph["nodes"][0]["constants"]  # → []   BUG CONFIRMED
```
`graph_builder.py` line 93:
```python
"constants": _sanitized_constants([]),  # ponytail: Phase 2 supplies raw constants
```

## Steps to Reproduce
1. Create a `ParsedFile` with a non-empty `constants` list.
2. Call `build_graph([pf], root)`.
3. Inspect `graph["nodes"][0]["constants"]` — always `[]`.

## Expected Behavior
`_sanitized_constants(result.constants)` — constants from the parser flow through sanitization into the graph output.

## Actual Behavior
`_sanitized_constants([])` — graph node constants is always empty regardless of upstream data.

## Root Cause
The placeholder comment was written to say "will be filled when Phase 2 arrives" but the placeholder is not a `TODO` that naturally breaks when data arrives — it is valid, running code that silently discards incoming data. The developer who implements Phase 2 parser must also remember to change this one line in `graph_builder.py`, but there is no compile-time, test-time, or runtime signal that this is required.

## Blast Radius
Module — scanner pipeline. Constants never appear in graph JSON or frontend UI regardless of parser state.

## Impact
- Phase 2 constants feature will appear broken without a clear error.
- Silent data loss: any constant extracted by parser is silently discarded.
- Security: C-01 sanitization is bypassed in practice (no data reaches it).
- Developer time wasted debugging why Phase 2 "doesn't work."

## Recommendation
Change line 93 of `graph_builder.py`:
```python
# BEFORE
"constants": _sanitized_constants([]),

# AFTER
"constants": _sanitized_constants(result.constants),
```
Add a regression test that creates a `ParsedFile` with constants and asserts they appear in `build_graph` output.

## Test Cases
- `ParsedFile(constants=[{"name":"X","value":"1","line":1}])` → `graph["nodes"][0]["constants"]` must be non-empty.
- `ParsedFile(constants=[{"name":"DB_PASSWORD","value":"secret","line":1}])` → value must be `"[REDACTED]"`.

## Regression Risk
High. Any future test that verifies constants in graph output will fail until this is fixed. The current test suite does not catch this because no test constructs a `ParsedFile` with non-empty constants and asserts graph output.

## Related Code Path
`graps/scanner/graph_builder.py:93` → `_sanitized_constants`  
`graps/scanner/__init__.py:63` — `ParsedFile.constants` field definition

---

# Finding 2

## Title
`enforce_origin` CSRF guard bypassed by omitting the `Origin` header entirely

## Severity
High

## Likelihood
Medium

## Confidence
High

## Category
Security / CSRF / Missing Validation

## Scenario
A script or tool running on the same machine as graps server sends a POST to `/api/ai/summary` without an `Origin` header. The CSRF guard does not fire. The request is processed.

## Description
`app.py` line 104 guards POST/PUT/DELETE with:
```python
if origin and not any(origin.startswith(a) for a in allowed):
    return JSONResponse({"error": "Forbidden"}, status_code=403)
```
When `origin = ""` (falsy — header absent), the `if origin` short-circuits to `False`. The guard is entirely skipped. Any tool that can reach `127.0.0.1:{port}` and knows the correct `Host` header can POST without restriction.

The security model states that browser-based CSRF requires Origin header to be set by the browser — which is true. However, non-browser clients (curl, Python requests, local scripts, malware with local access) can omit Origin freely and bypass this guard completely.

## Evidence
```
# Verified via TestClient:
r = client.post("/api/ai/summary", json=body, headers={"host": HOST_OK})
# NO origin header in request
r.status_code  # → 200  (not 403)
r.json()       # → {"enabled": False, "reason": "no_api_key"}
```

## Steps to Reproduce
```bash
curl -X POST http://127.0.0.1:8765/api/ai/summary \
  -H "Host: 127.0.0.1:8765" \
  -H "Content-Type: application/json" \
  -d '{"file":"x.py","function":"f","line":1,"modified_at":"","source":"..."}'
```
No `Origin` header → 200 response, not 403.

## Expected Behavior
Requests without an `Origin` header should either be rejected (fail-closed) or explicitly documented as allowed with reasoning.

## Actual Behavior
Requests without `Origin` are silently allowed through the CSRF guard.

## Root Cause
Guard logic uses `if origin and ...` — a falsy-empty string short-circuits the entire condition. The intent was "allow requests from the browser same-origin" but the implementation reads as "skip check if no origin is provided."

## Blast Radius
Service — `/api/ai/summary` endpoint. Any process with local access can invoke AI summarization and write to cache without going through the browser.

## Impact
- AI API key consumed by unauthorized local processes.
- Cache file written with attacker-controlled key names.
- If server is ever exposed beyond localhost (deployment change), becomes a direct CSRF vector.

## Recommendation
Fail-closed: reject requests with no Origin header for state-mutating methods:
```python
if request.method in ("POST", "PUT", "DELETE"):
    origin = request.headers.get("origin", "")
    if not origin or not any(origin.startswith(a) for a in allowed):
        return JSONResponse({"error": "Forbidden"}, status_code=403)
```

## Test Cases
- POST to `/api/ai/summary` with no `Origin` header → expect 403.
- POST with `Origin: ""` (empty string) → expect 403.

## Regression Risk
High. Existing self-check (app.py `__main__`) does not test the no-origin scenario.

## Related Code Path
`graps/server/app.py:99-106` — `enforce_origin` middleware

---

# Finding 3

## Title
`write_cache` concurrent writes: lost-update race + deterministic `.tmp` filename collision

## Severity
High

## Likelihood
Medium

## Confidence
High

## Category
Concurrency / Race Condition / Data Integrity

## Scenario
Two concurrent POST requests to `/api/ai/summary` for the same `file::function` key arrive simultaneously. Both miss cache. Both call the AI provider (double API cost). Both call `write_cache` concurrently with the same `cache_path`.

## Description
Two separate issues compound in `cache.py`:

**Issue A — Lost-update race (read-modify-write not atomic):**
`write_cache` does `read_cache()` → modify in memory → write to `.tmp` → rename. If two writers both `read_cache` before either finishes writing, the second writer's final rename overwrites the first, discarding that entry. This is the classic lost-update pattern.

**Issue B — Shared `.tmp` filename:**
`tmp = cache_path.with_suffix(cache_path.suffix + ".tmp")` produces a deterministic path (`cache.json.tmp`). Two concurrent writers both open this same path for writing. Writer A writes its data; Writer B immediately overwrites the same `.tmp` file; Writer A calls `os.chmod(tmp, 0o600)` and `tmp.replace(cache_path)` but the content it renames is Writer B's data, not its own. The result is a cache entry that is a mix of two writes that are not consistent with either transaction.

**FastAPI sync route runs in thread pool:** `post_summary` is defined as `def` (not `async def`), meaning Starlette runs it in a thread pool. Two simultaneous requests will execute concurrently in different threads — this is not a theoretical scenario.

## Evidence
```python
# Verified: tmp filename is deterministic
p = Path("cache.json")
tmp = p.with_suffix(p.suffix + ".tmp")
# tmp → PosixPath('cache.json.tmp')  — same for all concurrent callers

# Verified: sync FastAPI route runs in thread pool (Starlette default behavior)
# def post_summary(req: SummaryRequest) → executed in threadpool
```

## Steps to Reproduce
1. Start graps server with a valid AI API key.
2. Send two concurrent POST requests to `/api/ai/summary` for the same function before the first completes (within the AI provider's 30-second timeout window).
3. Observe: AI provider called twice (double cost). Cache file may reflect only one write.

## Expected Behavior
Only one AI API call per `file::function` key within a time window. Both requests receive the same result. Cache is consistent.

## Actual Behavior
Both requests call the AI provider. Cache write race — one entry may be lost, or the `.tmp` file content is a mixture of both writes.

## Root Cause
No mutual exclusion exists around the read-modify-write cycle. The atomic rename of `.tmp` → final path prevents partial reads by consumers, but does not prevent multiple concurrent producers from simultaneously reading stale state and overwriting each other.

## Blast Radius
Service — all concurrent AI summary requests. Cache file integrity.

## Impact
- Duplicate AI API costs for concurrent requests to the same function.
- Cache entry loss under concurrency.
- In worst-case `.tmp` race: cache file contains data from one writer's read-phase merged with another writer's write-phase — logically inconsistent cache state.

## Recommendation
Short-term: Use a per-`cache_path` `threading.Lock` to serialize `write_cache` calls:
```python
import threading
_cache_locks: dict[Path, threading.Lock] = {}
_cache_locks_lock = threading.Lock()

def _get_lock(cache_path: Path) -> threading.Lock:
    with _cache_locks_lock:
        return _cache_locks.setdefault(cache_path, threading.Lock())

def write_cache(cache_path, key, entry):
    with _get_lock(cache_path):
        # existing logic
```
Also use a unique tmp filename per call: `cache_path.with_name(cache_path.stem + f".{os.getpid()}.{threading.get_ident()}.tmp")`.

Long-term: Use SQLite (which handles concurrent writes natively) instead of a JSON file.

## Test Cases
- Concurrent `write_cache` calls with different keys → both keys present after completion.
- Concurrent `write_cache` calls with the same key → exactly one value in cache (idempotent).

## Regression Risk
Medium. Race is timing-dependent; hard to reproduce reliably in unit tests without explicit concurrency harness.

## Related Code Path
`graps/ai/cache.py:49-67` — `write_cache`  
`graps/server/app.py:121-176` — `post_summary` (sync route, runs in thread pool)

---

# Finding 4

## Title
TOCTOU race in `_port_free` — port check does not guarantee availability at bind time

## Severity
Medium

## Likelihood
Medium

## Confidence
High

## Category
TOCTOU / Reliability / Startup

## Scenario
User runs `graps .`. `_port_free(8765)` returns `True`. Between that return and `uvicorn.Server.run()` actually binding the socket, another process on the system claims port 8765. `uvicorn.Server.run()` raises `OSError: [Errno 98] Address already in use` — but only after scanning is complete, graph is built, and app is created. All that work is discarded. The error message from uvicorn is not the friendly message shown by the pre-flight check.

## Description
`_port_free()` binds then immediately closes a socket to test availability. The port is released before the function returns. This creates a window between the check and the actual `uvicorn.Config`/`server.run()` bind. Any process can claim the port during this window (other graps invocations, other servers, OS ephemeral port reuse). The pre-flight check provides false confidence, not guaranteed availability.

## Evidence
```python
# Verified via execution:
result["free_check"] = _port_free(test_port)  # → True (port released)
# Immediately after, another thread binds the same port
result["bind_after_check"]  # → "SUCCESS — port berhasil di-claim pihak lain"
# The TOCTOU window is real and demonstrable
```

## Steps to Reproduce
1. On a busy system, run `graps .` multiple times concurrently targeting the same port.
2. Or: write a script that binds port 8765 immediately after `_port_free` would release it.
3. Result: process gets past the pre-flight check, does full scan, then crashes at `server.run()`.

## Expected Behavior
Either: pre-flight check is reliable (fail-fast before scan), or: the startup failure at `server.run()` is caught and displays the same user-friendly error message.

## Actual Behavior
Pre-flight check passes, scan runs (~seconds for large repos), then uvicorn fails with an OS-level error that bypasses the user-friendly message at line 188-189.

## Root Cause
The check and the actual bind are two separate socket operations. There is no way to "hold" a port between the check and the bind without keeping the socket open.

## Blast Radius
Local — startup only. Does not affect running instances.

## Impact
- User sees a raw uvicorn error after waiting through a full scan.
- Pre-flight check gives false confidence.

## Recommendation
Wrap `server.run()` in a try/except for `OSError` with errno EADDRINUSE, and display the same friendly message:
```python
try:
    server.run()
except OSError as e:
    import errno
    if e.errno == errno.EADDRINUSE:
        typer.echo(f"  ✗ Port {port} already in use. Try: graps . --port {port + 1}")
        raise typer.Exit(1)
    raise
```
Optionally remove `_port_free` entirely — it provides no guarantee and the try/except is sufficient.

## Test Cases
- Mock `uvicorn.Server.run` to raise `OSError(errno.EADDRINUSE, ...)` → CLI exits with non-zero and prints friendly message.

## Regression Risk
Low. `_port_free` removal or wrapping does not affect the scanner or graph output.

## Related Code Path
`graps/cli.py:64-73` — `_port_free`  
`graps/cli.py:187-189` — pre-flight check  
`graps/cli.py:202-211` — `server.run()` block

---

# Finding 5

## Title
`_warn_if_cache_not_ignored` crashes with `UnicodeDecodeError` on non-UTF-8 `.gitignore`

## Severity
Medium

## Likelihood
Medium

## Confidence
High

## Category
Validation / Error Handling / Encoding

## Scenario
User has a `.gitignore` file created on Windows or with a BOM, or containing latin-1 characters (e.g., accented paths). `graps .` crashes immediately at startup before scanning begins.

## Description
`cli.py` line 90 calls `gitignore.read_text()` with no `encoding` or `errors` argument. Python's default is `locale.getpreferredencoding(False)` which on many Linux/VPS systems is UTF-8. A `.gitignore` file with any non-UTF-8 byte (Windows-1252, BOM, accented filenames) will raise `UnicodeDecodeError`. This exception is not caught. The process exits with an unhandled exception traceback rather than a friendly startup message.

## Evidence
```python
# Verified via execution:
gitignore.write_bytes(b"*.pyc\n\xff\xfe.venv\n")  # latin-1 / BOM bytes
_warn_if_cache_not_ignored(root)
# → UnicodeDecodeError: 'utf-8' codec can't decode byte 0xff in position 6
```

## Steps to Reproduce
1. Create a project with a `.gitignore` containing non-UTF-8 bytes (e.g., copy from a Windows machine).
2. Run `graps .`.
3. Observe traceback at startup.

## Expected Behavior
The `.gitignore` check is advisory (non-blocking by design per line 87 comment). A decode error should be silently ignored or logged, and the warning simply skipped.

## Actual Behavior
`UnicodeDecodeError` propagates uncaught — process crashes before scan begins.

## Root Cause
`Path.read_text()` without `errors="replace"` or a try/except. The function is documented as "non-blocking" but is actually a hard crash point for this input.

## Blast Radius
Local — startup only. Affects any user whose `.gitignore` contains non-ASCII bytes.

## Impact
- graps entirely unusable on affected projects.
- No scan ever begins; no error message explaining the cause.

## Recommendation
```python
def _warn_if_cache_not_ignored(root: Path) -> None:
    gitignore = root / ".gitignore"
    if gitignore.exists():
        try:
            content = gitignore.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return  # unreadable → skip warning silently
        if ".graps" not in content and ".graps/" not in content:
            typer.echo("  ⚠ .graps/ belum ada di .gitignore ...")
```

## Test Cases
- `.gitignore` with `\xff\xfe` (BOM) → `_warn_if_cache_not_ignored` does not raise.
- `.gitignore` with `\x80\x81` bytes → does not raise.
- `.gitignore` containing `.graps` → no warning printed.
- `.gitignore` without `.graps` → warning printed.

## Regression Risk
Low. Fix is purely additive error handling.

## Related Code Path
`graps/cli.py:82-96` — `_warn_if_cache_not_ignored`

---

# Finding 6

## Title
`threading.Timer` for browser open is not a daemon thread — process may hang if startup fails after timer is scheduled

## Severity
Medium

## Likelihood
Low

## Confidence
High

## Category
Reliability / Resource Leak / Startup

## Scenario
`server.run()` fails (e.g., port race from Finding 4, or any other exception). `KeyboardInterrupt` handler in `cli.py:208-211` runs `typer.Exit(0)`. But `threading.Timer` (scheduled at line 196) is already counting down as a non-daemon thread. Python's interpreter waits for all non-daemon threads to complete before exiting. The process hangs for up to 1 second (the timer delay) after the error, or if `webbrowser.open` itself hangs (slow default browser, missing X display on server), indefinitely.

## Evidence
```python
# Verified via execution:
t = threading.Timer(999, lambda: None)
t.daemon  # → False  (non-daemon by default)
# Python interpreter will not exit until all non-daemon threads finish.
```

## Steps to Reproduce
1. Schedule a `threading.Timer` for 1 second.
2. In main thread, raise an exception or call `sys.exit()` before the timer fires.
3. Observe: process does not exit cleanly for up to 1 second (or longer if timer callback hangs).

## Expected Behavior
Process exits immediately when `server.run()` ends or raises, regardless of pending timer.

## Actual Behavior
Process may hang waiting for the timer thread. On headless servers (VPS, CI), `webbrowser.open()` may block or hang on missing display.

## Root Cause
`threading.Timer` inherits `daemon=False` from `threading.Thread`. The timer is started unconditionally before `server.run()`. There is no cleanup path if `server.run()` fails before the timer fires.

## Blast Radius
Local — startup only. Does not affect running instances.

## Impact
- CLI appears to hang for 1+ seconds after unexpected server failure.
- On VPS/headless environments: `webbrowser.open()` may block indefinitely.

## Recommendation
```python
timer = threading.Timer(1.0, lambda: webbrowser.open(f"http://localhost:{port}"))
timer.daemon = True  # won't block process exit
timer.start()
```
Or cancel the timer in the exception/exit path.

## Test Cases
- Mock `server.run()` to raise immediately → process exits within 100ms.
- Headless environment with no DISPLAY → timer fires but does not block exit.

## Regression Risk
Low. Daemon flag change is a one-line fix.

## Related Code Path
`graps/cli.py:196-198` — `threading.Timer` scheduling

---

# Finding 7

## Title
AI provider called with empty source (`source=""`) — no server-side validation, AI receives no useful code

## Severity
Medium

## Likelihood
High

## Confidence
High

## Category
Functional / Missing Validation / AI Correctness

## Scenario
User clicks "Generate AI Insight" on any function. `panel.js` line 338 sends `source: ""` (hardcoded empty string) because raw source extraction is not yet implemented. The server accepts this, calls the AI provider with empty content, and charges one API call to produce a summary about nothing.

## Description
`panel.js:338` hardcodes `source: ""` with a `ponytail` comment acknowledging this is temporary. The server's `SummaryRequest` model (`app.py:51-64`) documents "no length validation — provider will reject if over limit." But empty string is never rejected. The AI provider `scrub_secrets("")` returns `""`, `_build_prompt("", ctx)` builds a prompt asking AI to analyze a function with empty source. The AI call succeeds, returns a summary, is cached, and billed.

## Evidence
```python
# Verified via execution:
call_log = []  # spy on generate_summary
# POST with source=""
# → provider called with source: ['']
# → AI call proceeds normally, returns summary, cached
```
`panel.js:337-339`:
```javascript
source: "",  // ponytail: parser belum ekstrak source raw
```

## Steps to Reproduce
1. Run `graps .` with a valid API key.
2. Open any file in the UI, click "Generate AI Insight" on any function.
3. Observe: AI called with empty source. API is billed. Cached result is based on no code.

## Expected Behavior
Server rejects `source: ""` with a 400 or returns `{"enabled": false, "reason": "no_source"}` to avoid billing an API call that will produce a meaningless summary.

## Actual Behavior
Empty source accepted, AI called, billed, result cached as if meaningful.

## Root Cause
Feature was shipped in two halves (frontend sends `source=""`, server does not validate it) with no coordination contract. The `ponytail` comment acknowledges the gap but there is no runtime guard.

## Blast Radius
Service — every "Generate AI Insight" click before source extraction is implemented.

## Impact
- Every AI call on every function costs API tokens for a meaningless empty-code analysis.
- Cache is populated with summaries of empty content — when source extraction is later implemented, cached entries will need invalidation (but `modified_at` is also `""` so cache will appear "valid").
- Wasted API budget.

## Recommendation
Add server-side guard in `post_summary`:
```python
if not req.source.strip():
    return {"enabled": False, "reason": "no_source"}
```
And/or add Pydantic validator: `@validator("source") def source_not_empty(cls, v): ...`

## Test Cases
- POST with `source=""` → `{"enabled": false, "reason": "no_source"}`, provider not called.
- POST with `source="   "` (whitespace only) → same rejection.

## Regression Risk
Medium. Once source extraction is implemented, this guard needs updating to allow non-empty sources.

## Related Code Path
`graps/frontend/panel.js:337-339` — hardcoded `source: ""`  
`graps/server/app.py:51-64` — `SummaryRequest` (no source validation)  
`graps/server/app.py:144-148` — `provider.generate_summary(req.source, ...)`

---

# Finding 8

## Title
`_parse_summary` returns `None` for fields with explicit `null` in AI response, violating string type contract

## Severity
Medium

## Likelihood
Medium

## Confidence
High

## Category
Type Contract Violation / Correctness / Downstream Crash Risk

## Scenario
An AI provider returns `{"role": "does something", "importance": null, "hidden_assumption": "none"}`. `_parse_summary` returns `{"role": "...", "importance": None, "hidden_assumption": "..."}`. Downstream code that assumes all three fields are strings (e.g., string concatenation, `len()`, template rendering) receives `None` and crashes or renders `null`.

## Description
`_parse_summary` (provider.py:267-271) uses `.get(key, "")` which only applies the default when the key is **absent**. If the AI returns `null` as an explicit JSON value for a field, `.get("importance", "")` returns `None` — not `""`. The function's documented contract is to return a dict of three string fields. This contract is silently broken for `null` values.

`panel.js` routes `null` through `esc()` which coerces `null` to the string `"null"` (via `String(null)` in `esc` line 21), so the UI will display the literal text "null" to the user — unexpected but not a crash on the frontend.

## Evidence
```python
# Verified via execution:
text = '{"role": "does something", "importance": null, "hidden_assumption": "none"}'
result = _parse_summary(text)
result["importance"]  # → None (not "")
type(result["importance"])  # → <class 'NoneType'>
```

## Steps to Reproduce
1. Monkeypatch `generate_summary` to return `{"role": "r", "importance": None, "hidden_assumption": "h"}`.
2. Call `post_summary`.
3. The cache entry's `summary.importance` is `None`.
4. Frontend `esc(null)` renders the literal text "null".

## Expected Behavior
`_parse_summary` always returns strings for all three fields, even when AI returns explicit `null`.

## Actual Behavior
Fields with explicit JSON `null` pass through as Python `None`.

## Root Cause
`dict.get(key, default)` — default is only used when key is missing, not when value is `None`. The distinction between "key absent" and "value is null" is not handled.

## Blast Radius
Module — `_parse_summary` output. Affects all AI summary consumers.

## Impact
- Frontend displays literal "null" text in the AI Insight panel.
- Any future backend consumer doing `len(summary["importance"])` or string operations will crash.
- Cache stores `None` — no automatic recovery without cache invalidation.

## Recommendation
```python
return {
    "role": data.get("role") or "",
    "importance": data.get("importance") or "",
    "hidden_assumption": data.get("hidden_assumption") or "",
}
```
Note: `or ""` handles both absent key and `None`/falsy value. If empty string vs `None` distinction matters, use explicit `if val is None` check.

## Test Cases
- AI returns `{"role": null, "importance": "x", "hidden_assumption": "y"}` → all three fields are strings in output.
- AI returns all three as `null` → all three are `""`.

## Regression Risk
Low. Fix is additive — no behavior change for the common case where AI returns strings.

## Related Code Path
`graps/ai/provider.py:256-271` — `_parse_summary`

---

# Finding 9

## Title
`sanitize_constant_value` docstring example for `WEBHOOK_SECRET` misleads about which detection layer triggers

## Severity
Low

## Likelihood
High

## Confidence
High

## Category
Documentation / Misleading Contract / Correctness

## Scenario
Developer adds a constant with a non-sensitive name (e.g., `MY_HOOK = "whsec_abc123"`). They read the docstring, see that `whsec_abc123` is listed as a redacted example, and assume value-based pattern detection will cover this case. In reality, `whsec_abc123` (6 chars after prefix) does NOT match the regex `whsec_[a-zA-Z0-9]{32,}` (requires 32+ chars). The constant is NOT redacted.

## Description
`sanitize.py` docstring line 58-59:
```
>>> sanitize_constant_value("WEBHOOK_SECRET", "whsec_abc123")
'[REDACTED]'
```
This is redacted because `"WEBHOOK_SECRET"` contains `"webhook_secret"` — a name-based keyword match (line 64). The docstring implies this example demonstrates webhook secret value detection. But the value `"whsec_abc123"` alone would NOT trigger value-based detection (regex requires 32+ chars after `whsec_`).

## Evidence
```python
# Verified:
sanitize_constant_value("MY_HOOK", "whsec_abc123")  # → "whsec_abc123" (NOT redacted)
# Name "MY_HOOK" not in keyword list, value too short for regex → passes through
```

## Steps to Reproduce
1. Store a constant `MY_HOOK = "whsec_abc123"` in source.
2. Call `sanitize_constant_value("MY_HOOK", "whsec_abc123")`.
3. Result: `"whsec_abc123"` (not redacted).

## Expected Behavior
Either: (a) docstring example uses a name in the keyword list AND notes that redaction is name-based; or (b) docstring uses a value long enough to trigger value-based detection (32+ chars after prefix).

## Actual Behavior
Docstring implies `whsec_abc123` is caught by value detection. It is actually caught by name detection only. Short `whsec_` values with non-sensitive names escape sanitization.

## Root Cause
Docstring example was written for a case where name and value both contribute, but the example only makes obvious which layer the author had in mind. The value regex was written for real Stripe webhook secrets (32+ hex chars), but the docstring uses a truncated placeholder that doesn't satisfy the regex.

## Blast Radius
Local — sanitize.py documentation only. No runtime impact for the documented example itself.

## Impact
- Developer may incorrectly believe short `whsec_` values are always caught.
- Real short webhook secrets with generic variable names escape C-01 sanitization.
- False confidence in sanitization coverage.

## Recommendation
Fix docstring to use a realistic example:
```python
>>> sanitize_constant_value("MY_WEBHOOK", "whsec_" + "a" * 32)
'[REDACTED]'
```
And add a comment clarifying the two detection layers and their independence.

## Test Cases
- `sanitize_constant_value("MY_HOOK", "whsec_" + "x" * 31)` → NOT redacted (value too short).
- `sanitize_constant_value("MY_HOOK", "whsec_" + "x" * 32)` → `"[REDACTED]"` (value regex matches).
- `sanitize_constant_value("WEBHOOK_SECRET", "whsec_abc")` → `"[REDACTED]"` (name-based).

## Regression Risk
Low. Documentation fix only; no behavior change.

## Related Code Path
`graps/scanner/sanitize.py:33` — value pattern `whsec_[a-zA-Z0-9]{32,}`  
`graps/scanner/sanitize.py:58-59` — misleading docstring example

---

# Finding 10

## Title
`resolve_import` called twice per import — once in `_build_node`, once in `_build_edges` — no result caching

## Severity
Low

## Likelihood
High

## Confidence
High

## Category
Performance / Scalability / Hot Path

## Scenario
A project with 200 files averaging 20 imports each has 4,000 imports. `build_graph` calls `_build_edges` (4,000 `resolve_import` calls) and `_build_node` × 200 files × 20 imports (4,000 more calls) = 8,000 filesystem stat/resolve operations total.

## Description
`resolve_import` performs filesystem operations on every call: `is_symlink()`, `is_file()`, `.resolve()`. In `graph_builder.py`, it is called independently in `_build_node` (line 77, for `resolved_path` field) and in `_build_edges` (line 109, for edge construction). There is no cache between these two call sites. Every import is resolved twice.

## Evidence
```python
# Verified via execution (spy on gb_mod.resolve_import):
# File with 1 import → resolve_import called 2 times
call_log  # → ['pkg.sub', 'pkg.sub']
# Double-call confirmed for every non-star, non-dynamic import
```

## Steps to Reproduce
Apply a spy to `graph_builder.resolve_import` and call `build_graph` with a file containing N imports. Observe 2N calls.

## Expected Behavior
Each import resolved once per `build_graph` call. Result memoized within the call.

## Actual Behavior
Each import resolved twice per `build_graph` call. 2× filesystem I/O overhead on the hot path.

## Root Cause
`_build_node` and `_build_edges` are independent functions with no shared state. There was no optimization pass after both functions were written.

## Blast Radius
Module — `graph_builder.build_graph` performance. Scales linearly with `O(2 × total_imports)`.

## Impact
- Doubles filesystem I/O during every scan.
- On large repos with many imports (1000+), noticeable latency increase.
- On slow filesystems or network mounts, this could be a significant bottleneck.

## Recommendation
Memoize `resolve_import` within a single `build_graph` call:
```python
from functools import lru_cache

def build_graph(results, root):
    @lru_cache(maxsize=None)
    def _cached_resolve(target, current_file, is_dynamic, is_star):
        imp = ParsedImport(target=target, is_dynamic=is_dynamic, is_star=is_star)
        return resolve_import(imp, current_file, root)
    # pass _cached_resolve to both _build_node and _build_edges
```
Or compute `resolved_path` once in `_build_edges` and attach it to the import object.

## Test Cases
- Spy confirms `resolve_import` called exactly once per unique `(target, current_file)` pair.
- Performance test: build_graph on 100-file repo completes within budget.

## Regression Risk
Low. Purely a performance optimization; behavior is unchanged.

## Related Code Path
`graps/scanner/graph_builder.py:77` — `_build_node` resolve call  
`graps/scanner/graph_builder.py:109` — `_build_edges` resolve call

---

# Finding 11

## Title
`validate_host` performs case-sensitive Host header comparison — may reject legitimate clients

## Severity
Low

## Likelihood
Low

## Confidence
High

## Category
Correctness / Compatibility

## Scenario
A reverse proxy, browser extension, or HTTP tool normalizes the `Host` header to uppercase (`LOCALHOST:8765`). The request is rejected with 400 even though it is the same host semantically.

## Description
`app.py:112`:
```python
if host not in (f"localhost:{port}", f"127.0.0.1:{port}"):
```
String comparison is case-sensitive. RFC 7230 specifies that host names in URIs are case-insensitive. A client sending `Host: LOCALHOST:8765` or `Host: Localhost:8765` will receive a 400 response.

## Evidence
```python
# Verified:
r = client.get("/api/graph", headers={"host": f"LOCALHOST:{PORT}"})
r.status_code  # → 400 (rejected)
```

## Steps to Reproduce
```bash
curl http://127.0.0.1:8765/api/graph -H "Host: LOCALHOST:8765"
# → 400 Invalid Host
```

## Expected Behavior
Host comparison is case-insensitive for the hostname portion.

## Actual Behavior
`LOCALHOST:8765` is rejected. `127.0.0.1:8765` is case-sensitive to IP notation (which in practice is always lowercase, so less of a risk).

## Root Cause
Simple string membership test without `.lower()` normalization.

## Blast Radius
Local — only affects non-standard clients. Browser-based access is unaffected.

## Impact
- Legitimate developer tools or proxies may be incorrectly blocked.
- Fail-closed direction (more restrictive than RFC), so no security impact.

## Recommendation
```python
host_lower = host.lower()
if host_lower not in (f"localhost:{port}", f"127.0.0.1:{port}"):
```
Note: `127.0.0.1` is an IP address, not a hostname — case normalization there is moot but harmless.

## Test Cases
- `Host: LOCALHOST:8765` → 200 (same as `localhost:8765`).
- `Host: evil.com:8765` → 400.

## Regression Risk
Low. One-line fix, behavior only changes for uppercase host strings.

## Related Code Path
`graps/server/app.py:108-114` — `validate_host` middleware

---

# Finding 12

## Title
Dead-code filter (`f.dead`) silently hides files with zero functions — incorrect semantics

## Severity
Low

## Likelihood
High

## Confidence
High

## Category
Functional / UI Logic / Correctness

## Scenario
User clicks "☠ Dead" filter to find unused code. All `__init__.py` files (which typically contain only imports, no function definitions) disappear from the graph. User thinks these files have no import relationships, when in fact they are infrastructure files. The filter is actively misleading.

## Description
`graph.js:93-101` — when the dead-code filter is active, `isDimmed(node)` evaluates:
```javascript
if (f.dead) {
  const fns = node.functions || [];
  if (fns.length === 0) return true;  // ← files with no functions are DIMMED (hidden)
  const allDead = fns.every(fn => fn.is_dead_code);
  if (!allDead) return true;
}
```
A file with zero functions is dimmed (hidden from "show dead code" view). But zero functions does not mean dead code — `__init__.py`, config files, and module-level scripts commonly have no functions. The filter should show files where ALL functions are dead, and treat zero-function files as neutral (not dead, not live).

## Evidence
From source read: `fns.length === 0 → return true` (dimmed). This is confirmed by reading the logic — a file with no functions is treated the same as a file that is "not all dead" — both are hidden when the dead filter is active.

## Steps to Reproduce
1. Scan a Python project with `__init__.py` files containing only imports.
2. Enable the "☠ Dead" filter.
3. Observe: all zero-function files disappear from graph view.

## Expected Behavior
Files with zero functions are treated as neutral — not dimmed by the dead-code filter. Only files where at least one function exists AND all functions are `is_dead_code=true` should be highlighted.

## Actual Behavior
Files with zero functions are dimmed (hidden) when the dead-code filter is active.

## Root Cause
The condition `fns.length === 0 → dim` was likely written to handle the "no functions → can't be dead → irrelevant → hide" case, but this contradicts the UX intent of "show me dead things" — hiding irrelevant things is different from showing dead things.

## Blast Radius
Local — frontend filter UI only. No data impact.

## Impact
- Infrastructure files (`__init__.py`, `conftest.py`, `config.py`) disappear from dead-code filter view.
- Graph becomes incomplete during a key workflow (finding dead code).
- User may incorrectly conclude those files have no import edges.

## Recommendation
Change the zero-function case to not dim (let it show neutrally):
```javascript
if (f.dead) {
  const fns = node.functions || [];
  if (fns.length === 0) return false;  // zero-function files: neutral, show them
  const allDead = fns.every(fn => fn.is_dead_code);
  if (!allDead) return true;           // mixed live/dead: dim
}
```

## Test Cases
- Node with `functions: []` → not dimmed when dead filter active.
- Node with all functions `is_dead_code: true` → not dimmed (shown as dead).
- Node with mixed dead/live functions → dimmed.

## Regression Risk
Low. Frontend-only change; no backend impact.

## Related Code Path
`graps/frontend/graph.js:93-101` — `isDimmed` dead-code filter logic

---

# Finding 13

## Title
`read_cache` performs full JSON parse on every POST `/api/ai/summary` request — scales with cache file size

## Severity
Low

## Likelihood
High

## Confidence
High

## Category
Performance / Scalability

## Scenario
A large project with 500 functions is fully summarized. The cache file contains 500 entries (~500KB). Every subsequent "Generate AI Insight" click — even for cache hits — reads and parses the entire 500KB JSON file before returning the cached result.

## Description
`app.py:134`:
```python
cache = cache_module.read_cache(cache_path)
```
This is called on every `POST /api/ai/summary` request, including cache hits. `read_cache` calls `cache_path.read_text()` (full file read) + `json.loads()` (full parse). As the cache grows with more summarized functions, every request gets slower, even for returning cached results where the data is already on disk.

## Evidence
`cache.py:36-46` — `read_cache` always reads and parses the entire file. No partial read, no in-memory cache layer.

## Steps to Reproduce
1. Summarize 500+ functions (populate cache).
2. Click any already-cached function's "Generate AI Insight."
3. Measure response time — increases with cache file size.

## Expected Behavior
Cache hits should be O(1) — an in-memory dict lookup, not O(file_size) filesystem + parse.

## Actual Behavior
Cache read is O(file_size) on every request.

## Root Cause
Cache module is a pure file I/O abstraction with no in-memory layer. `create_app` does not initialize any in-memory state. Each request reads from disk independently.

## Blast Radius
Service — all AI summary requests. Degrades progressively as cache grows.

## Impact
- Latency increases proportionally with cache file size.
- On a project with 1000+ functions, cache reads could become a noticeable bottleneck.
- Amplified by concurrent requests (Finding 3) — each concurrent reader also parses the full file.

## Recommendation
Add an in-memory cache layer in `create_app`:
```python
_mem_cache: dict = {}  # initialized once per app lifetime

def post_summary(req):
    ...
    hit = _mem_cache.get(key)  # O(1) lookup
    if not hit:
        hit = cache_module.read_cache(cache_path)["entries"].get(key)
        if hit: _mem_cache[key] = hit
```
Or use `functools.lru_cache` on the read path with cache invalidation on write.

## Test Cases
- After 1000 entries in cache, cache-hit response time should not regress beyond a defined budget.

## Regression Risk
Low. Optimization only; behavior is identical for correct single-threaded usage.

## Related Code Path
`graps/server/app.py:134` — `cache_module.read_cache(cache_path)` on every request  
`graps/ai/cache.py:29-46` — `read_cache` always reads full file

---

# Finding 14

## Title
`basename()` defined identically in both `graph.js` and `panel.js` — code duplication

## Severity
Informational

## Likelihood
—

## Confidence
High

## Category
Maintainability / Code Duplication

## Scenario
A bug is found in `basename()` (e.g., Windows path separator `\` not handled). Developer fixes it in `graph.js`. The identical bug in `panel.js` is not noticed. Both files diverge silently.

## Description
`basename()` (same function, same 4 lines) appears in `graph.js:288-292` and `panel.js:26-30`. The codebase uses IIFE modules with `window.graps` as the shared namespace, but `basename` is not exported to `window.graps` — it is a private function in each IIFE.

## Evidence
`graph.js:288-292`:
```javascript
function basename(p) {
  if (!p) return "";
  const i = p.lastIndexOf("/");
  return i >= 0 ? p.slice(i + 1) : p;
}
```
Identical to `panel.js:26-30`.

## Recommendation
Export `basename` from one module (e.g., add to `window.graps` in `graph.js`) and reference it from `panel.js`. Or create a shared `utils.js` loaded before both.

## Related Code Path
`graps/frontend/graph.js:288-292`  
`graps/frontend/panel.js:26-30`

---

## Coverage Checklist

| Category | Status |
|----------|--------|
| Happy Path | Evaluated — generally correct |
| Unhappy Path | Evaluated — several findings (5, 4, 6) |
| Edge Cases | Evaluated — findings 9, 11, 12 |
| Corner Cases | Evaluated — findings 8, 5 |
| Use Cases | Evaluated |
| Misuse Cases | Evaluated — finding 2 (CSRF bypass), 7 (empty source abuse) |
| Boundary Conditions | Evaluated — finding 9 (regex boundary) |
| Failure Modes | Evaluated — findings 4, 5, 6 |
| Error Handling | Evaluated — findings 5, 6, 8 |
| Concurrency | Evaluated — findings 3 (write_cache), 10 (double resolve) |
| Security | Evaluated — findings 2, 9 |
| Performance | Evaluated — findings 10, 13 |
| Scalability | Evaluated — findings 10, 13 |
| Reliability | Evaluated — findings 3, 4, 5 |
| Maintainability | Evaluated — findings 1, 9, 14 |
| Architecture | Evaluated — finding 1 (silent wiring gap), finding 3 (SPOF: single JSON cache file) |
| Regression Risk | Evaluated — noted per finding |
| Breaking Change Risk | Evaluated — findings 1, 7 are breaking if left unaddressed into Phase 2/3 feature activation |
