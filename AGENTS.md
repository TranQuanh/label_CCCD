# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## What this is

Vietnamese national ID card (CCCD) information extraction using a vision-language
model fine-tuned with QLoRA (4-bit), plus a Flutter e-KYC app and a FastAPI backend.
ML lifecycle: auto-label → human review → fine-tune → evaluate → serve. Designed for
a single small GPU (Colab T4 15GB / L4 24GB); `bitsandbytes` 4-bit requires
Linux/Colab/WSL (no Windows-native support), so all GPU work happens on Colab.

Comments, docstrings, and log messages are written in **Vietnamese** — match this
when editing. On Windows, PowerShell 5.1 shows UTF-8 files as mojibake; read them
with the Read tool or `Get-Content -Encoding UTF8`, never "fix" the encoding.

## Repo layout (state after commit c8576e4)

```
frontend/          Flutter e-KYC app. lib/{core,data,features}/
backend/           FastAPI package `backend` (relative imports): /api/v1 + proxy /extract-cccd
model/             ML pipeline copy A: src/{data_pipeline,models,utils} scripts/ notebooks/01–05
src/ scripts/      ML pipeline copy B (repo root): src/{baselines,data_pipeline,utils} scripts/
notebooks/         Colab notebooks 01–06 (06 = OCR baseline), run against copy B on Drive
result_front/ result_back/   committed eval reports (eval_*, gen_cost_*, provenance_*, model_comparison.*)
docs/              ARCHITECTURE.md, PRODUCT_SPEC.md, diagrams/class_diagram.{puml,png}
E2E_TEST_REPORT.md E2E run of 2026-11-02 against d9225bc: known backend defects (DEF-01…29)
/data/ /checkpoints/ /result/ /models/   artifacts (gitignored, anchored at root)
```

**There are two diverged copies of the ML pipeline, and neither is a shim.** The
old root shims (`src/__init__.py` repointing to `model/src`, `app/`, `runpy`
forwarders in `scripts/`) were replaced by real code in c8576e4. Every shared file
(`train.py`, `evaluate.py`, `metrics.py`, `cccd_schema.py`, `auto_label.py`, …)
differs between the two copies.

- `model/` has `src/models/{lora_setup,vlm_registry}.py`; root does not.
- Root has `src/baselines/` (PaddleOCR / VietOCR), `src/utils/console.py`
  (`force_utf8_output`) and `scripts/eval_baseline.py`; `model/` does not.
- Root `scripts/{train,evaluate,benchmark,eval_baseline}.py` and
  `src/baselines/ocr_registry.py` import `src.models.*`, so they fail with
  `ModuleNotFoundError` in this checkout. They work on Colab only because the Drive
  copy (`MyDrive/cccd_project/Data/label_CCCD`) still has `src/models/`.

When a task touches pipeline code, ask which copy is canonical (or change both)
before editing — don't silently fix one and let the other drift further.

## Commands

