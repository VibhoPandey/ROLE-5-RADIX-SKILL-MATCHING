import json
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.skill_match import (
    CandidateProfile,
    CandidateSkill,
    JobRequirements,
    RequiredSkill,
    SkillMatchRequest,
)
from app.services.matcher import match_candidate_to_job, match_role1_and_role3
from app.services.normalizer import normalize_skill_name
from app.services.scorer import calculate_match_score

client = TestClient(app)


# ==============================================================================
# 1. Normalization & Alias Tests
# ==============================================================================

def test_normalization_case_and_whitespace():
    assert normalize_skill_name("  PyThOn   ") == "python"
    assert normalize_skill_name("PostgreSQL") == "postgresql"
    assert normalize_skill_name("  REST   APIs  ") == "rest api"


def test_normalization_known_aliases():
    assert normalize_skill_name("js") == "javascript"
    assert normalize_skill_name("JavaScript") == "javascript"
    assert normalize_skill_name("postgres") == "postgresql"
    assert normalize_skill_name("RESTful API") == "rest api"
    assert normalize_skill_name("REST APIs") == "rest api"
    assert normalize_skill_name("Networking fundamentals") == "computer networks"
    assert normalize_skill_name("k8s") == "kubernetes"
    assert normalize_skill_name("SQL (basic)") == "sql"


def test_normalization_distinguishes_distinct_skills():
    # Git and GitHub are distinct
    assert normalize_skill_name("git") == "git"
    assert normalize_skill_name("github") == "github"
    assert normalize_skill_name("git") != normalize_skill_name("github")

    # Java and JavaScript are distinct
    assert normalize_skill_name("java") == "java"
    assert normalize_skill_name("javascript") == "javascript"
    assert normalize_skill_name("java") != normalize_skill_name("javascript")


# ==============================================================================
# 2. Scorer Unit Tests
# ==============================================================================

def test_scorer_all_match():
    reqs = [
        RequiredSkill(name="Python"),
        RequiredSkill(name="SQL"),
        RequiredSkill(name="Git"),
    ]
    matched = {"Python", "SQL", "Git"}
    assert calculate_match_score(reqs, matched) == 100.0


def test_scorer_none_match():
    reqs = [
        RequiredSkill(name="Python"),
        RequiredSkill(name="SQL"),
    ]
    matched = set()
    assert calculate_match_score(reqs, matched) == 0.0


def test_scorer_partial_match():
    # 3 out of 4 = 75.0%
    reqs = [
        RequiredSkill(name="Python"),
        RequiredSkill(name="SQL"),
        RequiredSkill(name="REST APIs"),
        RequiredSkill(name="Git"),
    ]
    matched = {"Python", "SQL", "Git"}
    assert calculate_match_score(reqs, matched) == 75.0


def test_scorer_empty_requirements():
    # Zero division guard
    assert calculate_match_score([], set()) == 0.0


def test_scorer_weighted_match():
    # Skill 1 (weight 3.0), Skill 2 (weight 1.0) -> Total weight = 4.0
    # If Skill 1 matches: 3.0 / 4.0 = 75.0%
    reqs = [
        RequiredSkill(name="Python", weight=3.0),
        RequiredSkill(name="Docker", weight=1.0),
    ]
    matched = {"Python"}
    assert calculate_match_score(reqs, matched) == 75.0


# ==============================================================================
# 3. Matching Service Core Logic Tests
# ==============================================================================

def test_matching_all_skills_match():
    profile = CandidateProfile(
        candidate_id="CAND1",
        skills=[CandidateSkill(name="Python"), CandidateSkill(name="SQL")],
    )
    job = JobRequirements(
        job_id="JOB1",
        job_title="Backend Dev",
        required_skills=[RequiredSkill(name="Python"), RequiredSkill(name="SQL")],
    )
    result = match_candidate_to_job(profile, job)
    assert result.match_score == 100.0
    assert result.matched_skills_count == 2
    assert set(result.matched_skills) == {"Python", "SQL"}
    assert result.missing_or_unverified_skills == []
    assert result.summary == "2 of 2 required skills were found in the candidate profile."


