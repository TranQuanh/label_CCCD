# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## What this is

Vietnamese national ID card (CCCD) information extraction using a vision-language
model fine-tuned with QLoRA (4-bit). A 4-stage human-in-the-loop ML lifecycle:
auto-label → human review → fine-tune → evaluate → serve. Designed to run on a
single small GPU (Colab T4 15GB / L4 24GB); `bitsandbytes` 4-bit requires
Linux/Colab/WSL (no Windows-native support).

Comments, docstrings, and log messages are written in **Vietnamese** — match this
when editing.

## Repo layout — three parts plus shims

```
frontend/  Flutter e-KYC app.  lib/{core,data,features}/ — see frontend/README.md
backend/   FastAPI: API /api/v1 (auth+RBAC+audit) + serving /extract-cccd.  main.py + modules
model/     ML pipeline.        src/  scripts/  notebooks/
docs/      ARCHITECTURE · CHANGELOG · VLM_COMPARISON_PLAN · Discussion
data/ checkpoints/ result_front/ result_back/   artifacts (gitignored)

src/  app/  scripts/   ← SHIMS at the repo root. No source code lives here.
```

The three root shims exist so every previously documented command and every Colab
notebook keeps working unchanged after the split:

- `src/__init__.py` and `app/__init__.py` repoint `__path__` to `model/src` and
  `backend/` respectively, so `python -m src.<...>`, `from src.utils...` and
  `uvicorn app.main:app` all still resolve.
- `scripts/{train,evaluate,compare_models,benchmark}.py` forward to
  `model/scripts/<same name>` via `runpy`.

**Edit the real files under `model/` and `backend/`, never the shims.** Do not
import both `app.main` and `backend.main` in one process — that loads the 4-bit
base twice and doubles VRAM.

## Commands

Run modules from the repo root. `src/` modules run via `python -m src.<...>`;
`scripts/*.py` patch `sys.path` so both `python scripts/x.py` and `-m` work.
Both paths go through the shims above.