```bash
# ML pipeline — copy A, run from model/ (scripts put model/ on sys.path)
cd model
python -m src.data_pipeline.auto_label  --input_dir ../data/raw --result_dir ../data/draft
python -m src.data_pipeline.label_tool  --jsonl ../data/draft/raw_draft.jsonl --front_dir ../data/Front --back_dir ../data/Back --share
python -m src.data_pipeline.prepare_dataset --input ../data/draft/raw_draft.jsonl --out_dir ../data/dataset
python scripts/train.py --train_jsonl ... --val_jsonl ... --model_name OpenGVLab/InternVL3_5-2B-HF --output_dir ../checkpoints/internvl-cccd-lora-front
python scripts/evaluate.py --test_jsonl ... --adapter_dir ... --report_path ...   # also writes <report>_preds.jsonl
python scripts/evaluate.py --test_jsonl ... --zero_shot --base_model <hf_id> --report_path ...
python scripts/compare_models.py --report_dir <dir>     # → model_comparison.{json,md}
python scripts/rescore.py rescore --preds <preds.jsonl> --report <report.json>  # re-parse `raw`, no GPU
python -m src.models.vlm_registry --model internvl --image ../data/Front/x_front.jpg  # image-token budget, CPU only
python -m src.models.vlm_registry --check_dir <snapshot_dir>                       # is a download complete?

# OCR baseline — copy B only (needs src/models from the Drive copy, see above)
python scripts/eval_baseline.py --test_jsonl ... --engine paddleocr --report_path ...

# Local Postgres + Redis (Docker, values = config.py defaults; db.py applies schema.sql at startup)
docker start cccd-postgres cccd-redis       # first time: see "Local DB" below

# Backend — run from the repo root (the package is backend/; `app.main` no longer exists)
$env:DATABASE_URL="postgresql://postgres:postgres@localhost:5432/cccd"
$env:REDIS_URL="redis://localhost:6379/0"; $env:JWT_SECRET="dev-secret"; $env:PYTHONIOENCODING="utf-8"
$env:INFERENCE_SERVER_URL="https://<current-ngrok>.ngrok-free.dev"   # Colab GPU server from notebook 04
uvicorn backend.main:app --port 8000        # or: python -m backend.main

# Frontend
cd frontend && flutter pub get
flutter run                                                 # mock mode, no network
flutter run --dart-define=USE_MOCK=false --dart-define=API_BASE_URL=http://10.0.2.2:8000   # Android emulator → host
flutter analyze                                             # the only check
```

`requirements.txt` holds only the proxy-backend deps; the ML deps (torch,
transformers, peft, bitsandbytes, gradio, …) are commented out and get installed by
the notebooks on Colab.

There is no test suite or linter for Python. `metrics.py`, `cccd_schema.py`, and
`lora_setup.py` have `__main__` smoke tests. `backend/smoke_test.py` (auth, RBAC,
forms, scan records, profiles; TestClient, no uvicorn) is **currently broken**:

- it does `from app.main import app`, but `app/` was deleted (use `backend.main`);
- Starlette 1.x's `TestClient` needs `httpx2`, which is not in `requirements.txt`;
- it `TRUNCATE`s tables before `init_db()`, so it fails on a fresh database;
- **its default `DATABASE_URL` is the dev DB `cccd`, and it truncates `tblUser`,
  `tblScanRecord`, `tblAuditLog`, `tblRefreshToken`.** Always point it at a
  throwaway database;
- once running, it reports 39 OK / 5 FAIL and crashes with `StopIteration`. The
  first failure is the self-demote guard bug (see Auth invariants).

## Architecture

### Prompt/schema contract

The pipeline rests on one rule: **prompt and field schema must be identical at
label, train, eval and serve time.** That contract lives in `src/utils/cccd_schema.py`
(`SYSTEM_PROMPT`, `build_user_prompt`, `infer_side_from_filename`,
`FRONT_FIELDS`/`BACK_FIELDS`). Don't hardcode prompts or field names elsewhere.

`infer_side_from_filename` derives the side from tokens in the filename
(`front`/`truoc`/`_mt` → front; `back`/`sau`/`_ms` → back), and
`build_user_prompt(side)` asks only for that side's fields so the model can't
hallucinate fields from the other side. Keep `front`/`back` tokens in filenames.

**Data format (JSONL).** `{"image": ..., "conversations": [{"from": "human", "value":
"<image>\n<prompt>"}, {"from": "gpt", "value": "<json answer>"}]}`. Drafts from
`auto_label` carry `_meta` (`reviewed`, `parse_ok`, `raw_output`); `prepare_dataset`
strips it and **drops records with `reviewed != true`** unless `--allow_unreviewed`.

### Training invariants (`scripts/train.py`, both were hard-won bug fixes)

1. Images go through `vlm_registry.preprocess_image()` (1024px thumbnail) before
   tokenization so image tokens don't overflow `max_length` and swallow the answer
   (was loss 0.0). The same resize must happen at eval and serve time.
2. The collator masks prompt + image/pad tokens to `-100`; loss is only on the JSON
   answer (was stuck loss ~6.38).

