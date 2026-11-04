# Synapse

Synapse is a full-stack code intelligence platform that clones Git repositories and extracts deep structural metadata and multi-language Abstract Syntax Tree (AST) symbols without executing untrusted repository code.

---

## Features

- **Safe & Isolated Shallow Cloning**:
  - Validates and sanitizes repository URLs to prevent CLI flag or argument injection.
  - Generates isolated workspace directories per job (`./cloned_repos/{job_id}`) to prevent race conditions during concurrent clones.
  - Executes non-blocking Git operations asynchronously via `asyncio.to_thread`.
  - Performs shallow cloning (`depth=1` by default) for high-speed indexing.
  - Masks and redacts sensitive credentials and tokens from logs and error responses.

- **Repository Metadata Extraction**:
  - File statistics: total file counts, directory counts, blank lines, code lines, and total lines of code (LOC).
  - Language breakdown: identifies 25+ programming and markup languages, with LOC and percentage distribution.
  - Dependency detection: parses manifests including `package.json` (npm direct/dev/peer dependencies), `requirements.txt` (pip dependencies and version constraints), and `pyproject.toml` (PEP 621 and Poetry specifications).
  - Git repository introspection: extracts default and active branches, latest commit author, hash, timestamp, commit message, and README presence.
  - Safe traversal: enforces filesystem ancestry checks to prevent symlink traversal outside repository boundaries.

- **Tree-sitter AST Symbol Parsing**:
  - Traverses Abstract Syntax Trees (ASTs) across **Python, JavaScript, TypeScript, TSX, Java, Go, Rust, and C++**.
  - Extracts declared entities: functions, classes, methods, imports, exports, and parameter lists with 1-based start and end line numbers.
  - Resilient syntax handling: tolerates syntax errors in source files without failing the overall analysis pipeline.
  - Pure static analysis: **never executes or imports repository code**.

- **Interactive Overview Dashboard**:
  - Enhanced React UI displaying real-time metrics: files, lines of code, AST symbols, manifest count, and language distribution badges.

---

## Project Structure

```text
Synapse/
├── backend/
│   ├── app/
│   │   ├── cloner.py        # Safe GitManager with async execution & isolation
│   │   ├── metadata.py      # Structural, linguistic & dependency extractor
│   │   ├── parser.py        # Tree-sitter multi-language AST engine
│   │   ├── schemas.py       # Pydantic v2 data models & response schemas
│   │   └── __init__.py
│   ├── tests/
│   │   ├── conftest.py      # Temporary repository fixtures & mocks
│   │   ├── test_cloner.py   # Unit tests for URL validation & cloner isolation
│   │   ├── test_metadata.py # Tests for LOC, languages, and dependencies
│   │   ├── test_parser.py   # Multi-language AST extraction test suite
│   │   └── test_api.py      # Endpoint integration & regression tests
│   ├── main.py              # FastAPI application & REST routing
│   ├── requirements.txt     # Backend Python dependencies
│   └── Dockerfile
├── synapse-frontend/
│   ├── src/
│   │   ├── App.jsx          # React UI with metrics and language badges
│   │   ├── App.css          # UI styles for dashboard overview
│   │   └── main.jsx
│   ├── package.json
│   └── Dockerfile
├── docker-compose.yml       # Multi-container orchestration
└── README.md
```

---

## Tech Stack

- **Backend**: Python 3.11+, FastAPI, Uvicorn, Pydantic v2, GitPython
- **Code Analysis**: Tree-sitter (`tree-sitter-python`, `tree-sitter-javascript`, `tree-sitter-typescript`, `tree-sitter-java`, `tree-sitter-cpp`, `tree-sitter-go`, `tree-sitter-rust`)
- **Frontend**: React 19, Vite 8, CSS3
- **Testing**: pytest

---

## Prerequisites

- Python 3.11+
- Node.js 18+
- Git CLI installed and available on system PATH

---

## Setup & Running

### Option 1: Native Setup

