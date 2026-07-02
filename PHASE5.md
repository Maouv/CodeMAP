# Phase 5 — Chat AI Refactor & Secret Handling Revisit

> Reference: BLUEPRINT.md §8 (UX Flow), §10 (AI Layer), §11 (Security), §15 (Phase Breakdown), §16 (Out of Scope), §18 (Decision Log)
> Pre-condition: Phase 3 AI layer (consent modal, scrub_secrets, cache) + Phase 4 BaseParser — VERIFIED ada di kode aktual (2026-07-02).
> Scope: Replace per-function AI insight button dengan chat interface. Implement Option C (kirim full file source + non-blocking warning). Hapus `scrub_secrets()`. Update BLUEPRINT C-02 + SECURITY.md supaya tidak kontradiksi internal.
> Post-MVP backlog: approval/consent toggle (ala Cline auto-approval vs manual) — di §16, BUKAN scope ini.

---

## 0. Keputusan yang Sudah Final (Jangan Re-discuss)

| Keputusan | Alasan |
|-----------|--------|
| Chat interface, bukan tombol insight per-fungsi | Vibe coder butuh debugging Q&A ("kenapa bug ini terjadi"), bukan 3-field summary terstruktur. Chat = use case paling high-value untuk target user |
| Option C — kirim full file source ke AI | Metadata saja tidak cukup answer debugging questions. Debugging = use case paling high-value untuk vibe coder. Justifikasi berdiri sendiri, bukan precedent Anthropic |
| Hapus `scrub_secrets()` | Option C kirim raw source. scrub otomatis konflik dengan "user responsibility + informed warning". Defense-in-depth manual regex/detect-secrets jadi dead code |
| Consent modal blocking → hapus, ganti non-blocking warning | Friksi di depan value bikin user enggan pakai AI — padahal nanya AI = persis yang vibe coder butuh. Gate di depan value = orang enggan pakai |
| Non-blocking warning di tag-time via `[REDACTED]` constants yang sudah ada di graph | Zero infra baru — reuse output `sanitize_constant_value()` (C-01) yang sudah ada di graph. Ceiling: cuma catch constants, bukan secret di function body |
| `.env` / dedicated credential files → hard exclude dari AI context | Secret yang user tidak intend share. Function guard di `build_ai_context`, BUKAN HTTP middleware |
| `cache.py` → deprecated, tidak dipakai untuk chat | Fresh session = stateless, no persistence. File dipertahankan (keep, mark legacy) untuk `/api/ai/summary` (disabled) + backward compat |
| `POST /api/ai/summary` → disable (keep route, return deprecation) | Backward compat untuk test lama + tidak break import. Logic provider/cache tidak jalan |
| `POST /api/ai/chat` → endpoint baru | Stateless, body `{message, tagged, history}`. Return `{reply, warnings}` atau error (200 + `error_type` pattern) |
| `scan_root: Path` absolut di-pass ke `create_app` | Server butuh baca source dari disk untuk Option C. Path absolut tidak masuk graph JSON (M-03 tetap aman — `meta.root` tetap relatif) |
| Approval/consent toggle → post-MVP backlog | Design toggle tanpa data usage = tebakan. Masuk setelah chat stabil + ada usage data. Catat §16 + Decision Log |
| Scope: feature-only + catat bug yang otomatis moot | Bug fix pass terpisah. Refactor ini otomatis moot-kan bug scrub_secrets + consent modal, sisanya dicatat |

---

## 1. Prinsip Wajib

Sama seperti PHASE3.md / PHASE4.md — berlaku semua task:

1. Simple tapi works.
2. Minimalisir bug — defensive terhadap input aneh/kosong/corrupt.
3. Gampang di-refactor — pertahankan separation of concern (`provider.py` tidak tahu FastAPI, `app.py` tidak tahu SDK internals).
4. Riset dulu sebelum tulis manual — kalau ada yang sudah solve, pakai.
5. Jangan build dari nol kalau ada yang sudah dibangun.