```bash
# Stage 1 — auto-label drafts (Qwen2.5-VL), then human-review in Gradio
python -m src.data_pipeline.auto_label  --input_dir data/raw --result_dir data/draft
python -m src.data_pipeline.label_tool  --jsonl data/draft/raw_draft.jsonl --front_dir data/Front --back_dir data/Back --share

# Stage 2 — split 80/10/10 + augment train-only, then QLoRA fine-tune
python -m src.data_pipeline.prepare_dataset --input data/draft/raw_draft.jsonl --out_dir data/dataset
python scripts/train.py --train_jsonl data/dataset/train.jsonl --val_jsonl data/dataset/val.jsonl --output_dir checkpoints/qwen-cccd-lora

# Stage 3 — evaluate on test set (writes result/eval_report.json)
python scripts/evaluate.py --test_jsonl data/dataset/test.jsonl --adapter_dir checkpoints/qwen-cccd-lora

# Stage 3b — fine-tune vs fine-tune across VLM architectures (VLM_COMPARISON_PLAN.md)
# Probe image-token budget first — processor only, no weights, runs on CPU:
python -m src.models.vlm_registry --model internvl --image data/Front/cccd_front_1.jpg
# Same hyperparameters for every model; --max_length and LoRA params come from the registry:
python scripts/train.py --train_jsonl data/dataset/train.jsonl --val_jsonl data/dataset/val.jsonl \
    --model_name OpenGVLab/InternVL3_5-2B-HF --output_dir checkpoints/internvl3_5-2b-cccd-lora
python scripts/evaluate.py --test_jsonl data/dataset/test.jsonl --zero_shot \
    --base_model OpenGVLab/InternVL3_5-2B-HF --report_path result/eval_internvl_zs.json
python scripts/compare_models.py --report_dir result   # → result/model_comparison.{json,md}
# evaluate.py also writes <report>_preds.jsonl by default
# ({image, pred, gold, raw} per line); notebook 05 needs it for bootstrap CI + McNemar.
# Disable with --no_save_predictions.

# Stage 3c — re-score WITHOUT a GPU after a parser change (scripts/rescore.py)
python scripts/rescore.py rescore --preds result/front/eval_qwen_zeroshot_front_preds.jsonl \
    --report result/front/eval_qwen_zeroshot_front.json      # re-parses `raw`, rewrites report
# For preds files written before `raw` existed, regenerate only the broken images:
python scripts/rescore.py missing --preds <old_preds> --test_jsonl <test.jsonl> --out mini.jsonl
python scripts/evaluate.py --test_jsonl mini.jsonl ... --report_path /tmp/mini.json
python scripts/rescore.py merge --base <old_preds> --patch /tmp/mini_preds.jsonl --out <old_preds>
python scripts/rescore.py rescore --preds <old_preds> --report <old_report>

# Stage 4 — serve API (one model per process; both side adapters on one base)
MODEL_KEY=qwen CHECKPOINT_DIR=checkpoints MAX_BATCH_SIZE=4 uvicorn app.main:app --port 8000
# discovers checkpoints/qwen-cccd-lora-{front,back}; GET /health lists which sides loaded
# POST one image to http://localhost:8000/extract-cccd/       (optional ?side=truoc|sau|auto)
# POST N images  to http://localhost:8000/extract-cccd/batch  (repeated `files` field)

# Stage 4b — serving throughput/latency (speed only; accuracy still comes from evaluate.py)
python scripts/benchmark.py --mode local --models qwen,internvl,llama_vision \
    --images data/Front data/Back --models_dir models --checkpoint_dir checkpoints
python scripts/benchmark.py --mode http --url http://localhost:8000 \
    --concurrency 1,2,4 --batch_sizes 1,4      # API must already be running
python scripts/benchmark.py --mode merge --report_dir result  # → benchmark_comparison.{json,md}

# Stage 4c — user API (/api/v1) needs PostgreSQL + Redis; run WITHOUT a GPU:
$env:SKIP_MODEL_LOAD=1; $env:DATABASE_URL="postgresql://postgres:postgres@localhost:5432/cccd"
$env:REDIS_URL="redis://localhost:6379/0"; $env:JWT_SECRET="dev-secret"; $env:PYTHONIOENCODING="utf-8"
uvicorn backend.main:app --port 8000     # /health reports db, redis, lite_mode
# Auth flow: POST /api/v1/auth/register|login|refresh|logout|me; GET /api/v1/users|audit-logs|forms
# Repo-local convenience script: powershell -File C:\Users\ADMIN\AppData\Local\Temp\opencode\start_backend_lite.ps1

# Stage 5 — Flutter client (frontend/). Scaffold is NOT committed; generate once:
cd frontend && flutter create . && flutter pub get
flutter run                                        # mock mode, no network
flutter run --dart-define=USE_MOCK=false --dart-define=API_BASE_URL=http://<ip>:8000
```

There is no Python test suite, linter, or build step. `metrics.py`,
`cccd_schema.py`, and `lora_setup.py` have `__main__` smoke tests runnable
directly. The Flutter side has lints enabled (`frontend/analysis_options.yaml`);
`flutter analyze` is the check there.

## Architecture

The whole pipeline is glued together by one rule: **prompt and field schema must be
identical at label time, train time, eval time, and serve time.** That contract
lives in [model/src/utils/cccd_schema.py](model/src/utils/cccd_schema.py) — the single source
of truth. Every other module imports `SYSTEM_PROMPT`, `build_user_prompt`,
`infer_side_from_filename`, and the `FRONT_FIELDS`/`BACK_FIELDS` lists from it. Do
not hardcode prompts or field names anywhere else.

**Dynamic per-side prompting.** `infer_side_from_filename` derives front/back from
the image filename (tokens `front`/`truoc`/`_mt` → front; `back`/`sau`/`_ms` →
back). `build_user_prompt(side)` then asks for *only* that side's fields, which
prevents the model from hallucinating fields that only exist on the other side.
Filenames therefore carry semantic meaning — keep `front`/`back` tokens in them.

