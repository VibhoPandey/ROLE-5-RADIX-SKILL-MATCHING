# RADIX Talent Match — Role 5: Skill Matching Engine

A production-grade, deterministic, and explainable Skill Matching REST API built with **FastAPI**, **Pydantic v2**, and **Python 3**.

---

## 1. Role and Objective

**Role 5 (Skill Matching)** sits downstream from:
- **Role 1 (JD Analytics)**: Extracts required skills, category breakdowns, and expectations from Job Descriptions.
- **Role 3 (Candidate Profiling / Profile Builder)**: Extracts candidate skills, categories, resume evidence snippets, and confidence levels.

Role 5's responsibility:
1. Validates and normalizes candidate and job data from upstream roles.
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
│   ├── __init__.py                 # Public package exports (matcher & schemas)
│   ├── __main__.py                 # CLI entrypoint (python -m app)
│   ├── cli.py                      # Standalone CLI tool with --role1 and --role3
│   ├── main.py                     # FastAPI application, OpenAPI /docs, error handlers
│   ├── api/
│   │   ├── __init__.py
│   │   └── skill_match.py          # API routes (POST /api/v1/skill-match, /api/v1/role1-role3-match)
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── skill_match.py          # Pydantic v2 schemas & upstream Role 1 / Role 3 adapters
│   └── services/
│       ├── __init__.py
│       ├── normalizer.py           # Text normalization & alias resolution dictionary
│       ├── matcher.py              # Core comparison & explanation engine (match_role1_and_role3)
│       └── scorer.py               # Deterministic match scoring formulas
├── sample_data/
│   ├── role1_job_sample.json       # Real Role 1 JD output fixture (Oracle Application Support)
│   ├── role3_candidate_sample.json # Real Role 3 Candidate output fixture (Priya Menon)
│   ├── role1_role3_request.json    # Combined Role 1 & Role 3 request fixture
│   ├── file_paths_request.json     # File-reference payload fixture
│   ├── combined_request.json       # Legacy combined request sample
│   └── conceptual_request_sample.json # Minimal hackathon specification payload
├── tests/
│   ├── __init__.py
│   └── test_skill_match.py         # 32 unit & integration test cases
├── requirements.txt                # Pinned dependencies
└── README.md
```

---

## 3. Matching Pipeline

```
[Candidate Profile (Role 3)]  +  [Job Requirements (Role 1)]
              │                               │
              ▼                               ▼
       [Input Validation & Upstream Adapters]
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

## 4. Supported Input Formats

Role 5 accepts inputs from **ROLE 1 (JD ANALYTICS)** and **ROLE 3 (CANDIDATE PROFILING)** in multiple flexible ways:

### Format A: Direct Role 1 & Role 3 JSON Payloads
Pass the raw outputs directly under `role1_jd_analytics` and `role3_candidate_profiling` (or shorthand `role1` and `role3`):

```json
{
  "role1_jd_analytics": {
    "file": "Oracle - Application Support Analyst.pdf",
    "company": "Oracle Financial Services Software",
    "role": "Application Support Analyst",
    "skills": [
      {"skill_name": "SQL", "category_code": "SQL", "importance": "required"},
      {"skill_name": "Linux", "category_code": "OS", "importance": "required"},
      {"skill_name": "Networking fundamentals", "category_code": "NETW", "importance": "required"}
    ]
  },
  "role3_candidate_profiling": {
    "source_file": "Priya_Menon.pdf",
    "skills": [
      {
        "skill_name": "SQL",
        "category_code": "SQL",
        "evidence": "SQL (basic), Java, Linux basics",
        "confidence": "high",
        "evidence_verified": true
      },
      {
        "skill_name": "Computer Networks",
        "category_code": "NETW",
        "evidence": "Networking fundamentals",
        "confidence": "high",
        "evidence_verified": true
      }
    ],
    "profile_prefill": {
      "name": "Priya Menon",
      "cv_file": "Priya_Menon.pdf"
    }
  }
}
```

### Format B: File Path References
Provide local JSON file paths generated by Role 1 and Role 3:

```json
{
  "role1_path": "sample_data/role1_job_sample.json",
  "role3_path": "sample_data/role3_candidate_sample.json"
}
```