**Tambahan spesifik Phase 5:**
- Chat = stateless. Tidak ada persistence, tidak ada session store, tidak ada cache conversation.
- `provider.py` tidak boleh tahu tentang graph, tag, atau file path — cuma terima `messages` + `context` string.
- `build_ai_context()` adalah satu-satunya tempat yang tahu cara map graph + disk → context string. Frontend tidak assemble context.
- Scanner layer TIDAK disentuh — `sanitize_constant_value()` (C-01 untuk graph JSON) tetap jalan, terpisah dari C-02.
- Bug dari `report-ai-cases.md` / `report-bug-frontend.md` TIDAK di-fix di sini kecuali yang otomatis moot karena refactor.

---

## 2. Yang Dihapus vs Dipertahankan

### Dihapus (konflik dengan Option C)

```
✗ scrub_secrets() + _SENSITIVE_PATTERNS + _DETECTORS (detect-secrets import block)
✗ _build_prompt() — single-shot JSON 3-field prompt, ganti chat system message
✗ _parse_summary() — JSON parse 3-field, ganti raw text return
✗ Consent modal blocking di panel.js (showConsentModal, _aiConsentGiven, overlay DOM)
✗ aiResults Map + callAI() per-function di panel.js
✗ AIError error_type "parse_failed" (tidak ada JSON parse lagi)
```

### Dipertahankan (reuse, tidak rewrite)

```
✓ AIError class (auth_failed / rate_limited / timeout / sdk_not_installed / unknown)
✓ AnthropicProvider + OpenAIProvider class skeleton + error mapping logic
✓ get_provider() env dispatch (Anthropic dulu, OpenAI fallback, None kalau kosong)
✓ cache.py — file tetap, mark deprecated (keep untuk /api/ai/summary disabled)
✓ enforce_origin + validate_host middleware (chat = POST, CSRF guard tetap jalan)
✓ sanitize_constant_value() di graph_builder (C-01, terpisah dari C-02)
✓ BaseParser interface, scanner layer semua
✓ filter.js, search.js, toast.js — tidak disentuh
✓ graph.js core (cuma minimal Ask AI trigger, defer kalau tidak perlu)
```

### Status bug yang otomatis MOOT (dicatat, TIDAK di-fix sekarang)

| Report | Finding | Status |
|--------|---------|--------|
| report-ai-cases.md #1 | scrub_secrets leak multi-line assignment | MOOT — scrub_secrets dihapus |
| report-ai-cases.md #2 | scrub_secrets leak dict-literal (no detect-secrets) | MOOT — scrub_secrets dihapus |
| report-ai-cases.md #8 | scrub_secrets false-positive (auth=True) | MOOT — scrub_secrets dihapus |
| report-ai-cases.md #4 | _parse_summary reject fences/prose | MOOT — chat return raw text |
| report-ai-cases.md #9 | _parse_summary truthy non-string | MOOT — no _parse_summary |
| report-bug-frontend.md #2 | Escape-vs-consent modal conflict | MOOT — consent modal dihapus |
| report-ai-cases.md #3,5,6,7,10,11 | cache bugs | TETAP ADA, cache deprecated → low priority, pass terpisah |
| report-bug-frontend.md #1,3-13 | graph/panel bugs | TETAP ADA, pass terpisah |

---

## 3. Architecture Overview

```
Frontend (panel.js)
  └── chat input bar dengan @tag parsing (aider-style)
        ├── user ketik "@get_user kenapa return None?"
        ├── tag-time warning: cek node.constants [REDACTED] → non-blocking inline
        └── POST /api/ai/chat { message, tagged: ["a.py::get_user"], history: [...] }
              │
              ▼
Server (app.py)
  ├── build_ai_context(tagged, graph, scan_root, max_tokens=8000)
  │     ├── resolve tag → file node / function di graph
  │     ├── .env/credential exclusion → hard skip source, catat warning
  │     ├── baca source dari disk (scan_root + rel path)
  │     │     ├── tag fungsi → function body (line_start-line_end) + N baris sekitar
  │     │     └── tag file → file truncated ke token budget
  │     ├── token budget per item (distribute max_tokens, truncate `... [truncated]`)
  │     └── assemble: [Graph Context] metadata + [Source Context] source
  │           → return (context_str, warnings: [{file, reason}])
  ├── provider = get_provider()  → None? return {enabled: false, reason: "no_api_key"}
  └── provider.chat(messages=history+message, context=context_str) → raw text
        ├── AIError → 200 + {error_type, retry_after?}
        └── success → 200 + {reply: str, warnings: [...]}
              │
              ▼
Frontend (panel.js)
  └── render reply (assistant bubble) + tampilkan warnings non-blocking inline
```

