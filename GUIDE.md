# CPNS LMS — Complete System Guide

A holistic reference covering architecture, every technical component, and all design decisions behind the system. Written for the person who built it and wants to understand the whole picture.

---

## Table of Contents

1. [System Purpose](#1-system-purpose)
2. [High-Level Architecture](#2-high-level-architecture)
3. [Repository Structure](#3-repository-structure)
4. [Layer 1 — Rust Backend](#4-layer-1--rust-backend)
5. [Layer 2 — Python ML Service](#5-layer-2--python-ml-service)
6. [Layer 3 — Admin Web](#6-layer-3--admin-web)
7. [Layer 4 — iOS Client](#7-layer-4--ios-client)
8. [Data Models & Schemas](#8-data-models--schemas)
9. [Question Taxonomy](#9-question-taxonomy)
10. [Scoring System](#10-scoring-system)
11. [AI Pipeline](#11-ai-pipeline)
12. [Sync Strategy (iOS ↔ Backend)](#12-sync-strategy-ios--backend)
13. [Service Management](#13-service-management)
14. [API Reference](#14-api-reference)
15. [Development Setup](#15-development-setup)
16. [Key Design Decisions](#16-key-design-decisions)

---

## 1. System Purpose

An **iPad-first Learning Management System** for people preparing for the Indonesian civil servant (CPNS) national exam. The exam has three scored categories:

| Category                            | Focus                                                         | Scoring                                       |
| ----------------------------------- | ------------------------------------------------------------- | --------------------------------------------- |
| **TWK** (Tes Wawasan Kebangsaan)    | Civic knowledge — Pancasila, UUD 1945, history, government    | Binary: 5 pts correct, 0 wrong                |
| **TIU** (Tes Intelegensi Umum)      | Intelligence — verbal analogies, logic, arithmetic, sequences | Binary: 5 pts correct, 0 wrong                |
| **TKP** (Tes Karakteristik Pribadi) | Behavioral/situational judgment                               | Weighted: 1–5 pts per option, no wrong answer |

The LMS lets an **admin** create and manage quiz sets via a web dashboard, and **students** practice on an iPad app — offline-first, with handwritten notes using Apple Pencil. An AI layer generates explanations and new questions on demand.

---

## 2. High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                        MONOREPO ROOT                                  │
│                     lms-kdwiheldy/                                    │
└──────────────────────────────────────────────────────────────────────┘
         │                   │                    │                   │
  [iPad App]           [Rust Server]        [Admin Web]        [ML Service]
 client-ios/             server/            admin-web/          ml-service/
  SwiftUI               Axum + MongoDB       Next.js 15         asyncio + Ollama
  PencilKit             REST API             TypeScript         RAG + gemma4:e4b
  SwiftData             Port 3000            Port 3001          Unix Domain Socket
  Offline-first         Single process       Browser app        Started by Rust
         │                   │                    │
         └─── HTTPS/JSON ────┤                    │
              (sync on save)  └─── HTTPS/JSON ────┘
                               (admin browser calls)
                                       │
                              ┌────────┴────────┐
                              │  Unix Domain     │
                              │  Socket (UDS)    │
                              │  /tmp/lms-ml.sock│
                              └────────┬────────┘
                                       │
                              [ML Service (Python)]
                                       │
                              localhost:11434
                              [Ollama — gemma4:e4b]
```

The Rust server and ML service communicate via **Unix Domain Socket (UDS)** — no TCP overhead, no port conflicts, and the Rust server manages the ML service lifecycle (auto-starts, watchdog restarts).

---

## 3. Repository Structure

```
lms-kdwiheldy/
├── server/                    # Rust Axum backend
│   ├── src/
│   │   ├── main.rs            # Router, AppState, service startup
│   │   ├── config.rs          # All env-var config with defaults
│   │   ├── error.rs           # Unified AppError type
│   │   ├── ml_client.rs       # Length-prefix UDS client for ML service
│   │   ├── service_manager.rs # Auto-start + watchdog for Ollama & ML service
│   │   ├── middleware/
│   │   │   └── auth.rs        # JWT (admin) + device key (iPad) middleware
│   │   ├── models/
│   │   │   └── quiz.rs        # Quiz, Question, QuestionOption, SubtypeConfig
│   │   └── routes/
│   │       ├── quizzes.rs     # Quiz CRUD + publish toggle
│   │       ├── questions.rs   # Question CRUD + AI generate + explain
│   │       └── upload.rs      # Image upload → /uploads/
│   ├── uploads/               # Uploaded images served statically
│   └── .env                   # Local config (not committed)
│
├── ml-service/                # Python ML service (asyncio socket server)
│   ├── serve.py               # Socket server: explain, generate, analogi verbs
│   ├── embedder.py            # Sentence embedding + cosine search (RAG)
│   ├── math_parser.py         # Plain-text math → LaTeX + arithmetic verifier
│   ├── analogi_engine.py      # Symlink → ../scripts/analogi_engine.py
│   ├── data/
│   │   ├── embeddings.npy     # Pre-computed 384-dim vectors (400 questions)
│   │   └── questions.json     # Question metadata for RAG lookup
│   └── .venv/                 # Python virtualenv (sentence-transformers, requests, Pillow, etc.)
│
├── admin-web/                 # Next.js 15 admin dashboard
│   └── src/
│       ├── app/               # App router pages
│       ├── components/        # Reusable UI components
│       ├── lib/api.ts         # Typed axios client for all backend calls
│       └── types/index.ts     # Shared TypeScript types
│
├── client-ios/                # SwiftUI iPad app (Xcode project)
│   └── lms/
│       ├── Models/            # SwiftData @Model classes
│       ├── Services/          # APIClient (network), SyncManager (offline sync)
│       ├── ViewModels/        # QuizSessionViewModel (business logic)
│       └── Views/             # SwiftUI views
│
└── scripts/                   # Data & tooling
    ├── *.json                 # 25 quiz data files (bulk import format)
    ├── analogi_engine.py      # Analogi gambar rendering + image pipeline
    └── gen_analogi_llm.py     # CLI tool: LLM → analogi spec → DB
```

---

## 4. Layer 1 — Rust Backend

### Technology choices

- **Rust + Axum**: High-performance async HTTP server. Low memory footprint — important for a VPS with Ollama also running. Compile-time safety eliminates a class of runtime bugs.
- **MongoDB** via the official `mongodb` crate: Questions are nested inside quiz documents (embedded documents). This fits the access pattern: quizzes are always fetched with all their questions together.
- **No ORM**: Raw BSON documents with serde. Keeps the model simple and avoids abstraction overhead.

### Configuration (`config.rs`)

All config comes from environment variables with sensible defaults:

| Env Var           | Default (macOS)                     | Purpose                          |
| ----------------- | ----------------------------------- | -------------------------------- |
| `MONGODB_URI`     | `mongodb://localhost:27017`         | MongoDB connection string        |
| `MONGODB_DB`      | `lms`                               | Database name                    |
| `UPLOAD_DIR`      | `./uploads`                         | Where uploaded images are stored |
| `PUBLIC_BASE_URL` | `http://localhost:3000`             | Used in generated image URLs     |
| `PORT`            | `3000`                              | HTTP server port                 |
| `ML_SOCKET_PATH`  | `/tmp/lms-ml.sock`                  | UDS path for ML service          |
| `OLLAMA_BIN`      | `/Applications/Ollama.app/…/ollama` | Path to Ollama binary            |
| `ML_SERVICE_DIR`  | `../ml-service`                     | Directory of Python ML service   |
| `MANAGE_SERVICES` | `true`                              | Auto-start Ollama + ML service   |

_(No authentication is implemented — all routes are currently open. See §16 for the planned auth approach.)_

### AppState

Every route handler receives a clone of `AppState` via Axum's `State` extractor:

```rust
pub struct AppState {
    pub db:     mongodb::Database,  // MongoDB connection pool
    pub config: Arc<Config>,        // Shared config (immutable after startup)
    pub ml:     Arc<MlClient>,      // ML service client over UDS
}
```

### Route table

All routes are registered in `main.rs`. Authentication is applied per-route via Axum middleware layers.

**All routes are currently unauthenticated.**

**Public routes (iPad app)**

| Method | Path                             | Handler                            | Description                                          |
| ------ | -------------------------------- | ---------------------------------- | ---------------------------------------------------- |
| GET    | `/api/v1/quizzes`                | `quizzes::list_published`          | Quiz list (metadata only, published only)            |
| GET    | `/api/v1/quizzes/{id}`           | `quizzes::get_quiz_with_questions` | Full quiz + questions; `?since=<ISO>` for delta sync |
| GET    | `/api/v1/questions/{id}/explain` | `questions::explain`               | AI explanation for one question                      |

**Admin routes**

| Method         | Path                                       | Handler                             | Description                         |
| -------------- | ------------------------------------------ | ----------------------------------- | ----------------------------------- |
| GET            | `/api/v1/admin/quizzes`                    | `quizzes::admin_list`               | All quizzes (incl. drafts)          |
| POST           | `/api/v1/admin/quizzes`                    | `quizzes::admin_create`             | Create quiz                         |
| GET/PUT/DELETE | `/api/v1/admin/quizzes/{id}`               | `quizzes::admin_*`                  | CRUD on one quiz                    |
| POST           | `/api/v1/admin/quizzes/{id}/publish`       | `quizzes::admin_toggle_publish`     | Toggle published flag               |
| GET            | `/api/v1/admin/questions`                  | `questions::admin_list`             | All questions; `?quiz_id=X` filter  |
| POST           | `/api/v1/admin/questions`                  | `questions::admin_create`           | Add one question to a quiz          |
| GET/PUT/DELETE | `/api/v1/admin/questions/{id}`             | `questions::admin_*`                | CRUD on one question                |
| POST           | `/api/v1/admin/questions/bulk`             | `questions::admin_bulk_import`      | Create quiz + all questions at once |
| POST           | `/api/v1/admin/questions/generate`         | `questions::admin_generate`         | LLM: generate similar to source     |
| POST           | `/api/v1/admin/questions/generate/analogi` | `questions::admin_generate_analogi` | LLM: generate analogi gambar        |
| POST           | `/api/v1/admin/upload/image`               | `upload::upload_image`              | Upload image → `/uploads/`          |
| GET            | `/uploads/*`                               | `ServeDir`                          | Static image serving                |

### Data storage: Embedded documents

MongoDB is used with **fully embedded documents** — no `$lookup` joins needed:

```
quizzes collection
└── Quiz document
    ├── id, title, category, ...
    └── questions: [
            Question { id, content, subtype, options: [Option, ...] }
            Question { ... }
        ]
```

The `/api/v1/admin/questions` endpoint queries across all quizzes by iterating quiz documents and flattening their `questions` arrays. This is fine at current scale (hundreds of questions). At tens of thousands, a separate collection would be needed.

---

## 5. Layer 2 — Python ML Service

### Overview

A lightweight asyncio socket server that provides AI capabilities via a local Ollama LLM. Communicates with the Rust server exclusively over a Unix Domain Socket using a simple length-prefix protocol — no HTTP, no FastAPI. Uses **Retrieval-Augmented Generation (RAG)**: before calling the LLM, it retrieves the 3 most similar questions from a pre-built embedding store and injects them as few-shot examples.

### Startup & lifecycle

The Rust server starts this service automatically via `ServiceManager`. The ML service is a plain Python process — no Docker, no ASGI stack, no special setup required beyond having the `.venv` with dependencies installed.

```
cargo run (from server/)
  → ServiceManager::ensure_ml_service()
  → spawns: .venv/bin/python serve.py
  → watchdog loop every 15s: restarts if dead
```

### Embedder (`embedder.py`)

Uses `intfloat/multilingual-e5-small` (117M params, 384-dimensional embeddings, natively supports Indonesian).

- At startup: loads pre-computed embeddings from `data/embeddings.npy` and metadata from `data/questions.json` (400 representative questions)
- On each request: embeds the incoming question text, does cosine similarity search over 400 vectors (~1ms), returns top-3 results as few-shot examples

**Why multilingual-e5-small?** It understands Indonesian without needing translation, runs on CPU in ~50ms per embed, and 117M params means it fits comfortably alongside Ollama.

### Math parser (`math_parser.py`)

A deterministic plain-text math → LaTeX converter with an arithmetic verifier. The LLM writes math as plain text (e.g., `3/4 + 5/6 =`). The math parser:

1. **Detects** math spans in text using anchors (`/`, `^`, `√`, `×`, `÷`) plus expansion rules
2. **Converts** to LaTeX: `3/4` → `\frac{\text{3}}{\text{4}}`, `2^5` → `2^{\text{5}}`, `√169` → `\sqrt{\text{169}}`
3. **Evaluates** arithmetic using `fractions.Fraction` for exact results (avoids floating-point)
4. **Corrects** hallucinated results: if the LLM writes `3/4 + 5/6 = 2/3`, the parser detects the mismatch, computes `19/12`, and replaces the wrong value

**Key decision:** The LLM is instructed to write expressions ending with `=` and leave the result blank (e.g. `"Sehingga 3/4 + 5/6 ="`). The math parser then appends the computed LaTeX result. This separates concerns — the LLM handles explanation logic, Python handles arithmetic correctness.

### Wire protocol

The Rust client and Python server speak a length-prefix protocol over the UDS:

```
Request:  "<verb> <byte_length>\n<json_bytes>"
Response: "ok <byte_length>\n<json_bytes>"
       or "error <byte_length>\n<message>"
```

Verbs: `explain`, `generate`, `analogi`. Because the only caller is the Rust server (compile-time typed), there is no schema validation on the Python side — the JSON is trusted to be structurally correct.

### Verbs

#### `explain`

Input: `{ question, options[{label, content, score}], subtype }`  
Output: `{ explanation, tip }`

Flow:

1. Pick system prompt based on subtype (math / language / civic / situational)
2. Retrieve 3 similar questions from embedding store (RAG)
3. Build few-shot prompt: 3 examples + the question
4. Call Ollama (`gemma4:e4b`)
5. Apply `plain_to_latex()` if subtype is numeric
6. Return explanation + tip

**Short-circuit:** For subtypes where the LLM can't add value (ANALOGI_GAMBAR — can't see images; ANTONIM/SINONIM/ANALOGI_VERBAL — simple lookups; TKP — stored explanations are sufficient), the Rust server returns the pre-written `explanation` field directly without calling the ML service at all. This decision is encoded in `SubtypeConfig.needs_ml_explain`.

#### `generate`

Input: `{ source_question, source_options[{label, content, score}], category, subtype }`  
Output: `{ content, options[{label, content, score}], explanation, tip }`

Flow for non-TKP subtypes:

1. Retrieve up to 5 similar questions (RAG); exclude the source question itself
2. Build generation prompt with source question as reference
3. Call Ollama → get `{ content, options, correct_label, explanation, tip }`
4. Validate: must have exactly 5 options; `correct_label` must be valid
5. **For math subtypes:** Try direct computation from question content (e.g. evaluate `3/4 + 5/6 =` to find which option `19/12` is). If the answer isn't in any option → reject.
6. **LLM correction pass:** If direct computation is inconclusive, send the question + options + explanation back to Ollama with a correction prompt. The correction prompt is instructed to make minimal changes (fix `correct_label` or fix one option content — never rewrite explanation or other options).
7. **Python deterministic inference:** Parse the final answer from the explanation text (`"= 19/12"`) and verify it matches an option.
8. Build `GeneratedOption` objects with `score=5` for correct option, `score=0` for others.

Flow for TKP subtypes:

1. Same RAG retrieval and prompt
2. LLM is instructed to output `score` per option (1–5), not a `correct_label`
3. Validate: 5 options, each with a score; must have ≥3 distinct scores (so options aren't all the same weight)
4. Clamp scores to 1–5 range
5. Return options with their LLM-assigned scores directly

#### `analogi`

No input required (self-contained generation).  
Output: `{ content, image_url, explanation, options[{label, content(=image_url), score}] }`

Flow (up to 3 attempts):

1. Call Ollama with `ANALOGI_SPEC_SYSTEM_PROMPT` → JSON spec describing 4 cells of shapes
2. Extract and normalize spec (coerce int fills to bool, set rotation defaults, etc.)
3. Validate spec (check positions are valid, no duplicate positions within a cell, etc.)
4. Call `analogi_engine.process_no_db(spec)`:
   - Render the A:B=C:? composite image via Pillow
   - Generate 4 distractors
   - Shuffle all 5 options (correct + 4 distractors)
   - Render each option cell as a PNG
   - Upload all images to Rust server (`POST /api/v1/admin/upload/image`)
5. Return the question data (no DB save — the admin reviews first)

### Subtype routing logic

```python
_MATH_SUBTYPES     = {ARITMATIKA, DERET_ANGKA, PERBANDINGAN_KUANTITATIF, SOAL_CERITA}
_LANGUAGE_SUBTYPES = {SINONIM, ANTONIM, ANALOGI_VERBAL, SILOGISME}
_CIVIC_SUBTYPES    = {PANCASILA, UUD_1945, BHINNEKA, NKRI, SEJARAH_NASIONAL,
                      SISTEM_PEMERINTAHAN, BELA_NEGARA, BAHASA_INDONESIA}
_SITUATIONAL_SUBTYPES = {all 9 TKP subtypes}
```

Each set gets its own system prompt tuned for that domain:

- **Math**: instructs explicit step-by-step calculation, leave `=` open
- **Language**: instructs semantic/logical pattern explanation
- **Civic**: instructs citation of specific laws, articles, historical dates
- **Situational (TKP)**: instructs ASN (civil servant) value alignment; weighted scoring 1-5

### Ollama model

`gemma4:e4b` — A multilingual LLM with strong Indonesian language support and good reasoning ability. Runs locally on CPU (slow, ~30s per call) or GPU. Timeout set to 180s.

---

## 6. Layer 3 — Admin Web

### Technology

Next.js 15 (App Router), TypeScript, Tailwind CSS, React Query (TanStack Query), React Hook Form + Zod, Axios, react-hot-toast.

### Pages

| URL                                   | Purpose                                                   |
| ------------------------------------- | --------------------------------------------------------- |
| `/`                                   | Dashboard home                                            |
| `/quiz-sets`                          | List all quiz sets                                        |
| `/quiz-sets/new`                      | Create a quiz set                                         |
| `/quiz-sets/[id]`                     | Edit quiz set metadata + view/manage its questions        |
| `/quiz-sets/[id]/questions/new`       | Add a new question manually                               |
| `/quiz-sets/[id]/questions/[qid]`     | Edit an existing question                                 |
| `/quiz-sets/[id]/generate`            | **Subtype-first AI generation page**                      |
| `/quiz-sets/[id]/generate/[sourceId]` | Generate similar to a specific source question            |
| `/questions`                          | Global question bank (all questions across all quiz sets) |

### Question generation UX (`/quiz-sets/[id]/generate`)

The generation page has two flows:

**Non-analogi subtypes:**

1. Admin picks a subtype from the category's subtype list (e.g. SILOGISME for a TIU quiz)
2. The page fetches all questions across all quiz sets to find one of that subtype as a seed
3. Calls `POST /admin/questions/generate` with the seed question
4. Shows preview: question text, options (correct option highlighted in green), explanation, tip
5. Admin clicks "Add to quiz" (saves) or "Skip" (generates another)
6. On save: the question is added to the current quiz, and a new generation starts immediately

**ANALOGI_GAMBAR:**

1. Admin picks ANALOGI_GAMBAR
2. Calls `POST /admin/questions/generate/analogi` (no seed needed — LLM generates from scratch)
3. Shows preview: question composite image (A:B=C:?), then 5 option images in a 3-column grid, correct option has a green border
4. Same Accept/Skip flow

**"Generate Similar" button (on question edit page):**
For non-ANALOGI_GAMBAR, non-TKP questions, a Wand2 icon button links to `/generate/[questionId]` — the old source-triggered flow that uses the specific question as a seed.

### Components

| Component            | Key responsibility                                                                                                                                                                                                                                       |
| -------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `QuestionEditor.tsx` | Full question form with Zod validation. Handles MCQ (radio for correct option), TRUE_FALSE, ESSAY, IMAGE types. Subtype dropdown filtered by quiz category. Score-based correctness: clicking a radio sets that option's score to 5 and all others to 0. |
| `QuizSetForm.tsx`    | Title, description, category, time_limit form                                                                                                                                                                                                            |
| `MathText.tsx`       | Renders text with LaTeX math expressions using a math rendering library                                                                                                                                                                                  |
| `Sidebar.tsx`        | Navigation: Dashboard, Quiz Sets, Questions                                                                                                                                                                                                              |

### Scoring in the editor

A key decision: options don't have a separate `is_correct` field. Correctness is implied by score:

- MCQ/TF/TWK/TIU: correct option gets `score = 5`, wrong options get `score = 0`
- TKP: each option gets a distinct score 1–5 chosen by the admin
- The UI shows a radio button group for MCQ/TF that marks one option correct; TKP shows numeric score inputs

---

## 7. Layer 4 — iOS Client

### Technology

Swift 6, SwiftUI, SwiftData, PencilKit. Target: iPad (landscape). Requires iOS 17+.

### Offline-first design

The app works without internet. Data is stored locally in SwiftData. The sync with the backend happens explicitly:

- **Quiz download**: triggered by the user tapping a quiz to open it
- **Session upload**: triggered automatically after completing a quiz; retried on next launch if it fails

### Key SwiftData models

```swift
LocalQuiz        — mirrors backend quiz (+ isDownloaded, serverUpdatedAt, lastSyncedAt)
LocalQuestion    — mirrors backend question
LocalOption      — mirrors option (score only, no is_correct; isCorrect computed as score == 5)
LocalUserNote    — stores PKDrawing data per question (local only, never synced)
LocalQuizSession — completed session (score computed locally; not synced to server)
LocalAnswer      — individual answer within a session
```

### `QuizSessionViewModel`

The single ViewModel driving the entire quiz experience:

- **Navigation**: `currentIndex`, `next()`, `previous()`, `goTo(index:)`
- **Answering**: `selectOption(_:for:)` for MCQ/TF; `setEssayText(_:for:)` for essays
- **Drawing notes**: `saveDrawing(_:for:)` — persists `PKDrawing` to `LocalUserNote` via SwiftData
- **Timer**: optional countdown based on `quiz.timeLimit`; auto-submits when it hits zero
- **Scoring**: `calculateScore()` — sums `option.score` for all answered questions. Works uniformly for MCQ (0 or 5) and TKP (1–5) without branching.
- **AI explanations**: `fetchAIExplanation(for:)` — lazy-fetches via `GET /api/v1/questions/{id}/explain`; cached in memory for the session
- **Submit**: packages answers into `LocalQuizSession`, saves to SwiftData for the result screen. Sessions are not uploaded to the server.
- **Reset (retry)**: deletes the saved session from SwiftData so the quiz appears fresh

### `SyncManager`

An `actor` (Swift concurrency-safe):

- `fetchAvailableQuizzes(context:)` — fetches server quiz list; updates `serverUpdatedAt` on locally-downloaded quizzes so the UI can show "update available" badges
- `downloadQuiz(id:context:)` — fetches full quiz + questions + options; upserts into SwiftData

### PencilKit canvas

- Each question has its own `LocalUserNote` with `drawingData: Data` (serialized `PKDrawing`)
- Notes are stored externally via `@Attribute(.externalStorage)` — large binary blobs don't bloat the main SwiftData store
- Notes are **never synced to the server** — they're personal scratch space

---

## 8. Data Models & Schemas

### MongoDB (`quizzes` collection)

```
Quiz {
  id: UUID string
  title: string
  description: string | null
  category: "TWK" | "TIU" | "TKP" | "MIXED"
  time_limit: int | null          // minutes
  is_published: bool
  questions: [                    // fully embedded — no separate collection
    Question {
      id: UUID string
      type: "MCQ" | "TRUE_FALSE" | "ESSAY" | "IMAGE"
      subtype: QuestionSubtype    // see taxonomy below
      content: string
      image_url: string | null
      explanation: string | null
      position: int               // 1-based ordering
      options: [
        QuestionOption {
          id: UUID string
          label: string           // "A"–"E", "True", "False"
          content: string
          score: int              // MCQ/TF: 0 or 5; TKP: 1–5
        }
      ]
      created_at: datetime
    }
  ]
  created_at: datetime
  updated_at: datetime
}
```

### Bulk import JSON format (for `POST /admin/questions/bulk`)

```json
{
  "quiz": {
    "title": "TIU – Silogisme",
    "description": "...",
    "category": "TIU",
    "time_limit": 25
  },
  "questions": [
    {
      "type": "MCQ",
      "subtype": "SILOGISME",
      "content": "Semua X adalah Y. Budi adalah X. ...",
      "explanation": "Ini adalah silogisme kategoris...",
      "position": 1,
      "options": [
        { "label": "A", "content": "...", "score": 0 },
        { "label": "B", "content": "...", "score": 5 },
        { "label": "C", "content": "...", "score": 0 },
        { "label": "D", "content": "...", "score": 0 },
        { "label": "E", "content": "...", "score": 0 }
      ]
    }
  ]
}
```

---

## 9. Question Taxonomy

All 26 question subtypes, organized by category:

### TWK — Tes Wawasan Kebangsaan (8 subtypes)

| Subtype               | Topic                                        |
| --------------------- | -------------------------------------------- |
| `PANCASILA`           | The five principles of Pancasila             |
| `UUD_1945`            | Indonesian constitution articles             |
| `BHINNEKA`            | Bhinneka Tunggal Ika, pluralism              |
| `NKRI`                | Unitary state, regional autonomy, territory  |
| `SEJARAH_NASIONAL`    | Indonesian national history                  |
| `SISTEM_PEMERINTAHAN` | Presidential system, parliament, elections   |
| `BELA_NEGARA`         | National defense, integrity, anti-corruption |
| `BAHASA_INDONESIA`    | Language grammar, vocabulary                 |

### TIU — Tes Intelegensi Umum (9 subtypes)

| Subtype                    | Topic                                          |
| -------------------------- | ---------------------------------------------- |
| `ANALOGI_VERBAL`           | Word pair relationships (A:B = C:?)            |
| `ANALOGI_GAMBAR`           | Visual pattern analogies (image-based)         |
| `SILOGISME`                | Logical syllogisms (two premises → conclusion) |
| `ANTONIM`                  | Antonyms                                       |
| `SINONIM`                  | Synonyms                                       |
| `ARITMATIKA`               | Arithmetic: fractions, percentages, powers     |
| `DERET_ANGKA`              | Number sequences and patterns                  |
| `SOAL_CERITA`              | Word problems / story math                     |
| `PERBANDINGAN_KUANTITATIF` | Column A vs Column B comparisons               |

### TKP — Tes Karakteristik Pribadi (9 subtypes)

| Subtype               | ASN Value Domain                |
| --------------------- | ------------------------------- |
| `PELAYANAN_PUBLIK`    | Public service orientation      |
| `PROFESIONALISME`     | Professionalism                 |
| `JEJARING_KERJA`      | Work networking & collaboration |
| `SOSIAL_BUDAYA`       | Social-cultural awareness       |
| `TEKNOLOGI_INFORMASI` | Technology literacy             |
| `ORIENTASI_BELAJAR`   | Learning orientation            |
| `MENGENDALIKAN_DIRI`  | Self-control                    |
| `BERADAPTASI`         | Adaptability                    |
| `KREATIVITAS_INOVASI` | Creativity & innovation         |

### ML explain behavior by subtype

| Subtype group                                                  | `needs_ml_explain` | Reason                                           |
| -------------------------------------------------------------- | ------------------ | ------------------------------------------------ |
| ANALOGI_GAMBAR                                                 | `false`            | LLM cannot see images; return stored explanation |
| ANTONIM, SINONIM, ANALOGI_VERBAL                               | `false`            | Stored explanation sufficient (direct lookup)    |
| All TKP (9 subtypes)                                           | `false`            | Behavioral questions; stored explanations work   |
| ARITMATIKA, DERET_ANGKA, SOAL_CERITA, PERBANDINGAN_KUANTITATIF | `true`             | LLM explains math method + LaTeX post-processing |
| All TWK (8 subtypes), SILOGISME                                | `true`             | LLM explains civic knowledge / logical reasoning |

---

## 10. Scoring System

### The `score` field (not `is_correct`)

Options do not have a boolean `is_correct` field. Correctness is entirely encoded in the `score` integer. This was a deliberate decision to unify MCQ and TKP scoring:

- **MCQ / TRUE_FALSE / TWK / TIU questions:**
  - Correct option: `score = 5`
  - Wrong options: `score = 0`
  - `isCorrect` can be derived anywhere as `score == 5`

- **TKP questions:**
  - All 5 options have scores in the range 1–5
  - Each score must be distinct (no two options the same)
  - `score = 5` = the most ASN-aligned response
  - `score = 1` = the least appropriate response
  - No option is "wrong" — they reflect varying degrees of appropriateness

### Session scoring

The session score is simply the sum of `option.score` for all selected options. No branching logic needed:

```swift
// iOS (Swift) — scoring is computed locally, not on the server
questions.reduce(0) { total, question in
    guard let answer = answers[question.id],
          let optionId = answer.selectedOptionId,
          let option = question.options.first(where: { $0.id == optionId })
    else { return total }
    return total + option.score
}
```

### Maximum possible score

`number_of_questions × 5` — this works for both MCQ (max 5 per question) and TKP (max 5 per question).

---

## 11. AI Pipeline

### Explanation pipeline (`/explain`)

```
iPad taps "AI Explain"
  → GET /api/v1/questions/{id}/explain (Rust)
  → Check SubtypeConfig.needs_ml_explain
     ├── false → return stored explanation immediately (no ML call)
     └── true  →
          → Build ExplainRequest (question text, options, best option label, subtype)
          → send "explain" verb to ML service (over UDS), with 3 retries (200/400/800ms backoff)
          → ML service:
               1. Embed question → cosine search → top-3 similar examples (RAG)
               2. Build few-shot prompt (3 examples + question)
               3. Call Ollama (gemma4:e4b) → {explanation, tip}
               4. Apply plain_to_latex() if subtype is numeric
               5. Return {explanation, tip}
          → Rust server returns {ai_explanation, ai_tip}
  → iPad shows explanation overlay
```

### Question generation pipeline (non-analogi)

```
Admin picks subtype on /generate page
  → Frontend: pick random question of that subtype from all quizzes
  → POST /admin/questions/generate {source_question_id}
  → Rust: build GenerateRequest from source question
  → send "generate" verb to ML service (over UDS)
  → ML service:
       1. Embed source question → cosine search → up to 5 examples (exclude source)
       2. Build generation prompt with examples + source
       3. Call Ollama → {content, options[{label,content}], correct_label, explanation, tip}
       4. Validate: exactly 5 options, correct_label valid
       [TKP path]
       5a. Extract score per option; validate variety (≥3 distinct); clamp 1–5
       5b. Return with TKP scores
       [Non-TKP path]
       5a. Try direct arithmetic computation from question content
       5b. If answer not in options → REJECT (retry in frontend)
       5c. If non-arithmetic → LLM correction pass (self-correction prompt)
       5d. Python deterministic inference: parse "= X" from explanation
       5e. Assign score=5 to correct, score=0 to others
       6. Return GeneratedQuestion
  → Admin sees preview → Accept (save) or Skip (generate next)
```

### Analogi gambar pipeline

```
Admin picks ANALOGI_GAMBAR on /generate page
  → POST /admin/questions/generate/analogi (no body)
  → Rust: send "analogi" verb to ML service (over UDS)
  → ML service (up to 3 attempts):
       1. Call Ollama with ANALOGI_SPEC_SYSTEM_PROMPT
          → JSON spec with cell_a, cell_b, cell_c, cell_d (each = list of shape objects)
       2. Extract spec from LLM response (handle markdown fences, find first {...})
       3. Normalize spec (coerce types, set defaults)
       4. Validate spec (positions unique per cell, shapes valid, all 4 cells present)
       5. Call analogi_engine.process_no_db(spec):
          a. Generate 4 distractors via auto_distractors_explicit()
          b. Shuffle correct + 4 distractors → 5 options with random labels
          c. Render composite image (A:B=C:?) via Pillow → upload to Rust
          d. Render 5 option cells via Pillow → upload each to Rust
          e. Return {content, image_url, explanation, options[{label, content=img_url, score=0or5}]}
  → Rust passes response back to admin web
  → Admin sees: composite image + 5 option images (correct has green border)
  → Accept or Skip
```

### Analogi spec language

The LLM generates analogi questions using a strict shape DSL:

- **Shapes**: circle, square, triangle, diamond, pentagon, hexagon, star, cross, semicircle, arrow, line, wave
- **Positions**: 3×3 named grid — TL, TC, TR, ML, C, MR, BL, BC, BR
- **Sizes**: small, medium, large
- **Fill**: `true` (solid black) or `false` (outline only)
- **Rotation**: 0, 30, 45, 60, 90, 120, 135, 150, 180 degrees

The LLM is instructed to:

1. Choose a transformation rule (mirror, invert, rotate, swap sizes)
2. Define `cell_a` (initial state)
3. Apply rule mentally → `cell_b`
4. Define `cell_c` (different shapes/positions)
5. Apply same rule → `cell_d` (the correct answer)

Pillow renders each cell as a 240×240px PNG with anti-aliased shapes.

---

## 12. Sync Strategy (iOS ↔ Backend)

### Download (Quiz → iPad)

```
QuizListView appears
  → SyncManager.fetchAvailableQuizzes()
  → GET /api/v1/quizzes (lightweight: no questions embedded)
  → For each quiz already downloaded locally:
       update serverUpdatedAt → UI shows "update available" if newer than lastSyncedAt
  → User taps a quiz to download
  → SyncManager.downloadQuiz(id:)
  → GET /api/v1/quizzes/{id} → full quiz + all questions + options
  → Upsert all into SwiftData (update existing, insert new)
  → Set isDownloaded = true, lastSyncedAt = now
```

Delta sync: `GET /api/v1/quizzes/{id}?since=<ISO_datetime>` returns only questions added/modified after that timestamp. Used for incremental updates.

### Sessions (local only)

Quiz sessions (answers, score, timestamps) are stored in SwiftData on the device and **never uploaded to the server**. The result screen reads from local storage. Sessions exist only for the duration the user keeps them on device.

**Why no server sync:** The purpose of the app is learning — the score is feedback for the student, not a record for the admin. Keeping sessions off the server removes any temptation to expose or manipulate results server-side.

### Conflict resolution

- Backend is source of truth for **questions** (admin edits override)
- iPad is source of truth for **drawings** (never synced)
- iPad is source of truth for **sessions** (local only, never sent to server)

---

## 13. Service Management

The Rust server auto-starts and supervises both Ollama and the Python ML service. This means starting the backend is a single command: `cargo run`.

### How it works

`ServiceManager` is created in `main.rs` when `MANAGE_SERVICES=true` (default). It runs before Axum starts accepting requests:

```rust
if config.manage_services {
    Arc::new(ServiceManager::new(&config))
        .start_and_watch()
        .await;
}
```

`start_and_watch()`:

1. Runs `ensure_ollama()` and `ensure_ml_service()` immediately (non-blocking — Axum starts while services initialize)
2. Spawns a background `tokio::spawn` loop that re-checks every 15 seconds

`ensure_ml_service()` logic:

1. If we hold a child handle and `try_wait()` shows it exited → clear handle → fall through to restart
2. If we hold a running child handle → return (healthy)
3. If no child and `UnixStream::connect(socket_path).ok()` → external instance → return (don't conflict)
4. Remove stale socket file if present (Python's `asyncio.start_unix_server` refuses to bind if it exists)
5. Spawn: `{ml_dir}/.venv/bin/python serve.py` with `current_dir = ml_dir` (serve.py reads `ML_SOCKET_PATH` from env)

**Production note:** On VPS with systemd managing processes, set `MANAGE_SERVICES=false` in `.env`. Systemd handles restarts and logging; the Rust server should stay out of the way.

---

## 14. API Reference

### Authentication

**Not implemented.** All routes are currently open — no token or API key is checked. The `server/src/middleware/auth.rs` file contains JWT and device-key middleware stubs, but they are not wired to any route and reference config fields (`jwt_secret`, `device_api_key`) that don't exist in `Config`. The `login()` function in `admin-web/src/lib/api.ts` and the `Authorization` header interceptor are similarly inoperative.

This is intentional for local/development use. Before exposing the server on a public VPS, authentication should be added (see §16).

### Key request/response shapes

**Quiz list (public)**

```
GET /api/v1/quizzes
→ Array of { id, title, description, category, time_limit, is_published, question_count, created_at, updated_at }
```

**Full quiz (public)**

```
GET /api/v1/quizzes/{id}
→ { quiz: Quiz, questions: Question[] }
Question: { id, quiz_id, type, subtype, content, image_url, explanation, position, created_at, options: Option[] }
Option: { id, question_id, label, content, score }
```

**AI explanation (public)**

```
GET /api/v1/questions/{id}/explain
→ { ai_explanation: string, ai_tip: string }
```

**Bulk import (admin)**

```
POST /api/v1/admin/questions/bulk
Body: { quiz: { title, category, time_limit }, questions: [...] }
→ { quiz_id, questions_imported }
```

**Generate similar question (admin)**

```
POST /api/v1/admin/questions/generate
Body: { source_question_id: UUID }
→ { question: { content, image_url?, options[{label, content, score}], explanation, tip? } }
```

**Generate analogi gambar (admin)**

```
POST /api/v1/admin/questions/generate/analogi
(no body)
→ { question: { content, image_url, options[{label, content(=URL), score}], explanation } }
```

---

## 15. Development Setup

### Prerequisites

- Rust (stable) + `cargo`
- MongoDB (local, port 27017)
- Python 3.11+ with pip
- Ollama (`ollama pull gemma4:e4b`)
- Node.js 20+ (for admin web)
- Xcode 15+ (for iOS app)

### Starting the backend (single command)

```bash
# From server/ directory
cd server
# First time: set absolute ML_SERVICE_DIR (already done in server/.env)
cargo run
# Rust server starts on :3000
# → auto-starts ML service (.venv/bin/python serve.py)
# → auto-starts Ollama (if installed at default path)
```

**Note:** `ML_SERVICE_DIR` must be an absolute path when running from outside `server/`. The `.env` file in `server/` already has the absolute path set.

### Setting up the ML service (first time)

```bash
cd ml-service
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 embed_questions.py   # pre-compute embeddings for RAG
```

### Starting the admin web

```bash
cd admin-web
npm install
npm run dev   # runs on :3001
```

### Importing quiz data

With the Rust server running:

```bash
cd scripts
python3 - <<'EOF'
import json, requests, pathlib
for f in sorted(pathlib.Path(".").glob("*.json")):
    d = json.loads(f.read_text())
    if "quiz" not in d: continue
    r = requests.post("http://localhost:3000/api/v1/admin/questions/bulk", json=d)
    print(f"{'✓' if r.ok else '✗'} {f.name}: {r.json()}")
EOF
```

---

## 16. Key Design Decisions

### 1. Embedded documents in MongoDB (no separate questions collection)

**Decision:** Questions are arrays inside the Quiz document, not a separate `questions` collection.

**Why:** The iPad fetches a quiz + all its questions in a single request. With embedded documents this is one MongoDB read (no join). The admin also always works with questions in the context of their quiz. At current scale (a few thousand questions), document size is not a concern.

**Trade-off:** Queries like "all questions of subtype X across all quizzes" require scanning all quiz documents. The admin question bank page does this in-memory. At 10,000+ questions, a separate collection with an index on `subtype` would perform better.

---

### 2. Score-only options (no `is_correct` field)

**Decision:** `QuestionOption` has only `score: int`, not `is_correct: bool`.

**Why:** TKP questions have weighted scores (1–5) with no single "correct" answer. A boolean `is_correct` doesn't model this. By using `score` everywhere, MCQ and TKP use the exact same code paths:

- Session scoring: `total += option.score` (no branching)
- UI highlighting: `score == 5` means "best" for both types
- Generation output: LLM outputs scores directly; no post-processing to set `is_correct`

---

### 3. UDS instead of TCP for Rust ↔ ML service

**Decision:** Rust talks to the ML service over a Unix Domain Socket, not TCP.

**Why:** No port assignment needed, no firewall rules, no TCP overhead. On the same machine, UDS is faster than loopback TCP and signals clearly that the two processes are co-located. The socket path (`/tmp/lms-ml.sock`) is configured as an env var so it works on both macOS (`/tmp/`) and Linux (`/run/lms/`).

---

### 4. Rust manages ML service lifecycle

**Decision:** The Rust server auto-starts and watchdogs both Ollama and the ML service.

**Why:** Eliminates "which order to start processes" problems in development. The whole backend is one command: `cargo run`. In production, `MANAGE_SERVICES=false` hands control to systemd (proper PID management, logging, restart policy).

---

### 5. Deterministic math verification, not LLM arithmetic

**Decision:** Arithmetic answers are verified by a Python evaluator, not trusted from the LLM.

**Why:** LLMs hallucinate numbers reliably. An LLM might write "3/4 + 5/6 = 2/3" with full confidence. The math parser evaluates using `fractions.Fraction` for exact results and overwrites any wrong values. The LLM's job is to explain the _method_; Python handles the _answer_.

---

### 6. Multi-pass generation with self-correction

**Decision:** Question generation uses up to three passes: initial generation → arithmetic check → LLM correction → Python inference.

**Why:** A single LLM call for question generation produces about 60–70% valid questions for math subtypes. Multiple validation and correction passes increase this to ~95% without requiring a larger/smarter model.

The passes in order:

1. LLM generates question + 5 options + correct_label
2. Direct computation: evaluate the question's math expression, match to option
3. LLM correction: if computation is inconclusive, send the question back for self-correction (minimal edit: fix label or one option content)
4. Python inference: parse the final answer from the explanation text

---

### 7. RAG with pre-computed embeddings

**Decision:** Use 400 pre-computed question embeddings stored as a NumPy array. No vector database.

**Why:** 400 vectors × 384 dimensions × 4 bytes = ~600KB in memory. Cosine search over 400 vectors takes under 1ms. A vector database like Faiss or Pinecone would add a dependency for no practical benefit at this scale. The embedding file is rebuilt by running `python3 embed_questions.py` whenever new questions are added to the RAG store.

---

### 8. iPad-only, landscape, offline-first

**Decision:** Target iPad in landscape orientation. Store everything locally in SwiftData. Sync only on explicit actions (download quiz, complete session).

**Why:** CPNS students often practice without reliable internet (commuting, rural areas). The app must work fully offline. SwiftData provides a SQLite-backed local store with Swift's type system. The landscape layout gives enough space for both the question panel and a handwriting canvas side-by-side.

---

### 9. PencilKit notes are local-only

**Decision:** Drawing notes are stored in SwiftData as binary `PKDrawing` data and never synced to the server.

**Why:** Notes are personal scratch work — not graded, not shared. Syncing binary drawing data would require significant storage and add sync complexity for no benefit. If a student switches devices, they lose their notes — an acceptable trade-off for v1.

---

### 10. Subtype drives everything

**Decision:** `QuestionSubtype` is a single enum that controls prompt selection, math post-processing, AI explanation eligibility, UI form rendering, and generation pipeline routing.

**Why:** The CPNS exam has fundamentally different question types that need different treatment at every layer. Rather than ad-hoc conditionals scattered through the code, routing through `subtype` at every decision point makes the behavior predictable and extensible. Adding a new subtype means updating the enum and its `config()` method — everything else falls out automatically.

---

---

### 11. Raw socket protocol instead of HTTP/FastAPI for ML service

**Decision:** The ML service speaks a custom length-prefix protocol over UDS, not HTTP. No FastAPI, no uvicorn, no Pydantic.

**Why:** The only caller is the Rust server, which has compile-time type safety — Pydantic input validation protects against untrusted external callers that don't exist here. Dropping the ASGI stack removes `fastapi`, `uvicorn`, `starlette`, `pydantic`, `anyio`, and `httpx` from the dependency tree, and removes `hyper`, `hyper-util`, `http-body-util`, and `bytes` from Rust's Cargo.toml. The replacement is ~15 lines of `asyncio.start_unix_server`. The only validation that remains is on LLM output (untrusted by nature) — that logic is unchanged inside the handler functions.

**Protocol:** `"<verb> <byte_len>\n<json>"` → `"ok <byte_len>\n<json>"` or `"error <byte_len>\n<message>"`. Handlers run in `asyncio.to_thread()` so the event loop stays responsive during Ollama's ~30s calls.

---

### 12. Authentication is not implemented (intentional for v1)

**Decision:** All API routes are currently open — no JWT, no device key check.

**Why:** The system runs on a local machine during development and is not yet exposed publicly. Adding auth would require: (a) `jwt_secret` + `device_api_key` fields in `Config`, (b) wiring `middleware::auth::require_admin` to admin routes and `require_device_key` to public routes in `main.rs`, (c) a `POST /api/v1/auth/login` route + admin user collection in MongoDB. The stubs exist in `server/src/middleware/auth.rs` and `admin-web/src/lib/api.ts` but are not active.

**Before going public:** enable auth. The middleware code is written — it just needs config fields and route wiring.

---

_This guide reflects the system as built through the development sessions ending 2026-06-09. Quiz data: 25 JSON files (620 questions), covering TWK (8 subtypes) and TIU (11 subtypes). TKP questions are generated on-demand via AI. Sessions are local-only — not uploaded to the server._