**Data format (JSONL).** Each record is `{"image": ..., "conversations": [{"from":
"human", "value": "<image>\n<prompt>"}, {"from": "gpt", "value": "<json answer>"}]}`.
Draft records (from `auto_label`) additionally carry a `_meta` block with
`reviewed`, `parse_ok`, `raw_output`. `prepare_dataset` strips `_meta` and **drops
any record with `reviewed != true`** unless `--allow_unreviewed` is passed;
`label_tool` sets `reviewed=true` on Save.

**Two loss-correctness invariants in [model/scripts/train.py](model/scripts/train.py)** (both
were hard-won bug fixes — preserve them):
1. Images are `thumbnail((1024,1024))`'d before tokenization so image tokens don't
   overflow `max_length` and swallow the JSON answer (was causing loss 0.0).
2. The collator masks the entire prompt + image/pad tokens to `-100`, computing
   loss only on the assistant's JSON answer (was causing stuck loss ~6.38). The
   1024px thumbnail at train time **must match** the same resize at eval/serve time,
   or image-token counts diverge.

**4-bit loading is centralized** in [model/src/models/lora_setup.py](model/src/models/lora_setup.py):
NF4 + double-quant, `prepare_model_for_kbit_training` with `use_reentrant=False`
(and gradient checkpointing is *not* re-enabled separately — double-enabling broke
gradient flow), vision tower frozen, LoRA on language-model attn+MLP projections
only. Inference paths (`evaluate.py`, `app/main.py`) re-create the same 4-bit
`BitsAndBytesConfig` and attach the adapter via `PeftModel.from_pretrained` — the
adapter dir also holds the saved processor.

**Models are loaded via `AutoModelForImageTextToText`** in the train/eval/serve
paths so they run on stable PyPI `transformers`. Only `auto_label.py` branches on
model name to pick a concrete class (`Qwen2_5_VLForConditionalGeneration` vs
`Qwen3VLForConditionalGeneration`); Qwen3-VL there needs `transformers` from source.

**Serving is multi-model and multi-adapter** ([backend/main.py](backend/main.py)). One process
serves one model (`MODEL_KEY`), but **both side adapters on one base**:
`discover_adapters()` finds `{model_key}-cccd-lora-{front,back}` under `CHECKPOINT_DIR`,
the first becomes a `PeftModel` and the rest attach via `load_adapter(adapter_name=...)`
— the 4-bit base exists once in VRAM. `run_inference_batch` groups a request's images by
side and calls `select_adapter()` per group, so a mixed-side batch costs ≥2 `generate`
calls. A side with no adapter is **rejected with a message**, never silently run on the
other side's adapter (InternVL currently has only a front adapter). `unload_model()` frees
VRAM so `benchmark.py` can sweep all three models in one process. `ADAPTER_DIR` (single
adapter) still works and infers its side from the dir name.

**Three serving-path invariants in [backend/main.py](backend/main.py)** (batch inference
depends on all three):
1. `set_left_padding()` forces `padding_side='left'` on the *inference* tokenizer;
   train stays `'right'` (`lora_setup._check_padding_side` enforces that). With
   right padding and batch > 1, pads sit between the prompt and the generation
   point, so shorter sequences continue after a pad token — garbage output — and
   the `output_ids[:, input_ids.shape[1]:]` slice cuts at the wrong offset.
2. Endpoints are `def`, **not** `async def`. `generate` blocks with no `await`
   inside, so on the event loop it would stall the whole server (including
   `/health`) and make concurrent requests queue invisibly. As `def`, FastAPI runs
   them in its threadpool; `GPU_LOCK` then serializes the critical section. That
   section must cover `select_adapter` **and** `generate` together — `set_adapter`
   mutates shared model state, so locking only `generate` lets one thread flip the
   adapter mid-generation of another.
3. `run_inference_batch` is the one inference path — `run_inference` is a 1-element
   wrapper over it, and `benchmark.py --mode local` imports it rather than
   rebuilding its own loop, so what gets measured is what gets served.