**State:**
- Chat history disimpan di frontend (in-memory, fresh session per conversation — no persistence, no localStorage).
- Graph in-memory di server (load sekali saat startup — sudah ada dari phase sebelumnya).
- `scan_root` absolut di-close-over dari `create_app` (in-memory, tidak masuk graph JSON — M-03 aman).


---

## 4. File Perubahan — Detail Spec

### 4.1 `graps/ai/provider.py` — Refactor `generate_summary` → `chat`

**Hapus:** `scrub_secrets()`, `_SENSITIVE_PATTERNS`, `_DETECTORS` (detect-secrets import block), `_build_prompt()`, `_parse_summary()`.

**Refactor:** `generate_summary(file_content, function_context) -> dict` → `chat(messages, context) -> str`.

```python
# graps/ai/provider.py — signature baru

class AIProvider:
    model: str = ""
    name: str = ""

    def chat(self, messages: list[dict[str, str]], context: str) -> str:
        """
        Kirim conversation ke provider. Return raw text reply.

        messages: [{"role": "user"|"assistant", "content": "..."}]
        context:  string context system (graph metadata + source) —
                  dikirim sebagai system message, BUKAN scrub.
        """
        raise NotImplementedError
```

```python
class AnthropicProvider(AIProvider):
    model = "claude-haiku-4-5-20251001"
    name = "anthropic"

    def chat(self, messages, context):
        try:
            import anthropic
        except ImportError:
            raise AIError("sdk_not_installed")

        key = os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise AIError("auth_failed")

        try:
            client = anthropic.Anthropic(api_key=key, timeout=30.0)
            resp = client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=context,          # context sebagai system message
                messages=messages,       # conversation history + user message
            )
            text = resp.content[0].text
        except anthropic.AuthenticationError as e:
            logger.warning(type(e).__name__)
            raise AIError("auth_failed")
        except anthropic.RateLimitError as e:
            # ... retry-after extraction sama seperti generate_summary lama ...
            raise AIError("rate_limited", retry_after=retry_after)
        except anthropic.APITimeoutError as e:
            logger.warning(type(e).__name__)
            raise AIError("timeout")
        except Exception as e:
            logger.warning(type(e).__name__)
            raise AIError("unknown")

        return text  # raw string, BUKAN dict 3-field
```

`OpenAIProvider` mirror pattern — `client.chat.completions.create(model, messages=[{"role":"system","content":context}, *messages])`, return `resp.choices[0].message.content`. Error mapping identik (`openai.AuthenticationError` / `RateLimitError` / `APITimeoutError`).

**Yang berubah vs `generate_summary`:**
- Tidak ada `scrub_secrets(file_content)` call — context dikirim raw.
- Tidak ada `_build_prompt()` — context string sudah di-assemble server-side.
- Tidak ada `_parse_summary()` — return raw text, frontend render apa adanya.
- `max_tokens` 512 → 1024 (chat reply lebih panjang dari 3-field summary).
- `AIError("parse_failed")` dihapus dari enum (tidak mungkin ter-trigger lagi).


### 4.2 `graps/server/app.py` — `build_ai_context()` + `/api/ai/chat`

**Tambah param `scan_root`:**

```python
def create_app(
    graph_data: dict[str, Any],
    port: int,
    cache_path: Path | None = None,
    scan_root: Path | None = None,   # BARU — path absolut untuk baca source
) -> FastAPI:
```

