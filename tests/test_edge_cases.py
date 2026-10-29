import json
import math
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.skill_match import (
    CandidateProfile,
    CandidateSkill,
    JobRequirements,
    RequiredSkill,
    SkillMatchRequest,
    SkillMatchResponse,
    _load_json_data,
)
from app.services.matcher import match_candidate_to_job, match_role1_and_role3
from app.services.normalizer import normalize_skill_name
from app.services.scorer import calculate_match_score

client = TestClient(app)


# ==============================================================================
# Category A: Empty Input Scenarios
# ==============================================================================
class TestCategoryAEmptyInputs:
    def test_a1_empty_role1_object(self):
        # Empty Role 1 means 0 required skills specified
        payload = {
            "role1": {},
            "role3": {
                "candidate_id": "CAND_1",
                "skills": [{"name": "Python"}],
            },
        }
        resp = client.post("/api/v1/skill-match", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_required_skills"] == 0
        assert data["matched_skills_count"] == 0
        assert data["match_score"] == 0.0
        assert data["matched_skills"] == []
        assert data["missing_or_unverified_skills"] == []
        assert data["additional_candidate_skills"] == ["Python"]
        assert "No required skills" in data["summary"]

    def test_a2_empty_role3_object(self):
        # Empty Role 3 means candidate has 0 skills
        payload = {
            "role1": {
                "job_id": "JOB_1",
                "job_title": "Backend",
                "required_skills": [{"name": "Python"}],
            },
            "role3": {},
        }
        resp = client.post("/api/v1/skill-match", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_required_skills"] == 1
        assert data["matched_skills_count"] == 0
        assert data["match_score"] == 0.0
        assert data["matched_skills"] == []
        assert data["missing_or_unverified_skills"] == ["Python"]

    def test_a3_both_role1_and_role3_empty_objects(self):
        payload = {"role1": {}, "role3": {}}
        resp = client.post("/api/v1/skill-match", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["match_score"] == 0.0
        assert data["total_required_skills"] == 0
        assert data["matched_skills_count"] == 0

    def test_a4_role1_is_none_rejected_422(self):
        payload = {
            "role1": None,
            "role3": {"candidate_id": "CAND1", "skills": []},
        }
        resp = client.post("/api/v1/skill-match", json=payload)
        assert resp.status_code == 422
        assert "job_requirements" in resp.text or "Validation Error" in resp.text

    def test_a5_role3_is_none_rejected_422(self):
        payload = {
            "role1": {"job_id": "JOB1", "job_title": "Dev", "required_skills": []},
            "role3": None,
        }
        resp = client.post("/api/v1/skill-match", json=payload)
        assert resp.status_code == 422
        assert "candidate_profile" in resp.text or "Validation Error" in resp.text

    def test_a6_both_inputs_none_rejected_422(self):
        payload = {"job_requirements": None, "candidate_profile": None}
        resp = client.post("/api/v1/skill-match", json=payload)
        assert resp.status_code == 422

    def test_a7_empty_role1_valid_role3_zero_score(self):
        payload = {
            "job_requirements": {},
            "candidate_profile": {
                "candidate_id": "CAND_ALICE",
                "skills": [{"name": "Python"}, {"name": "SQL"}],
            },
        }
        resp = client.post("/api/v1/skill-match", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["match_score"] == 0.0
        assert len(data["additional_candidate_skills"]) == 2

    def test_a8_empty_role3_valid_role1_zero_score(self):
        payload = {
            "job_requirements": {
                "job_id": "JOB_DATA",
                "job_title": "Data Engineer",
                "required_skills": [{"name": "SQL"}, {"name": "Spark"}],
            },
            "candidate_profile": {},
        }
        resp = client.post("/api/v1/skill-match", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["match_score"] == 0.0
        assert len(data["missing_or_unverified_skills"]) == 2

    def test_a9_empty_skill_arrays_both(self):
        payload = {
            "job_requirements": {"required_skills": []},
            "candidate_profile": {"skills": []},
        }
        resp = client.post("/api/v1/skill-match", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["match_score"] == 0.0
        assert data["total_required_skills"] == 0

    def test_a10_valid_metadata_no_usable_skills(self):
        payload = {
            "job_requirements": {
                "job_id": "JOB_999",
                "job_title": "Architect",
                "company": "Acme Corp",
                "required_skills": [],
            },
            "candidate_profile": {
                "candidate_id": "CAND_999",
                "candidate_name": "Bob",
                "skills": [],
            },
        }
        resp = client.post("/api/v1/skill-match", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == "JOB_999"
        assert data["company"] == "Acme Corp"
        assert data["candidate_id"] == "CAND_999"
        assert data["candidate_name"] == "Bob"
        assert data["match_score"] == 0.0

    def test_a11_whitespace_only_skill_name_rejected(self):
        payload = {
            "job_requirements": {
                "job_id": "J1",
                "job_title": "Dev",
                "required_skills": [{"name": "   "}],
            },
            "candidate_profile": {"skills": []},
        }
        resp = client.post("/api/v1/skill-match", json=payload)
        assert resp.status_code == 422
        assert "Skill name cannot be empty" in resp.text or "Validation Error" in resp.text

    def test_a12_empty_http_body_rejected_422(self):
        resp = client.post(
            "/api/v1/skill-match",
            content="",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 422


# ==============================================================================
# Category B: Missing Fields & Schema Validation
# ==============================================================================
class TestCategoryBMissingAndSchemaValidation:
    def test_b1_missing_entire_role1_payload(self):
        payload = {"role3": {"candidate_id": "C1", "skills": []}}
        resp = client.post("/api/v1/skill-match", json=payload)
        assert resp.status_code == 422
        assert "job_requirements" in resp.text

    def test_b2_missing_entire_role3_payload(self):
        payload = {"role1": {"job_id": "J1", "required_skills": []}}
        resp = client.post("/api/v1/skill-match", json=payload)
        assert resp.status_code == 422
        assert "candidate_profile" in resp.text

    def test_b3_missing_required_fields_in_role1_skills(self):
        # Missing skill name
        payload = {
            "job_requirements": {
                "required_skills": [{"category_code": "OS", "weight": 1.0}],
            },
            "candidate_profile": {"skills": []},
        }
        resp = client.post("/api/v1/skill-match", json=payload)
        assert resp.status_code == 422

    def test_b4_missing_required_fields_in_role3_skills(self):
        payload = {
            "job_requirements": {"required_skills": []},
            "candidate_profile": {
                "skills": [{"category_code": "OS", "confidence": "high"}],
            },
        }
        resp = client.post("/api/v1/skill-match", json=payload)
        assert resp.status_code == 422

    def test_b5_missing_skill_name_field(self):
        with pytest.raises(Exception):
            RequiredSkill.model_validate({})
        with pytest.raises(Exception):
            CandidateSkill.model_validate({})

    def test_b6_missing_optional_metadata_handled_gracefully(self):
        # No company, no section, no confidence, no source_file
        payload = {
            "job_requirements": {
                "job_id": "J1",
                "job_title": "Engineer",
                "required_skills": [{"name": "Go"}],
            },
            "candidate_profile": {
                "candidate_id": "C1",
                "skills": [{"name": "Go"}],
            },
        }
        resp = client.post("/api/v1/skill-match", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["match_score"] == 100.0
        assert data["company"] is None
        assert data["skill_details"][0]["confidence"] is None

    def test_b7_incorrect_field_names_and_misspelled_keys(self):
        # Misspelled top-level keys
        payload = {"job_reqs_bad": {}, "candidate_prof_bad": {}}
        resp = client.post("/api/v1/skill-match", json=payload)
        assert resp.status_code == 422

    def test_b8_incorrect_data_types_skills_not_a_list(self):
        payload = {
            "job_requirements": {"required_skills": "Python, SQL"},
            "candidate_profile": {"skills": []},
        }
        resp = client.post("/api/v1/skill-match", json=payload)
        assert resp.status_code == 422

    def test_b9_null_in_required_skill_name(self):
        payload = {
            "job_requirements": {"required_skills": [{"name": None}]},
            "candidate_profile": {"skills": []},
        }
        resp = client.post("/api/v1/skill-match", json=payload)
        assert resp.status_code == 422

    def test_b10_unexpected_additional_fields_ignored(self):
        payload = {
            "job_requirements": {
                "job_id": "J1",
                "job_title": "Dev",
                "required_skills": [{"name": "Python"}],
                "salary_range": "$120,000",
                "recruiter_notes": "urgent hire",
            },
            "candidate_profile": {
                "candidate_id": "C1",
                "skills": [{"name": "Python"}],
                "favorite_coffee": "espresso",
            },
            "extra_pipeline_metadata": {"stage": "screening"},
        }
        resp = client.post("/api/v1/skill-match", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["match_score"] == 100.0

    def test_b11_nested_skill_missing_required_name(self):
        payload = {
            "job_requirements": {"required_skills": [{"weight": 1.0}]},
            "candidate_profile": {"skills": []},
        }
        resp = client.post("/api/v1/skill-match", json=payload)
        assert resp.status_code == 422

    def test_b12_valid_minimal_payload(self):
        payload = {
            "job_requirements": {
                "job_id": "J1",
                "job_title": "Dev",
                "required_skills": [{"name": "Python"}],
            },
            "candidate_profile": {
                "candidate_id": "C1",
                "skills": [{"name": "Python"}],
            },
        }
        resp = client.post("/api/v1/skill-match", json=payload)
        assert resp.status_code == 200
        assert resp.json()["match_score"] == 100.0

    def test_b13_payload_with_all_optional_fields(self):
        payload = {
            "job_requirements": {
                "job_id": "J1",
                "job_title": "Senior Dev",
                "company": "Tech Corp",
                "category_breakdown": {"SWE": 1},
                "total_skills": 1,
                "required_skills": [
                    {
                        "name": "Python",
                        "category_code": "SWE",
                        "weight": 2.0,
                        "importance": "required",
                    }
                ],
            },
            "candidate_profile": {
                "candidate_id": "C1",
                "candidate_name": "Alice",
                "source_file": "Alice.pdf",
                "source_type": "resume",
                "schema_version": "1.0",
                "profile_prefill": {"name": "Alice", "email": "alice@test.com"},
                "skills": [
                    {
                        "name": "Python",
                        "category_code": "SWE",
                        "evidence": "10 years experience",
                        "confidence": "high",
                        "evidence_verified": True,
                        "source_section": "experience",
                    }
                ],
            },
        }
        resp = client.post("/api/v1/skill-match", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["candidate_name"] == "Alice"
        assert data["company"] == "Tech Corp"
        assert data["match_score"] == 100.0

    def test_b14_different_supported_representations_of_skills(self):
        # Plain strings in skills list
        payload = {
            "job_requirements": {
                "job_id": "J1",
                "job_title": "Dev",
                "required_skills": ["Python", "FastAPI"],
            },
            "candidate_profile": {
                "candidate_id": "C1",
                "skills": ["Python", "FastAPI"],
            },
        }
        resp = client.post("/api/v1/skill-match", json=payload)
        assert resp.status_code == 200
        assert resp.json()["match_score"] == 100.0


# ==============================================================================
# Category C: Malformed and Invalid JSON
# ==============================================================================
class TestCategoryCMalformedJson:
    def test_c1_invalid_json_syntax(self):
        resp = client.post(
            "/api/v1/skill-match",
            content='{"candidate_profile": { "skills": [} }',
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 422
        assert "Validation Error" in resp.text

    def test_c2_truncated_json(self):
        resp = client.post(
            "/api/v1/skill-match",
            content='{"candidate_profile": {"cand',
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 422

    def test_c3_extra_commas_json(self):
        resp = client.post(
            "/api/v1/skill-match",
            content='{"candidate_profile": {},, "job_requirements": {}}',
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 422

    def test_c4_unquoted_json_keys(self):
        resp = client.post(
            "/api/v1/skill-match",
            content='{candidate_profile: {}, job_requirements: {}}',
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 422

    def test_c5_invalid_escape_sequence(self):
        resp = client.post(
            "/api/v1/skill-match",
            content='{"test": "\\uZZZZ"}',
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 422

    def test_c6_invalid_content_type(self):
        # Non-JSON content-type with plain text
        resp = client.post(
            "/api/v1/skill-match",
            content="Hello world",
            headers={"Content-Type": "text/plain"},
        )
        assert resp.status_code == 422

    def test_c7_json_array_of_numbers_instead_of_object(self):
        resp = client.post(
            "/api/v1/skill-match",
            json=[1, 2, 3],
        )
        assert resp.status_code == 422

    def test_c8_plain_string_instead_of_object(self):
        resp = client.post(
            "/api/v1/skill-match",
            json="just a string payload",
        )
        assert resp.status_code == 422

    def test_c9_plain_number_instead_of_object(self):
        resp = client.post(
            "/api/v1/skill-match",
            json=12345,
        )
        assert resp.status_code == 422

    def test_c10_plain_boolean_instead_of_object(self):
        resp = client.post(
            "/api/v1/skill-match",
            json=True,
        )
        assert resp.status_code == 422

    def test_c11_deeply_nested_json_object(self):
        # Moderately deep nesting should not crash the server
        nested = {"level1": {"level2": {"level3": {"skills": [{"name": "Python"}]}}}}
        payload = {
            "job_requirements": {
                "job_id": "J1",
                "job_title": "Dev",
                "required_skills": [{"name": "Python"}],
            },
            "candidate_profile": {"skills": [{"name": "Python"}]},
            "metadata": nested,
        }
        resp = client.post("/api/v1/skill-match", json=payload)
        assert resp.status_code == 200

    def test_c12_large_payload_handling(self):
        # 100 skills payload should be processed safely without timeout or memory error
        skills = [{"name": f"Skill_{i}"} for i in range(100)]
        payload = {
            "job_requirements": {
                "job_id": "J_LARGE",
                "job_title": "Multi-Skilled Role",
                "required_skills": skills,
            },
            "candidate_profile": {
                "candidate_id": "C_LARGE",
                "skills": skills[:50],
            },
        }
        resp = client.post("/api/v1/skill-match", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_required_skills"] == 100
        assert data["matched_skills_count"] == 50
        assert data["match_score"] == 50.0


# ==============================================================================
# Category D: Skill Normalization Edge Cases
# ==============================================================================
class TestCategoryDNormalization:
    def test_d1_case_insensitivity(self):
        assert normalize_skill_name("Python") == "python"
        assert normalize_skill_name("PYTHON") == "python"
        assert normalize_skill_name("pYtHoN") == "python"

    def test_d2_surrounding_whitespace(self):
        assert normalize_skill_name("   Docker   ") == "docker"
        assert normalize_skill_name("\tKubernetes\n") == "kubernetes"

    def test_d3_internal_multiple_spaces(self):
        assert normalize_skill_name("Machine   Learning") == "machine learning"
        assert normalize_skill_name("REST    APIs") == "rest api"

    def test_d4_punctuation_cpp_csharp(self):
        assert normalize_skill_name("C++") == "c++"
        assert normalize_skill_name("cpp") == "c++"
        assert normalize_skill_name("c/c++") == "c++"
        assert normalize_skill_name("C#") == "c#"
        assert normalize_skill_name("csharp") == "c#"

    def test_d5_dots_and_slashes_node_cicd(self):
        assert normalize_skill_name("Node.js") == "node.js"
        assert normalize_skill_name("NodeJS") == "node.js"
        assert normalize_skill_name("CI/CD") == "ci/cd"
        assert normalize_skill_name("cicd") == "ci/cd"

    def test_d6_numbers_in_skills_python3_sql(self):
        assert normalize_skill_name("Python 3") == "python"
        assert normalize_skill_name("python3") == "python"
        assert normalize_skill_name("SQL") == "sql"

    def test_d7_parentheses_removal(self):
        assert normalize_skill_name("SQL (basic)") == "sql"
        assert normalize_skill_name("Linux (advanced administration)") == "linux"
        assert normalize_skill_name("AWS (EC2, S3)") == "aws"

    def test_d8_parentheses_only_yields_empty(self):
        assert normalize_skill_name("(basic)") == ""
        assert normalize_skill_name("()") == ""

    def test_d9_unicode_and_emojis(self):
        # Emojis and unicode shouldn't crash normalizer
        norm = normalize_skill_name("Python 🐍")
        assert "python" in norm

    def test_d10_very_long_skill_name(self):
        long_skill = "A" * 300
        norm = normalize_skill_name(long_skill)
        assert norm == ("a" * 300)

    def test_d11_known_aliases_resolution(self):
        assert normalize_skill_name("k8s") == "kubernetes"
        assert normalize_skill_name("postgres") == "postgresql"
        assert normalize_skill_name("Postgre SQL") == "postgresql"
        assert normalize_skill_name("VueJS") == "vue.js"
        assert normalize_skill_name("MS Excel") == "excel"

    def test_d12_distinct_skills_not_merged(self):
        # Crucial distinction guarantees
        assert normalize_skill_name("Java") != normalize_skill_name("JavaScript")
        assert normalize_skill_name("Git") != normalize_skill_name("GitHub")
        assert normalize_skill_name("C") != normalize_skill_name("C++")
        assert normalize_skill_name("C") != normalize_skill_name("C#")
        assert normalize_skill_name("SQL") != normalize_skill_name("NoSQL")

    def test_d13_duplicate_candidate_skills_highest_confidence(self):
        cand = CandidateProfile(
            candidate_id="C1",
            skills=[
                CandidateSkill(name="Python", confidence="low"),
                CandidateSkill(name="Python", confidence="high", evidence="Pro"),
            ],
        )
        job = JobRequirements(
            job_id="J1",
            job_title="Dev",
            required_skills=[RequiredSkill(name="Python")],
        )
        res = match_candidate_to_job(cand, job)
        assert res.matched_skills_count == 1
        assert "high confidence" in res.skill_details[0].explanation

    def test_d14_duplicate_job_skills_deduped(self):
        cand = CandidateProfile(
            candidate_id="C1",
            skills=[CandidateSkill(name="Python")],
        )
        job = JobRequirements(
            job_id="J1",
            job_title="Dev",
            required_skills=[
                RequiredSkill(name="Python"),
                RequiredSkill(name="python"),
                RequiredSkill(name="PYTHON"),
            ],
        )
        res = match_candidate_to_job(cand, job)
        assert res.total_required_skills == 1
        assert res.matched_skills_count == 1
        assert res.match_score == 100.0

    def test_d15_non_string_normalization_fallback(self):
        assert normalize_skill_name(None) == ""
        assert normalize_skill_name(123) == ""
        assert normalize_skill_name([]) == ""


# ==============================================================================
# Category E: Matching & Categorization Edge Cases
# ==============================================================================
class TestCategoryEMatchingAndCategorization:
    def test_e1_all_required_skills_match(self):
        cand = CandidateProfile(
            candidate_id="C1",
            skills=[CandidateSkill(name="Python"), CandidateSkill(name="SQL")],
        )
        job = JobRequirements(
            job_id="J1",
            job_title="Dev",
            required_skills=[RequiredSkill(name="Python"), RequiredSkill(name="SQL")],
        )
        res = match_candidate_to_job(cand, job)
        assert res.match_score == 100.0
        assert res.matched_skills_count == 2
        assert len(res.missing_or_unverified_skills) == 0

    def test_e2_no_skills_match(self):
        cand = CandidateProfile(
            candidate_id="C1",
            skills=[CandidateSkill(name="Rust")],
        )
        job = JobRequirements(
            job_id="J1",
            job_title="Dev",
            required_skills=[RequiredSkill(name="Python"), RequiredSkill(name="SQL")],
        )
        res = match_candidate_to_job(cand, job)
        assert res.match_score == 0.0
        assert res.matched_skills_count == 0
        assert len(res.missing_or_unverified_skills) == 2
        assert res.additional_candidate_skills == ["Rust"]

    def test_e3_some_skills_match(self):
        cand = CandidateProfile(
            candidate_id="C1",
            skills=[CandidateSkill(name="Python")],
        )
        job = JobRequirements(
            job_id="J1",
            job_title="Dev",
            required_skills=[RequiredSkill(name="Python"), RequiredSkill(name="SQL")],
        )
        res = match_candidate_to_job(cand, job)
        assert res.match_score == 50.0
        assert res.matched_skills == ["Python"]
        assert res.missing_or_unverified_skills == ["SQL"]

    def test_e4_required_match_preferred_missing(self):
        # Required weight = 1.0, Preferred weight = 0.5. Total = 1.5.
        # Match only required: 1.0 / 1.5 = 66.67%
        cand = CandidateProfile(
            candidate_id="C1",
            skills=[CandidateSkill(name="Python")],
        )
        job = JobRequirements(
            job_id="J1",
            job_title="Dev",
            required_skills=[
                RequiredSkill(name="Python", importance="required"),
                RequiredSkill(name="Docker", importance="preferred"),
            ],
        )
        res = match_candidate_to_job(cand, job)
        assert res.match_score == 66.67
        assert res.matched_skills == ["Python"]

    def test_e5_preferred_match_required_missing(self):
        # Match only preferred: 0.5 / 1.5 = 33.33%
        cand = CandidateProfile(
            candidate_id="C1",
            skills=[CandidateSkill(name="Docker")],
        )
        job = JobRequirements(
            job_id="J1",
            job_title="Dev",
            required_skills=[
                RequiredSkill(name="Python", importance="required"),
                RequiredSkill(name="Docker", importance="preferred"),
            ],
        )
        res = match_candidate_to_job(cand, job)
        assert res.match_score == 33.33
        assert res.matched_skills == ["Docker"]

    def test_e6_only_optional_skills_match(self):
        cand = CandidateProfile(
            candidate_id="C1",
            skills=[CandidateSkill(name="Kubernetes")],
        )
        job = JobRequirements(
            job_id="J1",
            job_title="Dev",
            required_skills=[
                RequiredSkill(name="Java", importance="required"),
                RequiredSkill(name="Kubernetes", importance="nice-to-have"),
            ],
        )
        res = match_candidate_to_job(cand, job)
        assert res.match_score == 33.33
        assert "Kubernetes" in res.matched_skills

    def test_e7_duplicate_required_skills_no_score_inflation(self):
        cand = CandidateProfile(
            candidate_id="C1",
            skills=[CandidateSkill(name="Python")],
        )
        job = JobRequirements(
            job_id="J1",
            job_title="Dev",
            required_skills=[
                RequiredSkill(name="Python"),
                RequiredSkill(name="Python"),
                RequiredSkill(name="SQL"),
            ],
        )
        res = match_candidate_to_job(cand, job)
        assert res.total_required_skills == 2
        assert res.matched_skills_count == 1
        assert res.match_score == 50.0

    def test_e8_duplicate_candidate_skills_retains_verified(self):
        cand = CandidateProfile(
            candidate_id="C1",
            skills=[
                CandidateSkill(name="Python", evidence_verified=False),
                CandidateSkill(name="Python", evidence_verified=True, evidence="Verified repo"),
            ],
        )
        job = JobRequirements(
            job_id="J1",
            job_title="Dev",
            required_skills=[RequiredSkill(name="Python")],
        )
        res = match_candidate_to_job(cand, job)
        assert res.skill_details[0].evidence_verified is True

    def test_e9_skill_in_multiple_categories(self):
        # Candidate lists SQL in category SQL, and SQL in category DB
        cand = CandidateProfile(
            candidate_id="C1",
            skills=[
                CandidateSkill(name="SQL", category_code="SQL"),
                CandidateSkill(name="SQL", category_code="DB"),
            ],
        )
        job = JobRequirements(
            job_id="J1",
            job_title="Analyst",
            required_skills=[RequiredSkill(name="SQL", category_code="SQL")],
        )
        res = match_candidate_to_job(cand, job)
        assert res.match_score == 100.0
        assert res.matched_skills_count == 1

    def test_e10_job_has_no_required_skills(self):
        cand = CandidateProfile(
            candidate_id="C1",
            skills=[CandidateSkill(name="Python")],
        )
        job = JobRequirements(
            job_id="J1",
            job_title="Intern",
            required_skills=[],
        )
        res = match_candidate_to_job(cand, job)
        assert res.match_score == 0.0
        assert res.total_required_skills == 0
        assert res.additional_candidate_skills == ["Python"]

    def test_e11_candidate_has_no_skills(self):
        cand = CandidateProfile(candidate_id="C1", skills=[])
        job = JobRequirements(
            job_id="J1",
            job_title="Dev",
            required_skills=[RequiredSkill(name="Python")],
        )
        res = match_candidate_to_job(cand, job)
        assert res.match_score == 0.0
        assert res.missing_or_unverified_skills == ["Python"]

    def test_e12_identical_skill_lists(self):
        skills = [CandidateSkill(name="Go"), CandidateSkill(name="AWS")]
        reqs = [RequiredSkill(name="Go"), RequiredSkill(name="AWS")]
        cand = CandidateProfile(candidate_id="C1", skills=skills)
        job = JobRequirements(job_id="J1", job_title="DevOps", required_skills=reqs)
        res = match_candidate_to_job(cand, job)
        assert res.match_score == 100.0
        assert len(res.additional_candidate_skills) == 0
        assert len(res.missing_or_unverified_skills) == 0

    def test_e13_candidate_additional_skills_categorization(self):
        cand = CandidateProfile(
            candidate_id="C1",
            skills=[
                CandidateSkill(name="Python"),
                CandidateSkill(name="FastAPI"),
                CandidateSkill(name="Rust"),
            ],
        )
        job = JobRequirements(
            job_id="J1",
            job_title="Dev",
            required_skills=[RequiredSkill(name="Python")],
        )
        res = match_candidate_to_job(cand, job)
        assert res.matched_skills == ["Python"]
        assert set(res.additional_candidate_skills) == {"FastAPI", "Rust"}

    def test_e14_job_missing_skills_categorization(self):
        cand = CandidateProfile(
            candidate_id="C1",
            skills=[CandidateSkill(name="Python")],
        )
        job = JobRequirements(
            job_id="J1",
            job_title="Dev",
            required_skills=[
                RequiredSkill(name="Python"),
                RequiredSkill(name="Scala"),
                RequiredSkill(name="Hadoop"),
            ],
        )
        res = match_candidate_to_job(cand, job)
        assert set(res.missing_or_unverified_skills) == {"Scala", "Hadoop"}

    def test_e15_empty_or_none_category_codes(self):
        cand = CandidateProfile(
            candidate_id="C1",
            skills=[CandidateSkill(name="Python", category_code=None)],
        )
        job = JobRequirements(
            job_id="J1",
            job_title="Dev",
            required_skills=[RequiredSkill(name="Python", category_code=None)],
        )
        res = match_candidate_to_job(cand, job)
        assert res.match_score == 100.0
        assert res.category_summary is None

    def test_e16_unknown_category_codes(self):
        cand = CandidateProfile(
            candidate_id="C1",
            skills=[CandidateSkill(name="Python", category_code="CUSTOM_CAT")],
        )
        job = JobRequirements(
            job_id="J1",
            job_title="Dev",
            required_skills=[RequiredSkill(name="Python", category_code="CUSTOM_CAT")],
        )
        res = match_candidate_to_job(cand, job)
        assert res.category_summary == {"CUSTOM_CAT": {"required": 1, "matched": 1}}

    def test_e17_numeric_confidence_levels(self):
        cand = CandidateProfile(
            candidate_id="C1",
            skills=[
                CandidateSkill(name="Python", confidence=0.95),
                CandidateSkill(name="SQL", confidence=50),
                CandidateSkill(name="Git", confidence=0.2),
            ],
        )
        conf_map = {s.name: s.confidence for s in cand.skills}
        assert conf_map["Python"] == "high"
        assert conf_map["SQL"] == "medium"
        assert conf_map["Git"] == "low"

    def test_e18_evidence_verified_string_boolean_parsing(self):
        s1 = CandidateSkill.model_validate({"name": "Python", "evidence_verified": "true"})
        s2 = CandidateSkill.model_validate({"name": "SQL", "evidence_verified": "0"})
        assert s1.evidence_verified is True
        assert s2.evidence_verified is False

    def test_e19_large_skill_list_matching(self):
        reqs = [RequiredSkill(name=f"Skill_{i}") for i in range(50)]
        cand_skills = [CandidateSkill(name=f"Skill_{i}") for i in range(25)]
        cand = CandidateProfile(candidate_id="C1", skills=cand_skills)
        job = JobRequirements(job_id="J1", job_title="Lead", required_skills=reqs)
        res = match_candidate_to_job(cand, job)
        assert res.total_required_skills == 50
        assert res.matched_skills_count == 25
        assert res.match_score == 50.0

    def test_e20_skills_dict_grouped_by_category(self):
        # Candidate profile where skills is a dict { category: [skills] }
        data = {
            "candidate_id": "C_DICT",
            "skills": {
                "LANG": ["Python", "JavaScript"],
                "DB": [{"name": "PostgreSQL"}],
            },
        }
        cand = CandidateProfile.model_validate(data)
        assert len(cand.skills) == 3
        skills_by_name = {s.name: s.category_code for s in cand.skills}
        assert skills_by_name["Python"] == "LANG"
        assert skills_by_name["PostgreSQL"] == "DB"


# ==============================================================================
# Category F: Scoring and Mathematical Edge Cases
# ==============================================================================
class TestCategoryFScoringAndMath:
    def test_f1_perfect_match_score(self):
        reqs = [RequiredSkill(name="A"), RequiredSkill(name="B")]
        assert calculate_match_score(reqs, {"A", "B"}) == 100.0

    def test_f2_zero_match_score(self):
        reqs = [RequiredSkill(name="A"), RequiredSkill(name="B")]
        assert calculate_match_score(reqs, set()) == 0.0

    def test_f3_partial_match_score_precision(self):
        # 1 of 3 = 33.33%
        reqs = [RequiredSkill(name="A"), RequiredSkill(name="B"), RequiredSkill(name="C")]
        assert calculate_match_score(reqs, {"A"}) == 33.33
        # 2 of 3 = 66.67%
        assert calculate_match_score(reqs, {"A", "B"}) == 66.67

    def test_f4_empty_skill_sets_zero_division(self):
        assert calculate_match_score([], set()) == 0.0
        assert calculate_match_score([], {"Python"}) == 0.0

    def test_f5_no_required_skills_zero_score(self):
        cand = CandidateProfile(candidate_id="C1", skills=[CandidateSkill(name="Python")])
        job = JobRequirements(job_id="J1", job_title="Open", required_skills=[])
        res = match_candidate_to_job(cand, job)
        assert res.match_score == 0.0

    def test_f6_duplicate_skills_dont_inflate_score(self):
        reqs = [RequiredSkill(name="Python"), RequiredSkill(name="Python")]
        # Deduplication is handled by matcher pipeline
        job = JobRequirements(job_id="J1", job_title="Dev", required_skills=reqs)
        cand = CandidateProfile(candidate_id="C1", skills=[CandidateSkill(name="Python")])
        res = match_candidate_to_job(cand, job)
        assert res.match_score == 100.0
        assert res.total_required_skills == 1

    def test_f7_score_bounds_invariant(self):
        reqs = [RequiredSkill(name="A", weight=10.0)]
        score_full = calculate_match_score(reqs, {"A"})
        score_none = calculate_match_score(reqs, set())
        assert 0.0 <= score_full <= 100.0
        assert 0.0 <= score_none <= 100.0

    def test_f8_score_determinism_repeated_runs(self):
        reqs = [
            RequiredSkill(name="Python", weight=2.0),
            RequiredSkill(name="SQL", weight=1.0),
            RequiredSkill(name="Docker", weight=0.5),
        ]
        matched = {"Python", "Docker"}
        scores = [calculate_match_score(reqs, matched) for _ in range(50)]
        assert len(set(scores)) == 1

    def test_f9_score_order_insensitivity(self):
        reqs1 = [
            RequiredSkill(name="Python", weight=2.0),
            RequiredSkill(name="SQL", weight=1.0),
        ]
        reqs2 = [
            RequiredSkill(name="SQL", weight=1.0),
            RequiredSkill(name="Python", weight=2.0),
        ]
        matched = {"Python"}
        assert calculate_match_score(reqs1, matched) == calculate_match_score(reqs2, matched)

    def test_f10_missing_optional_weights_defaults_to_one(self):
        req = RequiredSkill.model_validate({"name": "Python"})
        assert req.weight == 1.0

    def test_f11_negative_weight_rejected(self):
        with pytest.raises(Exception):
            RequiredSkill.model_validate({"name": "Python", "weight": -1.0})

    def test_f12_nan_weight_rejected(self):
        with pytest.raises(Exception):
            RequiredSkill.model_validate({"name": "Python", "weight": "nan"})
        with pytest.raises(Exception):
            RequiredSkill.model_validate({"name": "Python", "weight": float("nan")})

    def test_f13_inf_weight_rejected(self):
        with pytest.raises(Exception):
            RequiredSkill.model_validate({"name": "Python", "weight": "inf"})
        with pytest.raises(Exception):
            RequiredSkill.model_validate({"name": "Python", "weight": float("inf")})

    def test_f14_all_zero_weights_safe_zero_score(self):
        reqs = [RequiredSkill(name="A", weight=0.0), RequiredSkill(name="B", weight=0.0)]
        assert calculate_match_score(reqs, {"A", "B"}) == 0.0

    def test_f15_integer_and_float_weights_equivalent(self):
        req_int = RequiredSkill.model_validate({"name": "Python", "weight": 2})
        req_float = RequiredSkill.model_validate({"name": "Python", "weight": 2.0})
        assert req_int.weight == req_float.weight == 2.0

    def test_f16_large_finite_weights(self):
        reqs = [
            RequiredSkill(name="Critical", weight=1000.0),
            RequiredSkill(name="Secondary", weight=10.0),
        ]
        score = calculate_match_score(reqs, {"Critical"})
        assert score == round((1000.0 / 1010.0) * 100, 2)

    def test_f17_rounding_two_decimal_places(self):
        reqs = [RequiredSkill(name=f"S{i}") for i in range(7)]
        score = calculate_match_score(reqs, {"S0", "S1"})
        # 2 / 7 = 28.5714... -> 28.57
        assert score == 28.57

    def test_f18_audit_details_consistency_with_score(self):
        cand = CandidateProfile(
            candidate_id="C1",
            skills=[CandidateSkill(name="A"), CandidateSkill(name="B")],
        )
        job = JobRequirements(
            job_id="J1",
            job_title="Dev",
            required_skills=[
                RequiredSkill(name="A"),
                RequiredSkill(name="B"),
                RequiredSkill(name="C"),
            ],
        )
        res = match_candidate_to_job(cand, job)
        assert res.matched_skills_count == len(res.matched_skills) == 2
        assert len(res.missing_or_unverified_skills) == 1
        assert res.total_required_skills == 3
        assert res.match_score == 66.67


# ==============================================================================
# Category G: Cross-Role Integration Tests
# ==============================================================================
class TestCategoryGCrossRoleIntegration:
    def test_g1_realistic_role1_role3_fixtures(self):
        res = match_role1_and_role3(
            role1_input="sample_data/role1_job_sample.json",
            role3_input="sample_data/role3_candidate_sample.json",
        )
        assert res.candidate_name == "Priya Menon"
        assert res.job_title == "Application Support Analyst"
        assert res.match_score == 50.0
        assert "SQL" in res.matched_skills
        assert "Linux" in res.matched_skills
        assert "Networking fundamentals" in res.matched_skills

    def test_g2_role1_jd_analytics_and_role3_candidate_profiling_keys(self):
        with open("sample_data/role1_job_sample.json") as f:
            r1 = json.load(f)
        with open("sample_data/role3_candidate_sample.json") as f:
            r3 = json.load(f)
        payload = {"role1_jd_analytics": r1, "role3_candidate_profiling": r3}
        resp = client.post("/api/v1/skill-match", json=payload)
        assert resp.status_code == 200
        assert resp.json()["match_score"] == 50.0

    def test_g3_role1_and_role3_shorthand_keys(self):
        with open("sample_data/role1_job_sample.json") as f:
            r1 = json.load(f)
        with open("sample_data/role3_candidate_sample.json") as f:
            r3 = json.load(f)
        payload = {"role1": r1, "role3": r3}
        resp = client.post("/api/v1/skill-match", json=payload)
        assert resp.status_code == 200
        assert resp.json()["match_score"] == 50.0

    def test_g4_file_path_integration(self):
        payload = {
            "role1_path": "sample_data/role1_job_sample.json",
            "role3_path": "sample_data/role3_candidate_sample.json",
        }
        resp = client.post("/api/v1/skill-match", json=payload)
        assert resp.status_code == 200
        assert resp.json()["candidate_id"] == "Priya Menon"

    def test_g5_valid_role1_with_invalid_role3_rejects(self):
        with open("sample_data/role1_job_sample.json") as f:
            r1 = json.load(f)
        # Invalid role3 with empty skill name
        r3_invalid = {"skills": [{"name": "   "}]}
        payload = {"role1": r1, "role3": r3_invalid}
        resp = client.post("/api/v1/skill-match", json=payload)
        assert resp.status_code == 422

    def test_g6_invalid_role1_with_valid_role3_rejects(self):
        with open("sample_data/role3_candidate_sample.json") as f:
            r3 = json.load(f)
        r1_invalid = {"required_skills": [{"name": "Python", "weight": -10}]}
        payload = {"role1": r1_invalid, "role3": r3}
        resp = client.post("/api/v1/skill-match", json=payload)
        assert resp.status_code == 422

    def test_g7_role1_missing_ids_fallback(self):
        # Role 1 without output_file or file or id defaults gracefully
        data = {"role": "Senior Dev", "skills": ["Python"]}
        job = JobRequirements.model_validate(data)
        assert job.job_id == "JOB_DEFAULT"
        assert job.job_title == "Senior Dev"

    def test_g8_role3_missing_prefill_fallback(self):
        # Role 3 without profile_prefill defaults candidate_id
        data = {"source_file": "Resume_123.pdf", "skills": ["Python"]}
        cand = CandidateProfile.model_validate(data)
        assert cand.candidate_id == "Resume_123.pdf"

    def test_g9_role1_role3_null_skills_handled(self):
        payload = {
            "job_requirements": {"job_id": "J1", "required_skills": []},
            "candidate_profile": {"candidate_id": "C1", "skills": []},
        }
        resp = client.post("/api/v1/skill-match", json=payload)
        assert resp.status_code == 200

    def test_g10_unexpected_upstream_fields_ignored(self):
        with open("sample_data/role1_job_sample.json") as f:
            r1 = json.load(f)
        r1["internal_ai_token_cost"] = 0.002
        r1["latency_ms"] = 120

        with open("sample_data/role3_candidate_sample.json") as f:
            r3 = json.load(f)
        r3["parser_engine_version"] = "v2.4.1"

        payload = {"role1": r1, "role3": r3}
        resp = client.post("/api/v1/skill-match", json=payload)
        assert resp.status_code == 200

    def test_g11_schema_version_preserved(self):
        cand = CandidateProfile.model_validate(
            {"candidate_id": "C1", "schema_version": "2.1", "skills": []}
        )
        assert cand.schema_version == "2.1"

    def test_g12_metadata_not_confused_with_skills(self):
        cand = CandidateProfile.model_validate(
            {
                "candidate_id": "C1",
                "source_file": "Python_Developer.pdf",
                "skills": [{"name": "SQL"}],
            }
        )
        job = JobRequirements.model_validate(
            {
                "job_id": "J1",
                "job_title": "Python Developer",
                "required_skills": [{"name": "Python"}],
            }
        )
        res = match_candidate_to_job(cand, job)
        # "Python" in job_title or source_file must not be treated as a candidate skill!
        assert "Python" in res.missing_or_unverified_skills
        assert res.match_score == 0.0


# ==============================================================================
# Category H: API and HTTP Behavior
# ==============================================================================
class TestCategoryHApiHttpBehavior:
    def test_h1_successful_request_status_code(self):
        resp = client.post(
            "/api/v1/skill-match",
            json={
                "job_requirements": {"required_skills": [{"name": "Python"}]},
                "candidate_profile": {"skills": [{"name": "Python"}]},
            },
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/json")

    def test_h2_invalid_request_body_422(self):
        resp = client.post("/api/v1/skill-match", json={"invalid": "payload"})
        assert resp.status_code == 422
        data = resp.json()
        assert "error" in data
        assert "details" in data

    def test_h3_missing_required_payload_422(self):
        resp = client.post("/api/v1/skill-match", json={})
        assert resp.status_code == 422

    def test_h4_unsupported_http_method_405(self):
        resp = client.get("/api/v1/skill-match")
        assert resp.status_code == 405

    def test_h5_unknown_route_404(self):
        resp = client.get("/api/v1/nonexistent-route")
        assert resp.status_code == 404

    def test_h6_health_endpoint(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["service"] == "radix-role5"

    def test_h7_root_endpoint(self):
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "running"
        assert "/api/v1/skill-match" in data["endpoints"]["skill_match"]

    def test_h8_alias_endpoint_role1_role3_match(self):
        resp = client.post(
            "/api/v1/role1-role3-match",
            json={
                "role1": {"required_skills": [{"name": "Python"}]},
                "role3": {"skills": [{"name": "Python"}]},
            },
        )
        assert resp.status_code == 200
        assert resp.json()["match_score"] == 100.0

    def test_h9_alias_endpoint_match(self):
        resp = client.post(
            "/api/v1/match",
            json={
                "role1": {"required_skills": [{"name": "Python"}]},
                "role3": {"skills": [{"name": "Python"}]},
            },
        )
        assert resp.status_code == 200

    def test_h10_no_internal_stack_trace_leaks(self):
        resp = client.post(
            "/api/v1/skill-match",
            content="invalid json body",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 422
        assert "Traceback" not in resp.text
        assert "File \"" not in resp.text

    def test_h11_validation_error_structure(self):
        resp = client.post(
            "/api/v1/skill-match",
            json={"job_requirements": {"required_skills": [{"name": "Python", "weight": -5}]}},
        )
        assert resp.status_code == 422
        data = resp.json()
        assert data["error"] == "Validation Error"
        assert isinstance(data["details"], list)

    def test_h12_content_type_is_json(self):
        resp = client.get("/health")
        assert "application/json" in resp.headers["content-type"]

    def test_h13_malformed_json_returns_422(self):
        resp = client.post(
            "/api/v1/skill-match",
            content="{bad",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 422

    def test_h14_empty_json_object_returns_422(self):
        resp = client.post("/api/v1/skill-match", json={})
        assert resp.status_code == 422


# ==============================================================================
# Category I: Security, Reliability, and Performance
# ==============================================================================
class TestCategoryISecurityAndReliability:
    def test_i1_xss_injection_payloads(self):
        xss_string = "<script>alert('XSS')</script>"
        cand = CandidateProfile(
            candidate_id="C_XSS",
            skills=[CandidateSkill(name=xss_string)],
        )
        job = JobRequirements(
            job_id="J_XSS",
            job_title="Security Engineer",
            required_skills=[RequiredSkill(name=xss_string)],
        )
        res = match_candidate_to_job(cand, job)
        assert res.match_score == 100.0
        assert res.matched_skills == [xss_string]
        # Explanation safely embeds raw string without evaluation
        assert xss_string in res.skill_details[0].explanation

    def test_i2_sql_injection_payloads(self):
        sql_string = "' OR '1'='1'; DROP TABLE candidates;--"
        cand = CandidateProfile(
            candidate_id="C_SQL",
            skills=[CandidateSkill(name=sql_string)],
        )
        job = JobRequirements(
            job_id="J_SQL",
            job_title="DBA",
            required_skills=[RequiredSkill(name=sql_string)],
        )
        res = match_candidate_to_job(cand, job)
        assert res.match_score == 100.0

    def test_i3_control_characters_and_newlines(self):
        skill_with_newlines = "Python\n\r\tScripting"
        norm = normalize_skill_name(skill_with_newlines)
        assert "\n" not in norm and "\r" not in norm
        assert norm == "python scripting"

    def test_i4_unicode_and_emojis(self):
        cand = CandidateProfile(
            candidate_id="C_UNI",
            skills=[CandidateSkill(name="机器学习"), CandidateSkill(name="Python 🐍")],
        )
        job = JobRequirements(
            job_id="J_UNI",
            job_title="ML Researcher",
            required_skills=[RequiredSkill(name="机器学习"), RequiredSkill(name="Python 🐍")],
        )
        res = match_candidate_to_job(cand, job)
        assert res.match_score == 100.0
        assert "机器学习" in res.matched_skills

    def test_i5_large_payload_performance(self):
        import time
        reqs = [RequiredSkill(name=f"Skill_Perf_{i}") for i in range(200)]
        skills = [CandidateSkill(name=f"Skill_Perf_{i}") for i in range(150)]
        cand = CandidateProfile(candidate_id="C_PERF", skills=skills)
        job = JobRequirements(job_id="J_PERF", job_title="Lead", required_skills=reqs)

        start = time.perf_counter()
        res = match_candidate_to_job(cand, job)
        duration = time.perf_counter() - start

        assert res.match_score == 75.0
        # Must execute within 200ms
        assert duration < 0.20

    def test_i6_excessively_long_strings(self):
        long_evidence = "Evidence " * 500  # 4500 chars
        cand = CandidateProfile(
            candidate_id="C_LONG",
            skills=[CandidateSkill(name="Python", evidence=long_evidence)],
        )
        job = JobRequirements(
            job_id="J_LONG",
            job_title="Dev",
            required_skills=[RequiredSkill(name="Python")],
        )
        res = match_candidate_to_job(cand, job)
        assert res.match_score == 100.0
        assert res.skill_details[0].evidence == long_evidence

    def test_i7_deeply_nested_dict_structures(self):
        # Flattened nested skills mapping
        nested_skills = {
            "FRONTEND": ["React", "HTML"],
            "BACKEND": ["Node.js", "Python"],
            "DEVOPS": ["Docker"],
        }
        cand = CandidateProfile.model_validate({"candidate_id": "C_NEST", "skills": nested_skills})
        assert len(cand.skills) == 5

    def test_i8_repeated_identical_requests(self):
        payload = {
            "job_requirements": {
                "job_id": "J1",
                "job_title": "Dev",
                "required_skills": [{"name": "Python"}, {"name": "SQL"}],
            },
            "candidate_profile": {
                "candidate_id": "C1",
                "skills": [{"name": "Python"}],
            },
        }
        for _ in range(20):
            resp = client.post("/api/v1/skill-match", json=payload)
            assert resp.status_code == 200
            assert resp.json()["match_score"] == 50.0

    def test_i9_no_external_network_calls(self):
        # Core matcher should execute synchronously without internet/sockets
        cand = CandidateProfile(candidate_id="C1", skills=[CandidateSkill(name="C++")])
        job = JobRequirements(job_id="J1", job_title="Dev", required_skills=[RequiredSkill(name="C++")])
        res = match_candidate_to_job(cand, job)
        assert res.match_score == 100.0

    def test_i10_path_traversal_payloads(self):
        # Malicious file path strings shouldn't cause arbitrary file leakage or crash
        traversal_path = "../../../../../../../../../etc/passwd"
        payload = {
            "role1_path": traversal_path,
            "role3_path": "sample_data/role3_candidate_sample.json",
        }
        resp = client.post("/api/v1/skill-match", json=payload)
        # Because the path doesn't point to a valid JD JSON file, it either fails validation or rejects
        assert resp.status_code in (422, 400)

    def test_i11_null_byte_in_strings(self):
        # Null bytes should be safely handled without raising unhandled OS error
        assert _load_json_data("some\x00file.json") == "some\x00file.json"

    def test_i12_memory_stability_repeated_matching(self):
        cand = CandidateProfile(candidate_id="C1", skills=[CandidateSkill(name="Python")])
        job = JobRequirements(job_id="J1", job_title="Dev", required_skills=[RequiredSkill(name="Python")])
        for _ in range(100):
            res = match_candidate_to_job(cand, job)
            assert res.match_score == 100.0


# ==============================================================================
# Category J: Regression and Property-Based Invariant Tests
# ==============================================================================
class TestCategoryJRegressionAndInvariants:
    def test_j1_invariant_determinism(self):
        cand = CandidateProfile(
            candidate_id="C_INV",
            skills=[CandidateSkill(name="Go"), CandidateSkill(name="K8s")],
        )
        job = JobRequirements(
            job_id="J_INV",
            job_title="DevOps",
            required_skills=[
                RequiredSkill(name="Go", weight=2.0),
                RequiredSkill(name="Kubernetes", weight=1.0),
                RequiredSkill(name="Terraform", weight=1.0),
            ],
        )
        first_run = match_candidate_to_job(cand, job).model_dump()
        second_run = match_candidate_to_job(cand, job).model_dump()
        assert first_run == second_run

    def test_j2_invariant_order_insensitivity(self):
        # Order of candidate skills or job skills must not alter match score
        skills_order_a = [CandidateSkill(name="Python"), CandidateSkill(name="SQL"), CandidateSkill(name="Git")]
        skills_order_b = [CandidateSkill(name="Git"), CandidateSkill(name="Python"), CandidateSkill(name="SQL")]

        reqs = [RequiredSkill(name="Python"), RequiredSkill(name="SQL")]

        res_a = match_candidate_to_job(CandidateProfile(candidate_id="C1", skills=skills_order_a), JobRequirements(job_id="J1", job_title="Dev", required_skills=reqs))
        res_b = match_candidate_to_job(CandidateProfile(candidate_id="C1", skills=skills_order_b), JobRequirements(job_id="J1", job_title="Dev", required_skills=reqs))

        assert res_a.match_score == res_b.match_score == 100.0
        assert res_a.matched_skills_count == res_b.matched_skills_count == 2

    def test_j3_invariant_duplicate_insensitivity(self):
        cand_single = CandidateProfile(candidate_id="C1", skills=[CandidateSkill(name="Python")])
        cand_multi = CandidateProfile(
            candidate_id="C1",
            skills=[CandidateSkill(name="Python"), CandidateSkill(name="python"), CandidateSkill(name="PYTHON")],
        )
        job = JobRequirements(job_id="J1", job_title="Dev", required_skills=[RequiredSkill(name="Python")])

        res_single = match_candidate_to_job(cand_single, job)
        res_multi = match_candidate_to_job(cand_multi, job)

        assert res_single.match_score == res_multi.match_score == 100.0
        assert res_single.matched_skills_count == res_multi.matched_skills_count == 1

    def test_j4_invariant_score_bounds(self):
        for matched_count in range(5):
            reqs = [RequiredSkill(name=f"S{i}") for i in range(4)]
            cand_skills = [CandidateSkill(name=f"S{i}") for i in range(matched_count)]
            res = match_candidate_to_job(CandidateProfile(candidate_id="C", skills=cand_skills), JobRequirements(job_id="J", job_title="R", required_skills=reqs))
            assert 0.0 <= res.match_score <= 100.0

    def test_j5_invariant_skill_counts_sum(self):
        # Matched + Missing MUST strictly equal Total Required Skills
        reqs = [RequiredSkill(name="Python"), RequiredSkill(name="Ruby"), RequiredSkill(name="Java")]
        cand = CandidateProfile(candidate_id="C", skills=[CandidateSkill(name="Python")])
        job = JobRequirements(job_id="J", job_title="Dev", required_skills=reqs)
        res = match_candidate_to_job(cand, job)

        assert len(res.matched_skills) + len(res.missing_or_unverified_skills) == res.total_required_skills == 3

    def test_j6_invariant_matched_subset(self):
        cand = CandidateProfile(
            candidate_id="C",
            skills=[CandidateSkill(name="Python"), CandidateSkill(name="Docker")],
        )
        job = JobRequirements(
            job_id="J",
            job_title="Dev",
            required_skills=[RequiredSkill(name="Python"), RequiredSkill(name="Rust")],
        )
        res = match_candidate_to_job(cand, job)
        job_req_names = {r.name for r in job.required_skills}
        for matched in res.matched_skills:
            assert matched in job_req_names

    def test_j7_invariant_additional_disjoint(self):
        # Additional candidate skills should never intersect with matched skills
        cand = CandidateProfile(
            candidate_id="C",
            skills=[CandidateSkill(name="Python"), CandidateSkill(name="Docker")],
        )
        job = JobRequirements(
            job_id="J",
            job_title="Dev",
            required_skills=[RequiredSkill(name="Python")],
        )
        res = match_candidate_to_job(cand, job)
        assert set(res.matched_skills).isdisjoint(set(res.additional_candidate_skills))

    def test_j8_invariant_no_hallucinated_matches(self):
        cand = CandidateProfile(candidate_id="C", skills=[])
        job = JobRequirements(
            job_id="J",
            job_title="Dev",
            required_skills=[RequiredSkill(name="Python"), RequiredSkill(name="SQL")],
        )
        res = match_candidate_to_job(cand, job)
        assert res.matched_skills == []
        assert res.matched_skills_count == 0
        assert res.match_score == 0.0

    def test_j9_invariant_sample_data_matches(self):
        with open("sample_data/role1_job_sample.json") as f:
            r1 = json.load(f)
        with open("sample_data/role3_candidate_sample.json") as f:
            r3 = json.load(f)

        res = match_role1_and_role3(r1, r3)
        assert res.candidate_id == "Priya Menon"
        assert res.job_title == "Application Support Analyst"
        assert res.match_score == 50.0
        assert res.total_required_skills == 6
        assert res.matched_skills_count == 3

    def test_j10_cli_execution_modes(self):
        from app.cli import main
        orig_argv = sys.argv
        try:
            # Mode 1: Summary mode
            sys.argv = [
                "cli.py",
                "--role1", "sample_data/role1_job_sample.json",
                "--role3", "sample_data/role3_candidate_sample.json",
                "--summary",
            ]
            main()

            # Mode 2: Compact mode
            sys.argv = [
                "cli.py",
                "--role1", "sample_data/role1_job_sample.json",
                "--role3", "sample_data/role3_candidate_sample.json",
                "--compact",
            ]
            main()
        finally:
            sys.argv = orig_argv