### Format C: Standard / Conceptual Format
```json
{
  "candidate_profile": {
    "candidate_id": "CAND501",
    "skills": [{"name": "Python"}, {"name": "SQL"}]
  },
  "job_requirements": {
    "job_id": "JOB101",
    "job_title": "Backend Developer",
    "required_skills": [{"name": "Python"}, {"name": "SQL"}, {"name": "Docker"}]
  }
}
```

---

## 5. API Endpoints

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

### `POST /api/v1/skill-match` (and alias `POST /api/v1/role1-role3-match`)
Executes the deterministic matching engine on candidate and job data.

#### Example Response
```json
{
  "candidate_id": "Priya Menon",
  "candidate_name": "Priya Menon",
  "job_id": "oracle_-_application_support_analyst.json",
  "job_title": "Application Support Analyst",
  "company": "Oracle Financial Services Software",
  "match_score": 50.0,
  "total_required_skills": 6,
  "matched_skills_count": 3,
  "matched_skills": [
    "SQL",
    "Linux",
    "Networking fundamentals"
  ],
  "missing_or_unverified_skills": [
    "Aptitude and Problem Solving",
    "Communication",
    "Software Engineering"
  ],
  "additional_candidate_skills": [
    "Java",
    "Excel",
    "Ticketing Tools",
    "MySQL",
    "Troubleshooting and Escalations",
    "Coordination"
  ],
  "skill_details": [
    {
      "skill": "SQL",
      "category_code": "SQL",
      "status": "matched",
      "explanation": "'SQL' is present in the candidate profile under 'technical_skills' (evidence: 'SQL (basic), Java, Linux basics, Networking fundamentals') with high confidence.",
      "candidate_skill_matched": "SQL",
      "confidence": "high",
      "evidence": "SQL (basic), Java, Linux basics, Networking fundamentals",
      "evidence_verified": true
    },
    {
      "skill": "Aptitude and Problem Solving",
      "category_code": "APTI",
      "status": "missing_or_unverified",
      "explanation": "'Aptitude and Problem Solving' was not found in the available candidate profile.",
      "candidate_skill_matched": null,
      "confidence": null,
      "evidence": null,
      "evidence_verified": null
    }
  ],
  "summary": "3 of 6 required skills were found in the candidate profile.",
  "category_summary": {
    "SQL": {"required": 1, "matched": 1},
    "OS": {"required": 1, "matched": 1},
    "NETW": {"required": 1, "matched": 1},
    "APTI": {"required": 1, "matched": 0},
    "COMM": {"required": 1, "matched": 0},
    "SWE": {"required": 1, "matched": 0}
  },
  "role1_file": "oracle_-_application_support_analyst.json",
  "role3_file": "Priya_Menon.pdf"
}
```

---

## 6. CLI Usage

Run the matching engine directly from the command line:

```powershell
# Print concise human-readable summary
python -m app.cli --role1 sample_data/role1_job_sample.json --role3 sample_data/role3_candidate_sample.json --summary

# Output full JSON
python -m app.cli --role1 sample_data/role1_job_sample.json --role3 sample_data/role3_candidate_sample.json

# Save result to a file
python -m app.cli --role1 sample_data/role1_job_sample.json --role3 sample_data/role3_candidate_sample.json -o result.json
```

---

## 7. Python Library Usage

You can also import and use the matcher directly in Python scripts:

```python
from app import match_role1_and_role3

# Pass file paths directly
result = match_role1_and_role3(
    role1_input="sample_data/role1_job_sample.json",
    role3_input="sample_data/role3_candidate_sample.json",
)

print(f"Match Score: {result.match_score}%")
print(f"Matched Skills: {result.matched_skills}")
print(f"Missing Skills: {result.missing_or_unverified_skills}")
```

---

## 8. Local Setup & Execution (Windows PowerShell)

### Prerequisites
- Python 3.10+ (Current environment: Python 3.15)

### 1. Activate Virtual Environment
```powershell
.\.venv\Scripts\Activate.ps1
```

### 2. Install Dependencies
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

## 9. Verification with cURL / PowerShell

```powershell
# Test with Role 1 & Role 3 sample
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/skill-match" `
  -Method POST `
  -Headers @{ "Content-Type" = "application/json" } `
  -InFile "sample_data\role1_role3_request.json" | ConvertTo-Json -Depth 5
```