`scan_root` di-close-over dari `create_app`, tidak masuk graph JSON (M-03 tetap aman — `meta.root` tetap relatif `.`). Default `None` untuk backward-compat test yang tidak butuh baca source disk.

**Tambah `build_ai_context()`:**

```python
# Credential file exclusion — hard block (user tidak intend share)
_CREDENTIAL_FILES = {
    ".env", ".env.local", ".env.production", ".env.development",
    "credentials.json", "secrets.json", "secret.json",
}
_CREDENTIAL_EXTS = {".pem", ".key", ".p12", ".pfx"}


def _is_credential_file(rel_path: str) -> bool:
    name = Path(rel_path).name.lower()
    if name in _CREDENTIAL_FILES:
        return True
    if Path(rel_path).suffix.lower() in _CREDENTIAL_EXTS:
        return True
    if name.startswith(".env."):
        return True
    return False


def build_ai_context(
    tagged: list[str],
    graph: dict[str, Any],
    scan_root: Path,
    max_tokens: int = 8000,
) -> tuple[str, list[dict[str, str]]]:
    """
    Assemble context dari tagged items untuk dikirim ke AI (Option C).

    Per tagged item (format "file.py" atau "file.py::function"):
    1. Graph metadata (callers, callees, risk flags, params, returns, line range)
    2. Source dari disk — function body kalau tag fungsi, file truncated kalau tag file
    3. .env/credential exclusion → skip source, catat warning
    4. Token budget per item, truncate dengan `... [truncated]`

    Return (context_str, warnings) di mana warnings = [{file, reason}, ...].
    """
    if scan_root is None:
        return "", []
    # resolve tags ke graph nodes, baca disk, assemble structured context ...
```

Structured assembly format per item:

```
[Graph Context]
Function: get_user (services/user_service.py:12-28)
Called by: user_controller.py:34, admin_controller.py:89
Calls: get_session, User.query.filter
Risk flags: none_return_unchecked (2 callers tidak handle None)

[Source Context]
def get_user(user_id: int) -> User | None:
    session = get_session()
    return session.query(User).filter(User.id == user_id).first()
```

**Tambah `POST /api/ai/chat`:**

```python
class ChatRequest(BaseModel):
    message: str
    tagged: list[str] = []
    history: list[dict[str, str]] = []


@app.post("/api/ai/chat")
def post_chat(req: ChatRequest) -> dict[str, Any]:
    if not req.message.strip():
        return {"enabled": False, "reason": "empty_message"}

    context, warnings = build_ai_context(req.tagged, graph_data, scan_root)

    provider = provider_module.get_provider()
    if provider is None:
        return {"enabled": False, "reason": "no_api_key", "warnings": warnings}

    messages = req.history + [{"role": "user", "content": req.message}]
    try:
        reply = provider.chat(messages, context)
    except AIError as e:
        if e.error_type == "sdk_not_installed":
            return {"enabled": False, "reason": "sdk_not_installed", "warnings": warnings}
        payload: dict[str, Any] = {"enabled": True, "error_type": e.error_type, "warnings": warnings}
        if e.error_type == "rate_limited" and e.retry_after is not None:
            payload["retry_after"] = e.retry_after
        return payload

    return {"enabled": True, "reply": reply, "warnings": warnings}
```

**Disable `POST /api/ai/summary`:**

```python
@app.post("/api/ai/summary")
def post_summary(req: SummaryRequest) -> dict[str, object]:
    """DEPRECATED — Phase 5. Gunakan /api/ai/chat."""
    return {"deprecated": True, "reason": "use /api/ai/chat"}
```

Route + `SummaryRequest` + cache import tetap (handoff: keep tapi disable). Logic provider/cache tidak jalan.

### 4.3 `graps/cli.py` — Pass `scan_root`

Satu baris perubahan di `main()`:

```python
fastapi_app = create_app(graph, port=port, cache_path=cache_path, scan_root=path)
#                                                            ^^^^^^^^^^^^^^^^ BARU
```

`path` adalah argumen typer (absolute path dari user). Tidak ada perubahan lain di cli.py.