**4-bit loading** (`src/models/lora_setup.py`): NF4 + double-quant,
`prepare_model_for_kbit_training(use_reentrant=False)` — do **not** enable gradient
checkpointing a second time (that broke gradient flow). Training uses
`padding_side='right'` (`_check_padding_side` enforces it). Models load via
`AutoModelForImageTextToText`; only `auto_label.py` picks a concrete Qwen class.

### Multi-model registry (`src/models/vlm_registry.py`)

Second source of truth after `cccd_schema.py`; nothing model-specific belongs
outside it. It separates what must be **identical** across models
(`SHARED_LORA_TARGETS`, `SHARED_IMAGE_MAX_SIDE=1024`, `SHARED_LORA_R/ALPHA/DROPOUT`)
from what is **architecture-forced** per `VLMSpec` (`processor_kwargs`,
`vision_prefixes`, `max_length`, `nested_images`, `gated`). Keys: `qwen`
(Qwen2.5-VL-3B), `internvl` (InternVL3.5-2B), `llama_vision` (Llama-3.2-11B-Vision).

- Bare-name `target_modules` attach LoRA to the **vision tower** on all three
  models (their ViTs reuse `q_proj`/`gate_proj`/… names), and freezing the tower
  first doesn't help because new `lora_A/B` layers are trainable. Use
  `build_lora_target_regex()`; `assert_no_vision_lora()` raises on leaks.
- `generation_config.json` defaults differ (some sample), so
  `build_gen_kwargs()` forces greedy; any serving code must mirror it.
- Never treat `config.json.exists()` as "snapshot downloaded" — `snapshot_download`
  writes config before shards. Use `snapshot_complete()` / `ensure_snapshot()`;
  `resolve_model_dir()` picks Drive vs Colab SSD by `VLMSpec.weights_gb` (Llama
  ~21GB does not fit Drive).
- `train.py` writes `vlm_meta.json` next to the adapter; eval/serve read it to pick
  the base model. The base you fine-tune on must be the base you evaluate and serve.

### Metrics (`src/utils/metrics.py`)