def test_matching_no_skills_match():
    profile = CandidateProfile(
        candidate_id="CAND1",
        skills=[CandidateSkill(name="Ruby"), CandidateSkill(name="Rails")],
    )
    job = JobRequirements(
        job_id="JOB1",
        job_title="Python Dev",
        required_skills=[RequiredSkill(name="Python"), RequiredSkill(name="FastAPI")],
    )
    result = match_candidate_to_job(profile, job)
    assert result.match_score == 0.0
    assert result.matched_skills_count == 0
    assert result.matched_skills == []
    assert set(result.missing_or_unverified_skills) == {"Python", "FastAPI"}
    assert result.additional_candidate_skills == ["Ruby", "Rails"]


def test_matching_case_insensitivity_and_alias():
    profile = CandidateProfile(
        candidate_id="CAND1",
        skills=[
            CandidateSkill(name="postgres"),
            CandidateSkill(name="RESTful API"),
            CandidateSkill(name="JS"),
        ],
    )
    job = JobRequirements(
        job_id="JOB1",
        job_title="Fullstack",
        required_skills=[
            RequiredSkill(name="PostgreSQL"),
            RequiredSkill(name="REST APIs"),
            RequiredSkill(name="JavaScript"),
        ],
    )
    result = match_candidate_to_job(profile, job)
    assert result.match_score == 100.0
    assert len(result.matched_skills) == 3


def test_matching_duplicate_skills_deduplication():
    # Duplicate skills in job requirement and candidate profile
    profile = CandidateProfile(
        candidate_id="CAND1",
        skills=[
            CandidateSkill(name="Python", confidence="low"),
            CandidateSkill(name="Python", confidence="high", evidence="5 years experience", evidence_verified=True),
        ],
    )
    job = JobRequirements(
        job_id="JOB1",
        job_title="Python Engineer",
        required_skills=[
            RequiredSkill(name="Python"),
            RequiredSkill(name="python"),
            RequiredSkill(name="PYTHON"),
        ],
    )
    result = match_candidate_to_job(profile, job)
    # Total unique required skills is 1
    assert result.total_required_skills == 1
    assert result.matched_skills_count == 1
    assert result.match_score == 100.0
    # Explanation retains higher confidence evidence
    assert "high confidence" in result.skill_details[0].explanation


def test_matching_empty_candidate_skills():
    profile = CandidateProfile(candidate_id="CAND1", skills=[])
    job = JobRequirements(
        job_id="JOB1",
        job_title="Dev",
        required_skills=[RequiredSkill(name="Python")],
    )
    result = match_candidate_to_job(profile, job)
    assert result.match_score == 0.0
    assert result.total_required_skills == 1
    assert result.matched_skills_count == 0
    assert result.missing_or_unverified_skills == ["Python"]


def test_matching_empty_job_requirements():
    profile = CandidateProfile(
        candidate_id="CAND1",
        skills=[CandidateSkill(name="Python")],
    )
    job = JobRequirements(
        job_id="JOB1",
        job_title="Open Role",
        required_skills=[],
    )
    result = match_candidate_to_job(profile, job)
    assert result.match_score == 0.0
    assert result.total_required_skills == 0
    assert result.matched_skills_count == 0
    assert result.summary == "No required skills were specified in the job requirements."


def test_consistency_across_all_fields():
    profile = CandidateProfile(
        candidate_id="CAND1",
        skills=[
            CandidateSkill(name="Python"),
            CandidateSkill(name="Docker"),
            CandidateSkill(name="GraphQL"),
        ],
    )
    job = JobRequirements(
        job_id="JOB1",
        job_title="Backend",
        required_skills=[
            RequiredSkill(name="Python"),
            RequiredSkill(name="Kubernetes"),
            RequiredSkill(name="Docker"),
        ],
    )
    result = match_candidate_to_job(profile, job)

    # 1. Score consistency: 2 of 3 matched = 66.67%
    assert result.match_score == 66.67
    assert result.matched_skills_count == len(result.matched_skills)
    assert result.total_required_skills == len(result.skill_details)

    # 2. Lists match detail statuses
    matched_detail_names = [d.skill for d in result.skill_details if d.status == "matched"]
    missing_detail_names = [d.skill for d in result.skill_details if d.status == "missing_or_unverified"]

    assert result.matched_skills == matched_detail_names
    assert result.missing_or_unverified_skills == missing_detail_names

    # 3. Additional candidate skills
    assert result.additional_candidate_skills == ["GraphQL"]

    # 4. Summary string consistency
    expected_summary = f"{result.matched_skills_count} of {result.total_required_skills} required skills were found in the candidate profile."
    assert result.summary == expected_summary