### 4.4 Frontend — `panel.js` (changes terbesar)

**Hapus:**
- `callAI()`, `showConsentModal()`, `aiResults` Map, `_aiConsentGiven`, consent overlay DOM build, inline AI insight render per function (`fnDetail` AI section).

**Tambah chat UI (state in-memory, fresh session):**

```javascript
// panel.js — chat state (reset tiap app load, no localStorage)
const chatHistory = [];   // [{role, content}]
const chatWarnings = [];  // non-blocking warnings current message

function renderChat() {
  // message list (user bubble right, assistant bubble left)
  // input bar dengan @tag parsing
  // send button → handleSend()
  // warnings inline (amber, non-blocking, dismissible)
}

function parseTags(text) {
  // extract @file::function / @file / @function dari input
  // return { tags: [...], cleanText: "..." }
}

function checkTagWarnings(tags) {
  // tag-time: cek node.constants.some(c => c.value === "[REDACTED]")
  // → non-blocking warning "File ini mungkin contain sensitive values
  //   yang akan di-share ke AI provider."
  // reuse data graph yang sudah di-load — zero fetch tambahan
  // ponytail: ceiling = cuma catch constants, bukan secret di function body.
  //   Upgrade path: server-side preview endpoint kalau perlu akurasi lebih.
}

async function handleSend() {
  const { tags, cleanText } = parseTags(input.value);
  if (!cleanText.trim()) return;
  checkTagWarnings(tags);   // non-blocking, tidak halt send
  chatHistory.push({ role: "user", content: input.value });
  renderChat();

  const body = { message: cleanText, tagged: tags, history: chatHistory.slice(0, -1) };
  try {
    const r = await fetch("/api/ai/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await r.json();
    if (data.enabled === false) {
      // no_api_key / sdk_not_installed → tampil disabled state
    } else if (data.error_type) {
      // reuse errorMsg() mapping (auth_failed / rate_limited / timeout)
    } else {
      chatHistory.push({ role: "assistant", content: data.reply });
      if (data.warnings?.length) chatWarnings.push(...data.warnings);
    }
    renderChat();
  } catch (err) {
    // network error → bubble error
  }
}
```

**"Ask AI" per fungsi** — function row di panel dapat affordance (button/chevron click) → insert `@file::function` ke chat input + focus input. Tidak generate langsung — user ketik pertanyaan mereka sendiri.

```javascript
function askAI(fnName) {
  const node = currentNode();
  if (!node) return;
  const tag = "@" + node.path + "::" + fnName;
  chatInput.value = chatInput.value ? chatInput.value + " " + tag : tag;
  chatInput.focus();
}
```


### 4.5 Frontend — `index.html` + `style.css`

**index.html** — tambah chat section di side-panel (di bawah file detail). Aku propose: chat section di bawah function list di side panel, collapsible.

```html
<aside id="side-panel" ...>
  <!-- existing: file detail, function list -->
  <!-- BARU: chat section -->
  <section id="chat-section" class="chat-section">
    <div id="chat-messages" class="chat-messages"></div>
    <div id="chat-warnings" class="chat-warnings"></div>
    <div class="chat-input-bar">
      <input id="chat-input" type="text" placeholder="Ask AI…  @file @function" />
      <button id="chat-send">↑</button>
    </div>
  </section>
</aside>
```

Script urutan tetap: `toast.js` → `filter.js` → `graph.js` → `panel.js` → `search.js`.

**style.css** — tambah:
- `.chat-messages` (scrollable, flex column)
- `.chat-bubble--user` / `.chat-bubble--assistant`
- `.chat-input-bar` (sticky bottom)
- `.chat-warning` (amber inline, non-blocking, dismissible)
- `[✦ Ask AI]` affordance di function row
- Disabled state no-API-key (input bar greyed, hint tooltip)

**`graph.js`** — minimal. "Ask AI" primer hidup di panel.js (function rows). graph.js tidak diubah kecuali kalau UX butuh trigger dari canvas (defer — mulai di panel.js, tambah ke graph.js hanya kalau perlu).