Field Accuracy (exact match after normalization — the headline metric), CER, and
token micro-F1. Normalization: NFC, whitespace collapse, lowercase,
`null`/`none` → `""`. `safe_parse` must stay equal to the *parse* half of
`auto_label.parse_json_safe` (bare `json.loads` → strip ```` ```json ```` fence →
regex first `{...}`). **Never** port `parse_json_safe`'s content rewrites
(nulling `dac_diem_nhan_dang` with `/`, canonicalising `noi_cap`) into `safe_parse`:
gold goes through the same function, so it would rewrite the ground truth.

### Comparison and its caveats

6 VLM runs = 3 models × {zero-shot, fine-tuned} per side, plus OCR baselines
(PaddleOCR, PaddleOCR+VietOCR, with `ablation/` variants), all scored by the same
`metrics.evaluate`. Reports live in `result_front/` and `result_back/`.

The split is **per image, not per card**: `prepare_dataset.group_key` returns the
file stem. 1436 front images cover 689 card numbers, so 77.1% of front test images
have another image of the same card in train — front FA is optimistic. The fix is
`group_key` → `so_cccd`. Labels are also noisy: 46.3% of same-card image groups
carry differing labels.

### Serving

The **GPU inference server is not in this repo any more.** It was `app/main.py`
(`discover_adapters`, `select_adapter`, `run_inference_batch`, `GPU_LOCK`), deleted
in c8576e4. Notebook 04 still launches `uvicorn app.main:app` from the Drive copy and
exposes it via ngrok; `scripts/benchmark.py --mode local` also imports it, so local
benchmark mode fails in this checkout. If that file is restored, its invariants
were: left padding on the inference tokenizer, `def` (not `async def`) endpoints,
and one lock covering both `set_adapter` and `generate`.

`backend/main.py` is a **proxy only**: `config.SKIP_MODEL_LOAD` is hardcoded
`True`, and `/extract-cccd/` and `/extract-cccd/batch` forward the upload with
`requests.post` to `config.INFERENCE_SERVER_URL` (env, defaults to a hardcoded public
ngrok domain). They need **no auth** and don't validate size, type or `side`. They
always answer HTTP 200, with failures in `error`; an upstream non-2xx JSON body is
relayed as-is, without `error`/`parse_ok`. `/health` always reports
`status: "ok", lite_mode: true, proxy_mode: true`, even when `db`/`redis` are false.

## Backend (`backend/`)

User API under `include_router(prefix="/api/v1")` on the same app: `auth.py`,
`users.py` (admin RBAC), `audit.py` (append-only), `forms.py`, `records.py`
(scan records), `profiles.py` (`/profiles` CRUD on `tblCccdProfile`, many peer
profiles per user, no default). Config is read only through `config.py`. There is
**no `CORSMiddleware`**, so a Flutter Web build (any browser origin) cannot call the
API; native Android is unaffected.

**Roles are only `user` < `admin`** (`deps.ROLE_LEVELS`; `operator`/`viewer` are
gone). `/auth/register` always creates `user`, and no endpoint creates the first
admin. Bootstrap it with SQL (`INSERT … role='admin'` with a bcrypt hash).

**`schema.sql` runs on every startup** (`db.init_db()` from the lifespan), so it must
stay idempotent with respect to user data, and today it isn't:
- The form seed uses `ON CONFLICT (slug) DO UPDATE`, so any admin edit to
  `atm_open`/`health_declare`/`service_contract` is reverted on restart.
- The legacy-profile migration copies `tblUser.cccd_profile` into `tblCccdProfile`
  for every user with zero profiles and never clears the column. A user who deletes
  all their profiles gets the legacy one back on the next start.

`migrate_now.sql` is a manual copy of the same migrations; keep it in sync.

**CCCD profiles live in two places.** `tblUser.cccd_profile` is marked DEPRECATED
in `schema.sql` (a migration copies it into `tblCccdProfile` once per user), but
`auth.py` still serves `GET/PUT/DELETE /auth/profile` reading and writing that
column. New code uses `/profiles`.

**DB (`schema.sql`, applied idempotently by `db.py`)**: 6 tables, no views:
`tblUser`, `tblRefreshToken`, `tblFormType`, `tblScanRecord`, `tblAuditLog`,
`tblCccdProfile`; seeded with forms `atm_open`/`health_declare`/`service_contract`.
Dropped by `DO $$` migrations, so leave them out of new code: `tblBatchJob`,
`tblScanRecord.{review_status,raw_output,confidence_scores,batch_job_id}`,
`tblCccdProfile.is_default`. `tblUser.token_version` is bumped to revoke sessions;
`tblFormType.slug` is the business key (API uses slug, UUID is PK);
`required_fields` is JSONB `[{key,label,hint}]`; `tblScanRecord` has a
server-generated `code` (`HS<yyyyMMdd>-<6 digits>`), JSONB `supp`, `card_side`
(`front`/`back`/`both`) and `is_hidden`. `tblAuditLog.target_id` is polymorphic
(no FK). Field names are Vietnamese snake_case (`so_cccd`) everywhere.

`docs/diagrams/class_diagram.puml` is a code-level class diagram of the 6 tables
(classes `User`, `ScanRecord`, … plus `SuppFieldDef`): every column the backend
reads or writes, in camelCase with Java-style types (`String`, `int`, `boolean`,
`Date`, `UUID`, `Map<…>`, `ArrayList<…>`), FKs drawn as object references
(`user : User`, `scanRecords : ArrayList<ScanRecord>`), multiplicities `0..1`
for nullable FKs (◆ = `ON DELETE CASCADE`/embedded, ◇ = nullable FK). DB-only
columns no code touches (`created_at` of `tblRefreshToken`/`tblFormType`) are
left out. Update it with any schema change and
re-render with `java -jar <plantuml.jar> -charset UTF-8 -tpng <file>.puml` (the jar
ships in the VS Code PlantUML extension). Graphviz isn't installed, hence
`!pragma layout smetana`; keep the `{field}` prefix on attribute lines (any line
containing parentheses is otherwise parsed as a method and hidden).

**Local DB**: containers `cccd-postgres` (`postgres:16-alpine`, volume
`cccd-pgdata`, db `cccd`, `postgres`/`postgres`) and `cccd-redis`
(`redis:7-alpine`) on the default ports, `--restart unless-stopped`. There is no
compose file; recreate with `docker run -d --name cccd-postgres -e
POSTGRES_PASSWORD=postgres -e POSTGRES_DB=cccd -p 5432:5432 -v
cccd-pgdata:/var/lib/postgresql/data postgres:16-alpine` and `docker run -d --name
cccd-redis -p 6379:6379 redis:7-alpine`. psycopg isn't installed outside the
backend venv; for ad-hoc SQL use `docker exec cccd-postgres psql -U postgres -d cccd`.

**Auth invariants**: login `identifier` = email or username (`@` detection).
Register lower-cases the email but login does not. Password ≥8 chars with
letters+digits; bcrypt; unknown users are verified against a dummy hash so timing
doesn't leak existence. JWT HS256 with `sub`, `role`, `tok_ver`, `jti`, `exp`,
`type`; `JWT_SECRET` falls back to `dev-secret` with only a warning. Refresh tokens:
random 64 chars, SHA-256 in DB, 30-day TTL, not rotated. 5 failed logins → 15-min
lock (`LOCK_MINUTES`). Role change, lock or admin password reset →
`token_version++` + revoke refresh tokens.

Logout revokes **all** of the user's refresh tokens and blacklists the access `jti`
in Redis under `cccd:blacklist:jti:<jti>` with TTL = remaining token life. Redis is
optional and **fails open**: if unreachable, the blacklist is skipped (logout
doesn't kill the access token) and `get_redis()` retries the connection on every
request. The Redis client must use `protocol=2` (old Windows build lacks RESP3).

Last active admin can't be demoted or locked. "Can't self-demote" is intended, but
`users.update_user` compares the `str` path param with psycopg's `UUID`, so that
guard never fires. There is no self-lock guard either. Change-password has no OTP;
it verifies `current_password`, bumps `token_version` (which also revokes the
**current** session, despite its docstring) and audits `auth.change_password`.

**Scan records** (no review flow, no masking: both were removed). `POST
/scan-records` is open to any logged-in user; it generates `code` (local-time date,
retries on collision) and audits `record.create`. `GET` and `GET /{id}`: `user`
sees own records minus hidden ones (`?user_id`/`?all_users` are ignored); admin
sees own, `?user_id=`, or `?all_users=true` (hidden included). `PATCH /{id}` lets
owner/admin edit `extracted_data`/`supp`/`parse_ok`/`is_edited`, with PUT
semantics: omitted `supp` becomes `{}`. `PATCH /{id}/visibility` (admin) sets
`is_hidden` and audits `record.hide`/`record.show`; a hidden record returns 404 to
its owner. There is no delete for records or users. RBAC is app-layer only;
`extracted_data` is not validated server-side (rules live in `card_rules.dart`).

**Gotchas**:
- psycopg returns `uuid.UUID`: wrap in `str()` for JWT `sub` and before comparing
  with path params. Ids arrive as `str`, and a malformed one reaches Postgres as
  `InvalidTextRepresentation` → 500 (only `profiles.py` and `/visibility` parse
  them first).
- Unbounded strings into `VARCHAR(255)` → 500. `User-Agent`/`device_info` are
  stored as-is in `tblRefreshToken.device_info`, so a long User-Agent breaks login
  and register.
- `UniqueViolation` isn't caught; check-then-insert races return 500.
- DB timestamps are naive UTC (`_now_naive()`) and the API serialises them without
  `Z`. Never call `.timestamp()` on them: Python treats naive values as local time.
- `audit()` writes whatever metadata it's given. `user.update` currently logs
  `body.model_dump()`, which includes a reset password in plain text.
- `TestClient` needs a `with` block for lifespan; JSONB params take
  `json.dumps(...)`; `information_schema` lowercases table names;
  `ALTER TABLE ... USING` can't contain a subquery.

The full list with repro steps is in `E2E_TEST_REPORT.md` §11.

## Frontend (`frontend/`)

Layered `features → data → core` (core never imports data or features).

**The data layer has never been committed.** An old unanchored `data/` rule in the
root `.gitignore` swallowed `frontend/lib/data/`. The rule is now `/data/` (root
only, with a warning comment), so the directory shows as untracked, but no commit
in history contains it. The copy on this machine is a **stale pre-P1 version** and
the app doesn't compile against it:
- `data/api/auth_api_client.dart` is missing (imported by the three
  `features/admin/*_tab.dart`);
- `session_store.dart` lacks 19 members the screens call (`tryAutoLogin`,
  `register`, `loadForms`, `submitRecord`, `changePassword`, `loadRecords`,
  `loadProfiles`, `updateRecord`, `forms`, `profiles`, `role`, …);
- `FormType` lacks `layout`.

Restoring it needs the author's copy. Don't regenerate it from the bullets below,
which describe the intended contract.

Contract points (all single-source):

- `data/api/cccd_api_client.dart` — the only file that knows the extract HTTP
  shape. Always send `?side=truoc|sau` (camera files have no side token); decode
  with `utf8.decode(res.bodyBytes)` (no charset → latin1 mangles diacritics);
  extract errors come back as **HTTP 200** with `body['error']` / `parse_ok`; there
  is no confidence score.
- `data/api/auth_api_client.dart` — the only file that knows `/api/v1/*`
  (standard `{"detail": ...}` with real 4xx/5xx). Bearer token, auto-refresh once
  on 401, tokens in Secure Storage.
- `frontKeyMap` / `backKeyMap` in `data/models/id_card.dart` — the only mapping
  between backend snake_case and app camelCase; mirrors `FRONT_FIELDS`/`BACK_FIELDS`.
- `data/session/session_store.dart` — single owner of session and records
  (login/register/logout/tryAutoLogin, forms, submit, history, change password).
  `ApiConfig.useMock` bypasses the network.
- `data/validation/card_rules.dart` — "needs review" flags from domain rules
  (12 digits + province 001–096, real dates, sex vs digit 4, expiry on the
  25/40/60 birthday). `que_quan`, `noi_thuong_tru`, `co_gia_tri_den` may be empty.

The platform scaffold (`android/`, `ios/`, `web/`, …) is gitignored in the root
`.gitignore` (there is no `frontend/.gitignore` any more). Regenerate with
`flutter create . --project-name smartid --org vn.smartid`, then re-add CAMERA and
INTERNET permissions and `usesCleartextTraffic="true"` in
`android/app/src/main/AndroidManifest.xml`. Full behavior: `docs/PRODUCT_SPEC.md`.

## Docs vs. code

When `README.md`, `docs/ARCHITECTURE.md` or `requirements.txt` comments disagree
with the code, trust the code. Known drift: README still describes `src/`, `app/`,
`scripts/` as shims (they are real code, and `app/` is gone); docs name Qwen3-VL-8B while code defaults are Qwen2.5-VL-7B
(auto-label) and Qwen2.5-VL-3B (train/eval); docs describe group-aware splitting
(it is per image); quick-starts mention `data/raw` but images live in `data/Front/`
and `data/Back/`. `docs/VLM_COMPARISON_PLAN.md`, `Discussion.md` and `CHANGELOG.md`
are referenced in places but no longer exist.

## Colab / Drive conventions

Notebooks are driven by one `MODEL_KEY` (`qwen`/`internvl`/`llama_vision`) and a
`SIDE`, resolve everything from `vlm_registry`, and name checkpoints
`{model_key}-cccd-lora-{side}`. They mirror state under `MyDrive/cccd_project/`
so work survives disconnects, and import code from the Drive repo copy at
`MyDrive/cccd_project/Data/label_CCCD`. `label_tool.save_all()` writes JSONL **in
place** on purpose — Drive's FUSE layer turns atomic renames into duplicate files.
`auto_label` checkpoints per folder so it resumes after interruption.