#### 1. Backend

```bash
cd backend
python -m venv .venv

# On Linux / macOS / Git Bash:
source .venv/bin/activate
# On Windows PowerShell:
.venv\Scripts\Activate.ps1

pip install -r requirements.txt
uvicorn main:app --reload
```

The API will be available at `http://127.0.0.1:8000`. Interactive OpenAPI documentation is accessible at `http://127.0.0.1:8000/docs`.

#### 2. Frontend

```bash
cd synapse-frontend
npm install
npm run dev
```

The frontend will run at `http://localhost:5173`.

### Option 2: Docker Setup

Run both services with Docker Compose:

```bash
docker-compose up --build
```

- Backend API: `http://localhost:8000`
- Frontend UI: `http://localhost:5173`

---

## API Reference

### 1. `POST /clone`
Clones the repository and returns an initial indexing summary. Preserves 100% backward compatibility with legacy clients.

**Request Body**:
```json
{
  "url": "https://github.com/hasini-06/Synapse.git",
  "depth": 1,
  "parse_ast": true
}
```

**Success Response (200 OK)**:
```json
{
  "message": "Successfully cloned the repository.",
  "job_id": "4a71b2d3e5f6",
  "repo_name": "Synapse",
  "symbols_count": 137,
  "metadata": {
    "repo_info": {
      "name": "Synapse",
      "current_branch": "main",
      "default_branch": "main",
      "has_readme": true,
      "readme_path": "README.md"
    },
    "stats": {
      "total_files": 32,
      "total_directories": 6,
      "total_lines": 2840,
      "total_code_lines": 2410,
      "total_blank_lines": 430,
      "language_distribution": {
        "Python": { "files": 7, "lines": 1420, "percentage": 50.0 },
        "JavaScript": { "files": 8, "lines": 890, "percentage": 31.34 }
      }
    }
  }
}
```

### 2. `POST /analyze`
Executes the complete analysis pipeline (clone, metadata extraction, AST parsing) and returns the full structured AST symbols alongside repository metrics.

### 3. `GET /jobs/{job_id}/metadata`
Retrieves repository metadata for a previously processed job.

### 4. `GET /jobs/{job_id}/ast`
Queries extracted AST symbols with optional filtering.

**Query Parameters**:
- `language`: e.g. `python`, `javascript`, `typescript`, `go`, `rust`, `java`, `cpp`
- `type`: e.g. `function`, `class`, `method`, `import`, `export`

**Sample Output**:
```json
{
  "job_id": "4a71b2d3e5f6",
  "total_symbols": 2,
  "symbols": [
    {
      "name": "DataProcessor",
      "type": "class",
      "file_path": "backend/app/service.py",
      "start_line": 5,
      "end_line": 18,
      "language": "python"
    },
    {
      "name": "DataProcessor.process_item",
      "type": "method",
      "file_path": "backend/app/service.py",
      "start_line": 7,
      "end_line": 12,
      "parameters": ["item_id: int", "flag: bool = True"],
      "language": "python"
    }
  ]
}
```

---

## Running the Automated Test Suite

The test suite covers unit tests and integration tests for cloning, URL validation, metadata parsing, AST symbol extraction, and API route behaviors.

```bash
cd backend
pytest -v
```

---

## Limitations & Honest Notes

- **Private Repositories**: Cloning authenticated private repositories requires supplying credentials in the Git URL or pre-configuring SSH keys on the host machine.
- **File Size Cap**: Source files larger than 1 MB are skipped during AST parsing to prevent memory spikes on large generated bundles.
- **Grammar Coverage**: Tree-sitter grammars are loaded for 8 primary languages (Python, JS, TS, TSX, Java, Go, Rust, C++). Unsupported languages fall back to file count and line metric analysis without failing the rest of the repository.
- **In-Memory Job Storage**: Analyzed jobs are temporarily cached in-memory. In a distributed multi-worker production setup, this can be transitioned to Redis or PostgreSQL.