### 4.6 Dokumen Update — `BLUEPRINT.md` + `SECURITY.md`

**BLUEPRINT.md:**
- §11 risk matrix **C-02**: `CRITICAL: Source ke AI tanpa scrubbing → scrub_secrets() + consent` → revise jadi `revised: user responsibility + non-blocking informed warning (Option C)`. Status C-02 → "revised: user-responsibility model".
- §7 data contract: field `ai_summary: null` per function → mark deprecated (chat tidak pakai field ini).
- §8 UX **Level 3 (AI Insight)** → rewrite ke chat architecture (chat interface, Ask AI, `@tag`, non-blocking warning).
- §10 AI layer → update ke chat (`provider.chat`, `build_ai_context`, `POST /api/ai/chat`).
- §15 Phase 3 Task 1 (scrub_secrets upgrade) + Task 2 (consent) → mark **superseded** oleh Phase 5.
- §16 Out of Scope → tambah "Approval/consent mode toggle (ala Cline auto-approval vs manual) — post-MVP, setelah chat stabil + ada usage data".
- §18 Decision Log → tambah baris: `Option C — send full source, remove scrub_secrets, user responsibility + non-blocking warning | vibe coder debugging use case | 2026-07-02`.

**SECURITY.md:**
- Section "Secret Scrubbing" → rewrite: graps tidak scrub otomatis lagi; user responsibility + non-blocking warning saat tag file dengan potential secret (detected via `[REDACTED]` constants dari C-01). `.env` / credential files di-exclude dari AI context (hard block). Tetap best-effort bukan jaminan — review kode sendiri sebelum tag file berisi secret.


---

## 5. Secret Handling Model (Option C Final)

```
┌──────────────────────────────────────────────────────────────────┐
│  Kategori file                 │ AI context treatment             │
├────────────────────────────────┼──────────────────────────────────┤
│ .env / *.pem / *.key /         │ HARD EXCLUDE — source tidak      │
│ credentials.json / secrets.json│ dikirim. Warning di chat.        │
│ .env.* variants                │                                  │
├────────────────────────────────┼──────────────────────────────────┤
│ Source file dengan constant    │ KIRIM RAW + non-blocking warning │
│ yang ter-redact (C-01 detect)  │ saat tag (cek [REDACTED] di graph)│
│ → "API_KEY", "DB_PASSWORD"     │ User proceed atau remove tag.    │
├────────────────────────────────┼──────────────────────────────────┤
│ Source file bersih             │ KIRIM RAW, no warning            │
└────────────────────────────────┴──────────────────────────────────┘
```

