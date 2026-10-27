<<<<<<< HEAD
# RADIX Talent Match — Role 5: Skill Matching Engine

A production-grade, deterministic, and explainable Skill Matching REST API built with **FastAPI**, **Pydantic v2**, and **Python 3**.

---

## 1. Role and Objective

**Role 5 (Skill Matching)** sits downstream from:
- **Role 1 (JD Analytics)**: Extracts required skills, category breakdowns, and expectations from Job Descriptions.
- **Role 3 (Profile Builder)**: Extracts candidate skills, categories, resume evidence snippets, and confidence levels.

Role 5's responsibility:
1. Validates and normalizes candidate and job data.
2. Compares candidate skills against job requirements deterministically.
3. Computes a reproducible match score.
4. Categorizes skills into `matched`, `missing_or_unverified`, and `additional_candidate_skills`.
5. Returns factual, audit-ready JSON explanations suitable for frontend rendering and downstream modules.

> **Zero External Dependencies at Runtime**: No LLMs, external APIs, or Supabase required for core matching. Runs completely offline and deterministically.

---

## 2. Project Architecture

```
radix-role5/
├── app/
│   ├── __init__.py
│   ├── main.py                     # FastAPI application, OpenAPI /docs, error handlers
│   ├── api/
│   │   ├── __init__.py
│   │   └── skill_match.py          # API route definitions (POST /api/v1/skill-match)
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── skill_match.py          # Pydantic v2 schemas & upstream adapters
│   └── services/
│       ├── __init__.py
│       ├── normalizer.py           # Text normalization & alias resolution dictionary
│       ├── matcher.py              # Core comparison & explanation engine
│       └── scorer.py               # Deterministic match scoring formulas
├── sample_data/
│   ├── role1_job_sample.json       # Real Role 1 JD output fixture (Oracle Application Support)
│   ├── role3_candidate_sample.json # Real Role 3 Candidate output fixture (Priya Menon)
│   └── conceptual_request_sample.json # Minimal hackathon specification payload
├── tests/
│   ├── __init__.py
│   └── test_skill_match.py         # 23 unit & integration test cases
├── requirements.txt                # Pinned dependencies
└── README.md
```

---

## 3. Matching Pipeline

```
[Candidate Profile (Role 3)]  +  [Job Requirements (Role 1)]
              │                               │
              ▼                               ▼
       [Input Validation & Schema Normalization]
              │
              ▼
    [Skill Normalization] ──> Lowercase, trim, strip parens, apply ALIAS_MAP
              │
              ▼
   [Requirement Deduplication] ──> Deduplicates JD skills by normalized key
              │
              ▼
    [Skill Comparison] ──> Classifies into:
                           - Matched (with candidate evidence & confidence)
                           - Missing or Unverified (factual phrasing)
                           - Additional Candidate Skills
              │
              ▼
    [Scoring Engine] ──> (Matched Unique Skills / Total Unique Skills) × 100
                         (Supports optional importance weights)
              │
              ▼
    [Response Assembly] ──> Consistent, non-contradicting JSON output
```

### Deterministic Scoring Formula
```
Match Score = (Number of Matched Required Skills / Total Number of Unique Required Skills) × 100
```
- Deduplicated: Repeated requirements in JD do not bias the score.
- Zero Division Guard: If total required skills is 0, score is strictly `0.0%`.
- Rounded to 2 decimal places.
- Weighted scoring supported if `weight` or `importance: preferred` is specified.

---

## 4. API Endpoints

### `GET /`
Returns service status, version, and endpoint sitemap.

### `GET /health`
Returns system health check:
```json
{
  "status": "healthy",
  "service": "radix-role5",
  "version": "1.0.0"
}
```

### `POST /api/v1/skill-match`
Accepts either:
1. **Real Role 1 & Role 3 formats** (with `profile_prefill`, `evidence`, `category_code`, `confidence`).
2. **Simplified hackathon format** (`candidate_id`, `job_id`, `skills`, `required_skills`).

#### Example Request (Simplified Format)
```json
{
  "candidate_profile": {
    "candidate_id": "CAND501",
    "skills": [
      {"name": "Python"},
      {"name": "SQL"},
      {"name": "Git"}
    ]
  },
  "job_requirements": {
    "job_id": "JOB101",
    "job_title": "Backend Developer",
    "required_skills": [
      {"name": "Python"},
      {"name": "SQL"},
      {"name": "REST APIs"},
      {"name": "Git"}
    ]
  }
}
```

#### Example Response
```json
{
  "candidate_id": "CAND501",
  "candidate_name": null,
  "job_id": "JOB101",
  "job_title": "Backend Developer",
  "company": null,
  "match_score": 75.0,
  "total_required_skills": 4,
  "matched_skills_count": 3,
  "matched_skills": [
    "Python",
    "SQL",
    "Git"
  ],
  "missing_or_unverified_skills": [
    "REST APIs"
  ],
  "additional_candidate_skills": [],
  "skill_details": [
    {
      "skill": "Python",
      "category_code": null,
      "status": "matched",
      "explanation": "'Python' is present in the candidate profile.",
      "candidate_skill_matched": "Python",
      "confidence": null,
      "evidence": null,
      "evidence_verified": null
    },
    {
      "skill": "SQL",
      "category_code": null,
      "status": "matched",
      "explanation": "'SQL' is present in the candidate profile.",
      "candidate_skill_matched": "SQL",
      "confidence": null,
      "evidence": null,
      "evidence_verified": null
    },
    {
      "skill": "REST APIs",
      "category_code": null,
      "status": "missing_or_unverified",
      "explanation": "'REST APIs' was not found in the available candidate profile.",
      "candidate_skill_matched": null,
      "confidence": null,
      "evidence": null,
      "evidence_verified": null
    },
    {
      "skill": "Git",
      "category_code": null,
      "status": "matched",
      "explanation": "'Git' is present in the candidate profile.",
      "candidate_skill_matched": "Git",
      "confidence": null,
      "evidence": null,
      "evidence_verified": null
    }
  ],
  "summary": "3 of 4 required skills were found in the candidate profile.",
  "category_summary": null
}
```

---

## 5. Local Setup & Execution (Windows PowerShell)

### Prerequisites
- Python 3.10+ (Current environment: Python 3.15.2)

### 1. Activate Virtual Environment
```powershell
.\.venv\Scripts\Activate.ps1
```

### 2. Install Dependencies (if not already installed)
```powershell
pip install -r requirements.txt
```

### 3. Run the Development Server
```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
- Interactive Swagger UI: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- Interactive ReDoc: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)
- Health Endpoint: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)

### 4. Run Pytest Suite
```powershell
.\.venv\Scripts\pytest.exe -v
```

---

## 6. Verification with cURL / PowerShell

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/skill-match" `
  -Method POST `
  -Headers @{ "Content-Type" = "application/json" } `
  -InFile "sample_data\conceptual_request_sample.json" | ConvertTo-Json -Depth 5
```

=======
# ROLE-5-RADIX-SKILL-MATCHING
RADIX Talent Match Hackathon — Role 5: Skill Matching API built with Python and FastAPI.
>>>>>>> origin/main