`MAX_BATCH_SIZE` (env, default 4) caps images per `generate`; larger uploads are
chunked. Batch/padding can shift outputs slightly vs batch=1, so accuracy numbers
for the report must still come from `evaluate.py` (sequential, batch=1) —
`benchmark.py` reports speed and tracks `parse_ok_rate` only as a padding-sanity
check.

**Multi-model support is centralized in [model/src/models/vlm_registry.py](model/src/models/vlm_registry.py)**
— the second source of truth after `cccd_schema.py`, and the same rule applies: don't
hardcode anything model-specific outside it. It splits config into what must stay
**identical** across models (`SHARED_LORA_TARGETS`, `SHARED_IMAGE_MAX_SIDE=1024`,
`SHARED_LORA_R/ALPHA/DROPOUT`) and what is **architecture-forced** (per-`VLMSpec`:
`processor_kwargs`, `vision_prefixes`, `max_length`, `nested_images`, `gated`). Three
non-obvious things it exists to prevent:

- `target_modules` as bare names attaches LoRA to the **vision tower** on all three
  models — InternViT and Llama's ViT name their linears `q_proj/k_proj/v_proj`, and
  Qwen2.5-VL's ViT uses a SwiGLU MLP named `gate_proj/up_proj/down_proj` (96 modules at
  ViT depth 32). Freezing the vision tower before `get_peft_model` does **not** help:
  the freshly injected `lora_A`/`lora_B` layers are trainable regardless. Any Qwen
  adapter trained before the registry refactor therefore has vision-MLP LoRA in it and
  must be retrained to be comparable. `build_lora_target_regex()` emits a
  negative-lookahead regex; `assert_no_vision_lora()` raises if anything leaks through.
- `preprocess_image()` is the **single** resize used by train/eval/serve. The 1024px
  thumbnail is a shared control variable, not a Qwen quirk — every model sees the same
  pixels, and its own tiling/resize is the thing being measured.
- `generation_config.json` differs per model (some default to sampling), so
  `evaluate.build_gen_kwargs()` forces greedy explicitly; `app/main.py` mirrors it.
- Never guard a local snapshot with `config.json.exists()`. `snapshot_download` writes
  config/index/tokenizer *before* the heavy shards, so an interrupted download (out of
  Drive space, Colab disconnect) leaves a dir that passes that guard and then dies at
  `from_pretrained` with `FileNotFoundError: model-00001-of-0000N.safetensors`. Use
  `snapshot_complete()` (checks `model.safetensors.index.json` + total byte size) and
  `ensure_snapshot()`; `resolve_model_dir()` picks Drive vs Colab SSD from
  `VLMSpec.weights_gb` vs free space — Llama-11B (~21GB) does not fit Drive free (15GB).
  Notebooks 01–04 all go through these; `--check_dir` on the registry CLI inspects a dir.

`resolve()` maps a key / HF id / checkpoint path to a spec. Probe the image-token budget
without downloading weights: `python -m src.models.vlm_registry --model <key> --image <img>`.
`train.py` writes `vlm_meta.json` next to the adapter; `evaluate.py` and `app/main.py`
read it to pick the right base model and warn on mismatch.

**Model comparison** ([docs/VLM_COMPARISON_PLAN.md](docs/VLM_COMPARISON_PLAN.md)): the OCR
baselines (Tesseract / PaddleOCR / VietOCR) and the zero-shot Qwen-VL baseline were
removed — that comparison axis is dropped. The comparison is fine-tune vs fine-tune
across VLM architectures (Qwen2.5-VL-3B anchor vs InternVL3.5-2B vs Llama-3.2-11B-Vision),
6 runs = 3 models × {zero-shot, fine-tuned}, all scored with the **same**
`metrics.evaluate` and merged by [model/scripts/compare_models.py](model/scripts/compare_models.py).