**Why no scrub:** scrub otomatis memberi false sense of security — vibe coder assume "graps handle secret", padahal scrub leak di multi-line / dict-literal (`report-ai-cases.md` #1, #2). Informed warning + user responsibility = model yang jujur dan align dengan target user (developer yang sadar risk, sama seperti stance Claude Code).

**Why non-blocking, not consent gate:** friksi di depan value bikin user enggan pakai AI — padahal nanya AI = persis yang vibe coder butuh. Warning kasih info tanpa halt flow. Approval toggle post-MVP kalau user yang takut break things mau opt-in gate (ala Cline auto-approval vs manual).

---

## 6. Token Budget & Context Assembly

`build_ai_context()` constraint: total context ≤ `max_tokens` (default 8000). Distribusi per tagged item.

```python
# Pseudocode distribution
per_item_budget = max_tokens // max(len(tagged), 1)
for tag in tagged:
    metadata = extract_graph_metadata(tag, graph)   # always included, kecil
    source_budget = per_item_budget - approx_tokens(metadata)
    if _is_credential_file(rel_path):
        source = None  # hard exclude
        warnings.append({file, reason: "credential_file_excluded"})
    else:
        raw = read_source(scan_root / rel_path)
        if "::" in tag:
            source = extract_function_body(raw, line_start, line_end, source_budget)
        else:
            source = truncate_file(raw, source_budget)  # marker `... [truncated]`
    context_parts.append(format_block(metadata, source))
```

**Truncation marker:** `... [truncated, N lines omitted]` — supaya AI tahu context tidak lengkap dan user tahu budget habis.

**Token estimate:** ponytail — `len(text) // 4` (approx 4 chars/token untuk English + code). Tidak pakai tiktoken — dependency baru untuk estimate kasar tidak worth it. Ceiling: estimate kasar, kadang under/over budget. Upgrade path: tiktoken kalau provider OpenAI + akurasi critical.


---

## 7. Tests

### `tests/test_provider.py` — rewrite

**Hapus** 4 test `scrub_secrets` (`test_scrub_secrets__*`). **Ganti** dengan test `chat()`:

| Test | Assertion |
|------|-----------|
| `test_chat__returns_raw_text` | Mock SDK, `chat()` return string apa adanya (bukan dict) |
| `test_chat__auth_failed` | Mock raise `AuthenticationError` → `AIError("auth_failed")` |
| `test_chat__rate_limited_with_retry_after` | Mock raise `RateLimitError` + header → `AIError("rate_limited", retry_after=N)` |
| `test_chat__timeout` | Mock raise `APITimeoutError` → `AIError("timeout")` |
| `test_chat__sdk_not_installed` | Monkeypatch import raise `ImportError` → `AIError("sdk_not_installed")` |
| `test_get_provider__dispatch` | env dispatch tetap (Anthropic dulu, OpenAI fallback, None kalau kosong) |

### `tests/test_api.py` — tambah + adjust

**Tambah** `/api/ai/chat` tests:

| Test | Assertion |
|------|-----------|
| `test_chat__no_api_key_returns_disabled` | no env → `{enabled: false, reason: "no_api_key"}` |
| `test_chat__empty_message_rejected` | message `""` → `{enabled: false, reason: "empty_message"}` |
| `test_chat__mocked_provider_returns_reply` | Mock `provider.chat` return "debug answer" → `{reply: "debug answer"}` |
| `test_chat__mocked_auth_failed` | Mock raise `AIError("auth_failed")` → `{error_type: "auth_failed"}` |
| `test_chat__credential_file_excluded` | tag `.env` → warning `credential_file_excluded`, source tidak dikirim |
| `test_chat__build_context_with_scan_root` | tag fungsi + `scan_root` tmpdir → context mengandung function body |
| `test_chat__no_scan_root_empty_context` | `scan_root=None` → `context=""`, `warnings=[]` (backward-compat test) |

**Adjust** `/api/ai/summary` tests yang lama → expect deprecation response `{"deprecated": true, "reason": "use /api/ai/chat"}`. Test cache roundtrip yang lama → mark skip atau hapus (cache deprecated).

### `tests/test_cache.py` — tidak berubah

`cache.py` preserved (deprecated tapi file tetap). Test tetap jalan validasi legacy I/O.

### Self-check `__main__`

- `provider.py` `__main__`: update ke `chat()` flow (hapus scrub self-check, tambah chat mock).
- `app.py` `__main__`: update self-check ke `/api/ai/chat` (hapus summary success path, tambah chat mocked).


---

## 8. Checklist Ringkas

```
[ ] graps/ai/provider.py — refactor generate_summary → chat
    [ ] hapus scrub_secrets, _SENSITIVE_PATTERNS, _DETECTORS, _build_prompt, _parse_summary
    [ ] chat(messages, context) -> str di AnthropicProvider + OpenAIProvider
    [ ] AIError enum: hapus "parse_failed"
    [ ] self-check __main__ update
[ ] graps/server/app.py
    [ ] create_app(scan_root=...) param baru
    [ ] build_ai_context(tagged, graph, scan_root, max_tokens) -> (str, warnings)
    [ ] _is_credential_file() hard exclusion
    [ ] POST /api/ai/chat endpoint
    [ ] POST /api/ai/summary → disable (deprecation response)
    [ ] self-check __main__ update
[ ] graps/cli.py — pass scan_root ke create_app
[ ] tests/test_provider.py — rewrite (chat tests, hapus scrub tests)
[ ] tests/test_api.py — tambah /api/ai/chat, adjust summary deprecation
[ ] BLUEPRINT.md — C-02 revise, §7 ai_summary, §8 Level 3, §10, §15 Phase 3 mark, §16 backlog, §18 Decision Log
[ ] SECURITY.md — rewrite Secret Scrubbing section
[ ] frontend/index.html — chat section markup
[ ] frontend/style.css — chat UI styling
[ ] frontend/panel.js — chat UI + Ask AI + tag-time warning, hapus callAI/consent
[ ] frontend/graph.js — minimal (Ask AI trigger, defer kalau tidak perlu)
[ ] Full test suite pass, zero regresi (kecuali yang sengaja di-adjust)
```

---

## 9. Urutan Implementasi (Dependency Order)

```
1. provider.py          ← foundation, no deps on server/frontend
2. server/app.py        ← build_ai_context + /api/ai/chat + scan_root
3. cli.py               ← pass scan_root (satu baris)
4. tests backend        ← test_provider.py, test_api.py
5. BLUEPRINT.md + SECURITY.md  ← doc updates
6. frontend/index.html + style.css  ← chat panel markup + styling
7. frontend/panel.js    ← chat UI + Ask AI + tag-time warning
8. frontend/graph.js    ← Ask AI trigger (minimal)
9. Run full test suite, zero regresi
```

---

## 10. Yang TIDAK Termasuk Phase 5

```
✗ Approval/consent mode toggle (ala Cline auto-approval vs manual) — post-MVP backlog
✗ Chat persistence / session store — fresh session by design
✗ Conversation cache — stateless by design
✗ Bug fix dari report-ai-cases.md (kecuali yang otomatis moot) — pass terpisah
✗ Bug fix dari report-bug-frontend.md (kecuali #2 moot) — pass terpisah
✗ scanner/ perubahan — sanitize_constant_value (C-01) tetap jalan, terpisah dari C-02
✗ BaseParser interface — tidak disentuh
✗ filter.js / search.js / toast.js — tidak disentuh
✗ Lazy loading — MVP full scan di startup (BLUEPRINT keputusan)
✗ Frontend build step — tetap vanilla JS
✗ Tree-sitter / multi-language — Phase 4 selesai
```

---

## 11. Verifikasi Pre-Implementasi (kode aktual, 2026-07-02)

| Item | Status |
|------|--------|
| `provider.py` punya `scrub_secrets` + `_build_prompt` + `_parse_summary` | ✅ ada — akan dihapus |
| `provider.py` punya `AnthropicProvider` / `OpenAIProvider` / `AIError` / `get_provider` | ✅ ada — dipertahankan |
| `cache.py` punya read/write/is_valid + lock | ✅ ada — mark deprecated |
| `app.py` `create_app(graph_data, port, cache_path)` | ✅ ada — tambah `scan_root` |
| `app.py` `POST /api/ai/summary` + `SummaryRequest` | ✅ ada — disable |
| `cli.py` `create_app(graph, port, cache_path)` line 237 | ✅ ada — tambah `scan_root=path` |
| `panel.js` `callAI` + `showConsentModal` + `aiResults` | ✅ ada — dihapus |
| `panel.js` kirim `source: ""` (AI insight mati sekarang) | ✅ verified line 334-336 — akan hidup via chat |
| `graph_builder.py` `meta.root = _rel(root, root)` = `.` | ✅ verified — scan_root absolut tidak masuk graph JSON (M-03 aman) |
| `sanitize_constant_value()` (C-01) di graph_builder | ✅ ada — tetap jalan, terpisah dari C-02 |
| `enforce_origin` + `validate_host` middleware | ✅ ada — chat POST tetap CSRF-guarded |
| Consent modal blocking (PHASE3 Task 2) | ✅ ada — dihapus, ganti non-blocking warning |
| detect-secrets import (PHASE3 Task 1) | ✅ ada — dihapus bareng scrub_secrets |

---

*PHASE5.md — reference BLUEPRINT.md §8, §10, §11, §15, §16, §18.*
*Dibuat: 2026-07-02.*