# ==============================================================================
# 4. API HTTP Integration Tests
# ==============================================================================

def test_api_root():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "running"
    assert "/health" in data["endpoints"]["health"]


def test_api_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "service": "radix-role5",
        "version": "1.0.0",
    }


def test_api_skill_match_conceptual_payload():
    payload = {
        "candidate_profile": {
            "candidate_id": "CAND501",
            "skills": [
                {"name": "Python"},
                {"name": "SQL"},
                {"name": "Git"},
            ],
        },
        "job_requirements": {
            "job_id": "JOB101",
            "job_title": "Backend Developer",
            "required_skills": [
                {"name": "Python"},
                {"name": "SQL"},
                {"name": "REST APIs"},
                {"name": "Git"},
            ],
        },
    }
    response = client.post("/api/v1/skill-match", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["candidate_id"] == "CAND501"
    assert data["job_id"] == "JOB101"
    assert data["match_score"] == 75.0
    assert data["matched_skills"] == ["Python", "SQL", "Git"]
    assert data["missing_or_unverified_skills"] == ["REST APIs"]
    assert data["summary"] == "3 of 4 required skills were found in the candidate profile."


def test_api_skill_match_role1_and_role3_real_structures():
    # Real structure from Role 3 (Priya Menon) and Role 1 (Oracle Application Support Analyst)
    with open("sample_data/role3_candidate_sample.json", "r") as f:
        candidate_data = json.load(f)

    with open("sample_data/role1_job_sample.json", "r") as f:
        job_data = json.load(f)

    payload = {
        "candidate_profile": candidate_data,
        "job_requirements": job_data,
    }

    response = client.post("/api/v1/skill-match", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["candidate_id"] == "Priya Menon"
    assert data["job_id"] == "oracle_-_application_support_analyst.json"
    assert data["job_title"] == "Application Support Analyst"
    assert data["company"] == "Oracle Financial Services Software"

    # Priya has SQL, Linux, Networking fundamentals (via Computer Networks)
    assert "SQL" in data["matched_skills"]
    assert "Linux" in data["matched_skills"]
    assert "Networking fundamentals" in data["matched_skills"]

    # Factual explanations must not assume mastery or lack thereof
    for detail in data["skill_details"]:
        if detail["status"] == "matched":
            assert "is present in the candidate profile" in detail["explanation"]
        else:
            assert "was not found in the available candidate profile" in detail["explanation"]


def test_api_rejects_missing_candidate_profile():
    payload = {
        "job_requirements": {
            "job_id": "JOB101",
            "job_title": "Backend",
            "required_skills": [{"name": "Python"}],
        }
    }
    response = client.post("/api/v1/skill-match", json=payload)
    assert response.status_code == 422
    assert "candidate_profile" in response.text


def test_api_rejects_missing_job_requirements():
    payload = {
        "candidate_profile": {
            "candidate_id": "CAND1",
            "skills": [{"name": "Python"}],
        }
    }
    response = client.post("/api/v1/skill-match", json=payload)
    assert response.status_code == 422
    assert "job_requirements" in response.text


def test_api_rejects_malformed_skill_objects():
    # Skill name is an empty string
    payload = {
        "candidate_profile": {
            "candidate_id": "CAND1",
            "skills": [{"name": "   "}],
        },
        "job_requirements": {
            "job_id": "JOB101",
            "job_title": "Backend",
            "required_skills": [{"name": "Python"}],
        },
    }
    response = client.post("/api/v1/skill-match", json=payload)
    assert response.status_code == 422


def test_api_rejects_invalid_weights():
    # Negative weight should fail validation
    payload = {
        "candidate_profile": {
            "candidate_id": "CAND1",
            "skills": [{"name": "Python"}],
        },
        "job_requirements": {
            "job_id": "JOB101",
            "job_title": "Backend",
            "required_skills": [{"name": "Python", "weight": -5.0}],
        },
    }
    response = client.post("/api/v1/skill-match", json=payload)
    assert response.status_code == 422



# ==============================================================================
# 5. Role 1 & Role 3 Integration Tests
# ==============================================================================

def test_api_with_role1_jd_analytics_and_role3_candidate_profiling_keys():
    with open("sample_data/role1_job_sample.json", "r") as f:
        role1_data = json.load(f)
    with open("sample_data/role3_candidate_sample.json", "r") as f:
        role3_data = json.load(f)

    payload = {
        "role1_jd_analytics": role1_data,
        "role3_candidate_profiling": role3_data,
    }
    response = client.post("/api/v1/skill-match", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["candidate_id"] == "Priya Menon"
    assert data["job_title"] == "Application Support Analyst"
    assert "SQL" in data["matched_skills"]


def test_api_with_role1_and_role3_short_keys():
    with open("sample_data/role1_job_sample.json", "r") as f:
        role1_data = json.load(f)
    with open("sample_data/role3_candidate_sample.json", "r") as f:
        role3_data = json.load(f)

    payload = {
        "role1": role1_data,
        "role3": role3_data,
    }
    response = client.post("/api/v1/skill-match", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["candidate_id"] == "Priya Menon"
    assert data["job_title"] == "Application Support Analyst"


def test_api_with_file_path_inputs():
    payload = {
        "role1_path": "sample_data/role1_job_sample.json",
        "role3_path": "sample_data/role3_candidate_sample.json",
    }
    response = client.post("/api/v1/skill-match", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["candidate_id"] == "Priya Menon"
    assert data["job_title"] == "Application Support Analyst"
    assert data["match_score"] == 50.0


def test_api_alias_endpoint_role1_role3_match():
    payload = {
        "role1_path": "sample_data/role1_job_sample.json",
        "role3_path": "sample_data/role3_candidate_sample.json",
    }
    response = client.post("/api/v1/role1-role3-match", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["candidate_id"] == "Priya Menon"
    assert data["job_title"] == "Application Support Analyst"


def test_match_role1_and_role3_python_function_with_paths():
    res = match_role1_and_role3(
        role1_input="sample_data/role1_job_sample.json",
        role3_input="sample_data/role3_candidate_sample.json",
    )
    assert res.candidate_id == "Priya Menon"
    assert res.job_title == "Application Support Analyst"
    assert res.match_score == 50.0
    assert "SQL" in res.matched_skills
    assert "Linux" in res.matched_skills
    assert "Networking fundamentals" in res.matched_skills


def test_match_role1_and_role3_python_function_with_dicts():
    with open("sample_data/role1_job_sample.json", "r") as f:
        r1 = json.load(f)
    with open("sample_data/role3_candidate_sample.json", "r") as f:
        r3 = json.load(f)

    res = match_role1_and_role3(r1, r3)
    assert res.candidate_id == "Priya Menon"
    assert res.matched_skills_count == 3


def test_match_candidate_to_job_with_raw_dicts():
    cand_dict = {
        "candidate_id": "CAND_DICT_1",
        "skills": [{"name": "Python"}, {"name": "SQL"}],
    }
    job_dict = {
        "job_id": "JOB_DICT_1",
        "job_title": "Data Analyst",
        "required_skills": [{"name": "Python"}, {"name": "SQL"}, {"name": "Tableau"}],
    }
    res = match_candidate_to_job(cand_dict, job_dict)
    assert res.candidate_id == "CAND_DICT_1"
    assert res.matched_skills_count == 2
    assert res.total_required_skills == 3
    assert res.match_score == 66.67


def test_flexible_schema_variations():
    # Test handling integer IDs, fullName, and must_have_skills
    cand_data = {
        "id": 999,
        "fullName": "Alex Smith",
        "skills": ["Python", "FastAPI"],
    }
    job_data = {
        "id": 888,
        "title": "Backend Engineer",
        "must_have_skills": ["Python"],
        "good_to_have_skills": ["FastAPI", "Docker"],
    }
    req = SkillMatchRequest.model_validate({"candidate": cand_data, "job": job_data})
    assert req.candidate_profile.candidate_id == "999"
    assert req.candidate_profile.candidate_name == "Alex Smith"
    assert req.job_requirements.job_id == "888"
    assert req.job_requirements.job_title == "Backend Engineer"
    assert len(req.job_requirements.required_skills) == 3


def test_cli_execution():
    from app.cli import main
    import sys
    orig_argv = sys.argv
    try:
        sys.argv = [
            "cli.py",
            "--role1", "sample_data/role1_job_sample.json",
            "--role3", "sample_data/role3_candidate_sample.json",
            "--summary",
        ]
        # Calling main shouldn't raise any unhandled exception
        main()
    finally:
        sys.argv = orig_argv