**Metrics** ([model/src/utils/metrics.py](model/src/utils/metrics.py)): Field Accuracy (exact
match after normalization — the headline metric), CER (Levenshtein), and micro-F1
on tokens. Normalization = NFC Unicode, whitespace collapse, lowercase,
`null`/`none`/`None` → `""`.

`metrics.safe_parse` is the scoring-side JSON parser and must stay behaviourally
equal to the *parse* half of `auto_label.parse_json_safe` (bare `json.loads` →
strip ```` ```json ```` fence → regex the first `{...}`), because that is what the
serving path in `backend/main.py` uses. It previously did bare `json.loads` only,
so any model that wrapped its answer in a markdown fence or added a lead-in
sentence scored `{}` — every field wrong. That is what produced
`json_parse_rate = 0/144` and `f1 = 0.0` for InternVL zero-shot while its raw
output may well have been readable. **Never** port `parse_json_safe`'s content
post-processing (forcing `dac_diem_nhan_dang` containing `/` to null, canonicalising
`noi_cap`) into `safe_parse`: `evaluate.py` runs gold through the same function, so
those rules would rewrite the ground truth before comparison.

## Backend (`backend/`) — API `/api/v1` + serving `/extract-cccd/*`

One FastAPI app, two layers in `backend/main.py`:

- **User API `/api/v1/*`** — `auth.py` (`/auth/register|login|refresh|logout|me`,
  `/auth/change-password` P2), `users.py` (`/users`, admin-only RBAC),
  `audit.py` (`/audit-logs`, append-only), `forms.py` (`/forms` + POST/PUT admin
  P2), `records.py` (P2: `/scan-records` submit, history, review-queue, review).
  Lives under `include_router(prefix="/api/v1")` on the same app (NOT a mounted
  sub-app).
- **Serving `/extract-cccd/*`** — VLM extraction; internal, used by the Flutter
  camera flow, `benchmark.py`, and notebooks. No auth on this layer.

Env: `SKIP_MODEL_LOAD=1` runs in **lite mode** (model skipped) — `/health` reports
`db`, `redis`, `lite_mode`. Without it, needs the 4-bit base + adapters (GPU).

**DB (`schema.sql`)** — 6 tables + view `v_scan_record_masked`; seeded with 3
forms (`atm_open`/`health_declare`/`service_contract`). Key columns:
`tblUser.token_version` (bumped to revoke sessions on role change/lock,
change-password P2),
`tblFormType.slug` (business key, UUID is PK — API uses slug),
`tblFormType.required_fields` **JSONB `[{key,label,hint}]`** (P2 — server is the
single source of form metadata),
`tblScanRecord.review_status` (`pending`/`reviewed` — batch results still need
human review) plus P2 `code` (`HS<yyyyMMdd>-<6số>`, server-generated) and `supp`
(JSONB, form extra fields), `tblAuditLog` append-only. Field names are Vietnamese
snake_case (`so_cccd`) everywhere — see `cccd_schema.py`.

**Auth invariants** (all smoke-tested in `backend/smoke_test.py`, 72 cases):
- Login by `identifier` = email OR username (`@`-detection); password ≥8 chars
  with letters+numbers; bcrypt hashes.
- JWT HS256: `sub` (UUID), `role`, `tok_ver`, `jti`, `exp`, `type`. Refresh
  tokens are random 64-char strings, SHA-256-hashed in DB, revocable, 30-day TTL.
- Lockout: 5 failed logins → locked 15 min. Role change / lock → `token_version++`
  + revoke all refresh tokens (old JWT dies immediately).
- Logout revokes refresh + blacklists access `jti` in Redis (`jwt:blacklist`).
  Redis must use `protocol=2` (old Windows build lacks RESP3/HELLO).
- Guards: can't self-demote; can't lock/demote the last active admin.
- P2 change-password: NO OTP (no real SMS/email infra); verifies `current_password`,
  bumps `token_version` + revokes refresh tokens, audits `auth.change_password`.

**Scan-records invariants (P2, in `backend/records.py`)**: `POST /scan-records`
(operator+) issues the server-generated `code` (`_generate_code()` retries on
collision), sets `review_status='pending'`, audits `record.create`; 404 unknown
form, 400 empty `extracted_data`. `GET /scan-records` sends `masked:true` top-level
when the caller is viewer (reads `v_scan_record_masked`, only reviewed records,
CCCD masked `left(...,6) || '******'`); operator sees own records, admin own or
`?user_id=`. `PATCH /scan-records/{id}/review` (operator+) flips pending↔reviewed,
audits `record.review`. RBAC enforced in app layer (RLS not enabled on
`tblScanRecord`).

**Gotchas while editing `backend/`**: psycopg returns UUID objects → wrap with
`str()` for JWT `sub`; DB timestamps are naive → use the `_now_naive()` helper;
FastAPI `TestClient` needs a `with` block to run lifespan; console is cp1252 →
set `PYTHONIOENCODING=utf-8` for Vietnamese output; JSONB columns take
`json.dumps(...)` strings (psycopg3 has no native adapter); `information_schema`
lowercases table names (`tblformtype`) so migration guards use `lower(table_name)`;
`ALTER TABLE ... USING` cannot contain a subquery (use `to_jsonb(text[])`);
`CREATE OR REPLACE VIEW` can't reorder columns → `DROP VIEW IF EXISTS` first.

## Frontend (`frontend/`)

Flutter e-KYC client, layered `features → data → core` (core must never import
data or features). Three contract points, all single-source:

- **[frontend/lib/data/api/cccd_api_client.dart](frontend/lib/data/api/cccd_api_client.dart)**
  is the only file that knows the extract HTTP shape. Four invariants, each of which was a
  real bug: always send `?side=truoc|sau` explicitly (`auto` infers from filename
  and camera files have no `front`/`back` token); decode with
  `utf8.decode(res.bodyBytes)` (FastAPI sends no charset, `http` falls back to
  latin1 and mangles diacritics); errors come back with **HTTP 200** so check
  `body['error']` and `parse_ok`, not just the status code; and there is no
  confidence score anywhere in the backend.
- **[frontend/lib/data/api/auth_api_client.dart](frontend/lib/data/api/auth_api_client.dart)**
  is the only file that knows the `/api/v1/*` shape (`/auth/*`, `/users`,
  `/audit-logs`, `/forms`, `/forms/{slug}`, `/scan-records`, `/scan-records/{id}`,
  `/scan-records/review-queue`, `/scan-records/{id}/review`, `/auth/change-password`).
  It rides on
  [api_client.dart](frontend/lib/data/api/api_client.dart), a wrapper that attaches
  the Bearer token and **auto-refreshes on 401** (once via `/auth/refresh`, then
  replays the original request). Tokens live in Secure Storage
  ([token_store.dart](frontend/lib/data/api/token_store.dart)) — never plaintext.
  Errors from `/api/v1/*` use standard FastAPI `{"detail": "..."}` with a proper
  4xx/5xx status (unlike the extract layer's HTTP-200 convention).
- **`frontKeyMap` / `backKeyMap` in
  [frontend/lib/data/models/id_card.dart](frontend/lib/data/models/id_card.dart)**
  is the only mapping between backend snake_case (`so_cccd`) and app camelCase
  (`idNumber`). It mirrors `FRONT_FIELDS`/`BACK_FIELDS` in `cccd_schema.py` — if
  the schema changes, change it here too. P2 adds `serverKeyMap` /
  `toServerJson()` / `IdCardData.fromServerJson()` for scan-record submission and
  history (same snake_case contract).
- **`sessionStore` is the single owner of the session + records**
  ([session_store.dart](frontend/lib/data/session/session_store.dart)): P1
  `login({identifier, password})`, `register(...)`, `logout()` (calls API + wipes
  Secure Storage + RAM state), `tryAutoLogin()` (startup: refresh token in storage
  → `/auth/me`; failure → back to the login screen). P2 adds `loadForms()`,
  `submitRecord()` (server code returned), `loadRecords()` (`masked` flag for
  viewer), `changePassword()`. Mock mode
  (`ApiConfig.useMock`) bypasses all network.
- **`FormType.fromJson` / `kFormTypes` in
  [frontend/lib/data/models/form_type.dart](frontend/lib/data/models/form_type.dart)**
  — real mode renders forms from `GET /api/v1/forms` (`required_fields`
  `[{key,label,hint}]`); `kFormTypes` is mock-only. Per-slug color/glyph is a
  client-side style map, not data.

Because the backend emits no confidence, the "needs review" flags come from
[frontend/lib/data/validation/card_rules.dart](frontend/lib/data/validation/card_rules.dart):
domain constraints (12 digits + province code 001–096, real calendar dates, sex
matching digit 4 of the ID, expiry landing on the 25/40/60 birthday). `que_quan`,
`noi_thuong_tru` and `co_gia_tri_den` are allowed to be empty — one card layout
does not print them and cards issued at 60+ have no expiry, so blocking on those
would lock out valid users.

`frontend/` ships `lib/` + `pubspec.yaml` only; the platform scaffold is **not
committed** (`.gitignore` excludes it). The current dev machine has it generated
already (`flutter create . --project-name smartid --org vn.smartid`, applicationId
`vn.smartid.smartid`) with CAMERA/INTERNET permissions and
`usesCleartextTraffic="true"` added in `android/app/src/main/AndroidManifest.xml`.
After a fresh clone, regenerate with the same `flutter create` command and re-add
the manifest entries. `flutter analyze` is the check (0 issues) — there is no
test suite. The complete current behavior is documented in
[docs/PRODUCT_SPEC.md](docs/PRODUCT_SPEC.md).

## Docs vs. code drift (important)

`README.md` and `docs/ARCHITECTURE.md` describe an *intended* design that the
current code has diverged from. When they conflict, **trust the code**:

- **Base model**: docs say `Qwen3-VL-8B-Instruct`. Code defaults differ —
  `auto_label.py` → `Qwen2.5-VL-7B-Instruct`;
  `train.py`/`evaluate.py`/`backend/main.py` → `Qwen2.5-VL-3B-Instruct`. Whatever
  base you fine-tune on **must** be the base you evaluate and serve on (pass
  `--model_name`/`--base_model`/`BASE_MODEL` consistently).
- **Splitting**: docs describe group-aware splitting (front+back of the same person
  kept together). Current `prepare_dataset.group_key` returns the file stem, so
  **each image is its own group** (front/back are split independently). This is
  not just cosmetic: the 1436 front images cover only 689 distinct card numbers,
  so **77.1% of front test images have another image of the same card in train**
  and 61.1% have a byte-identical label there. Front-side FA is therefore an
  optimistic estimate — see [docs/Discussion.md](docs/Discussion.md) for the
  measurement and the one-line fix (`group_key` → `so_cccd`).
- **Image dirs**: docs/quick-start mention `data/raw`. Real local images live in
  `data/Front/` and `data/Back/` (capitalized), which are `label_tool`'s defaults.

## Colab / Drive conventions

Notebooks `02`–`04` are driven by a single `MODEL_KEY` variable (`qwen` / `internvl` /
`llama_vision`) in their first cell — they resolve the spec from `vlm_registry` and
derive the base model, the `transformers` version pin, and the checkpoint path
(`{model_key}-cccd-lora-{side}`) from it. Run each notebook once per model. `05`
merges the reports and runs the statistics (no GPU needed).

Notebooks `01`–`05` mount Google Drive and mirror everything under
`MyDrive/cccd_project/` (`code/`, `data/`, `models/`, `checkpoints/`, `result/`) so
progress survives Colab disconnects. `label_tool.save_all()` deliberately writes
JSONL **in place** (no temp-file + `os.replace`) because Drive's FUSE layer turns
atomic renames into duplicate files. Long-running steps (`auto_label`) checkpoint
per-folder so they resume after interruption.
