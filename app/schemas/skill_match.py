import json
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field, field_validator, model_validator


def _load_json_data(val: Any) -> Any:
    """
    Helper to resolve and load data that might be:
    - Already a dict or list
    - A JSON string (e.g. '{"skills": ...}')
    - A file path string or Path object pointing to an existing JSON file
    """
    if isinstance(val, (dict, list)):
        return val
    if not isinstance(val, (str, Path)):
        return val

    val_str = str(val).strip()
    if not val_str:
        return val

    # If it looks like a JSON string, try parsing it
    if (val_str.startswith("{") and val_str.endswith("}")) or (
        val_str.startswith("[") and val_str.endswith("]")
    ):
        try:
            return json.loads(val_str)
        except Exception:
            pass

    # Try resolving as file path
    try:
        p = Path(val_str)
        if p.exists() and p.is_file():
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass

    return val


class CandidateSkill(BaseModel):
    name: str = Field(..., description="Display name of the candidate's skill")
    category_code: Optional[str] = Field(None, description="Category code (e.g., SQL, OS, COD, COMM)")
    evidence: Optional[str] = Field(None, description="Extracted resume evidence supporting the skill")
    confidence: Optional[str] = Field(None, description="Confidence level: high, medium, low")
    evidence_verified: Optional[bool] = Field(None, description="Whether the evidence has been verified")
    source_section: Optional[str] = Field(None, description="Resume section (e.g., technical_skills, projects)")

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, value: Any) -> str:
        if not isinstance(value, str):
            value = str(value) if value is not None else ""
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Skill name cannot be empty")
        return cleaned

    @field_validator("confidence", mode="before")
    @classmethod
    def validate_confidence(cls, value: Any) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            score = float(value)
            if score > 1.0:
                score = score / 100.0
            if score >= 0.7:
                return "high"
            if score >= 0.4:
                return "medium"
            return "low"
        cleaned = str(value).strip().lower()
        return cleaned if cleaned else None

    @field_validator("evidence_verified", mode="before")
    @classmethod
    def validate_evidence_verified(cls, value: Any) -> Optional[bool]:
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        val_str = str(value).strip().lower()
        if val_str in ("true", "1", "yes", "verified"):
            return True
        if val_str in ("false", "0", "no", "unverified"):
            return False
        return None

    @model_validator(mode="before")
    @classmethod
    def adapt_role3_skill(cls, data: Any) -> Any:
        if isinstance(data, str):
            return {"name": data}
        if isinstance(data, dict):
            adapted = dict(data)
            # Map Role 3 'skill_name', 'skill', 'title', etc. to 'name'
            if "name" not in adapted:
                for k in ("skill_name", "skill", "title", "skill_title", "label"):
                    if adapted.get(k):
                        adapted["name"] = adapted[k]
                        break

            # Map category
            if not adapted.get("category_code"):
                for k in ("category", "category_name", "cat"):
                    if adapted.get(k):
                        adapted["category_code"] = str(adapted[k]).strip()
                        break

            # Map evidence
            if not adapted.get("evidence"):
                for k in ("proof", "snippet", "snippets", "resume_evidence", "context", "notes"):
                    if adapted.get(k):
                        ev = adapted[k]
                        if isinstance(ev, list):
                            adapted["evidence"] = ", ".join(str(x) for x in ev)
                        else:
                            adapted["evidence"] = str(ev)
                        break

            # Map verified
            if adapted.get("evidence_verified") is None:
                for k in ("verified", "is_verified"):
                    if adapted.get(k) is not None:
                        adapted["evidence_verified"] = adapted[k]
                        break

            # Map section
            if not adapted.get("source_section"):
                for k in ("section", "resume_section"):
                    if adapted.get(k):
                        adapted["source_section"] = str(adapted[k]).strip()
                        break

            return adapted
        return data


class CandidateProfile(BaseModel):
    candidate_id: str = Field(default="CANDIDATE_ANONYMOUS", description="Unique identifier or name for the candidate")
    candidate_name: Optional[str] = Field(None, description="Display name of candidate")
    skills: List[CandidateSkill] = Field(default_factory=list, description="Skills present in profile")
    source_file: Optional[str] = Field(None, description="Original source resume file")
    source_type: Optional[str] = Field(None, description="Source type (e.g., resume)")
    schema_version: Optional[str] = Field(None, description="Schema version from Role 3")
    profile_prefill: Optional[Dict[str, Any]] = Field(None, description="Candidate details extracted by Role 3")

    @field_validator("candidate_id", mode="before")
    @classmethod
    def validate_candidate_id(cls, value: Any) -> str:
        if value is None:
            return "CANDIDATE_ANONYMOUS"
        cleaned = str(value).strip()
        if not cleaned:
            return "CANDIDATE_ANONYMOUS"
        return cleaned

    @model_validator(mode="before")
    @classmethod
    def adapt_role3_profile(cls, data: Any) -> Any:
        data = _load_json_data(data)
        if not isinstance(data, dict):
            return data
        adapted = dict(data)

        # Handle nested candidate wrappers if passed: e.g. {"role3_candidate_profiling": {...}} or {"candidate": {...}}
        for wrapper in (
            "role3_candidate_profiling",
            "candidate_profiling",
            "candidate_profile",
            "role3",
            "candidate",
            "profile",
        ):
            if wrapper in adapted and isinstance(adapted[wrapper], dict) and (
                "skills" in adapted[wrapper] or "technical_skills" in adapted[wrapper]
            ):
                nested = dict(adapted[wrapper])
                for k, v in adapted.items():
                    if k not in nested and k != wrapper:
                        nested[k] = v
                adapted = nested
                break

        # Extract profile_prefill if present
        prefill = adapted.get("profile_prefill")
        if not isinstance(prefill, dict):
            prefill = {}

        candidate_name = None
        for k in ("candidate_name", "name", "full_name", "fullName"):
            if adapted.get(k):
                candidate_name = str(adapted[k]).strip()
                break
        if not candidate_name:
            for k in ("name", "candidate_name", "full_name"):
                if prefill.get(k):
                    candidate_name = str(prefill[k]).strip()
                    break

        candidate_id = None
        for k in ("candidate_id", "id", "candidateId"):
            if adapted.get(k) is not None:
                candidate_id = str(adapted[k]).strip()
                break

        if not candidate_id:
            if candidate_name:
                candidate_id = candidate_name
            elif adapted.get("source_file"):
                candidate_id = str(adapted["source_file"]).strip()
            elif prefill.get("cv_file"):
                candidate_id = str(prefill["cv_file"]).strip()
            elif prefill.get("email"):
                candidate_id = str(prefill["email"]).strip()
            else:
                candidate_id = "CANDIDATE_ANONYMOUS"

        adapted["candidate_id"] = candidate_id
        if candidate_name and "candidate_name" not in adapted:
            adapted["candidate_name"] = candidate_name
        elif not adapted.get("candidate_name") and candidate_id != "CANDIDATE_ANONYMOUS":
            adapted["candidate_name"] = candidate_id

        # Map skills if candidate profile provided skills in alternative keys
        if "skills" not in adapted:
            for k in (
                "technical_skills",
                "skills_list",
                "candidate_skills",
                "extracted_skills",
                "profile_skills",
                "skills_extracted",
            ):
                if k in adapted:
                    adapted["skills"] = adapted[k]
                    break

        # If skills is a dictionary mapping category -> list of skills: flatten it
        if isinstance(adapted.get("skills"), dict):
            flattened = []
            for cat, skill_items in adapted["skills"].items():
                if isinstance(skill_items, list):
                    for item in skill_items:
                        if isinstance(item, str):
                            flattened.append({"name": item, "category_code": cat})
                        elif isinstance(item, dict):
                            item_copy = dict(item)
                            item_copy.setdefault("category_code", cat)
                            flattened.append(item_copy)
            adapted["skills"] = flattened

        return adapted


class RequiredSkill(BaseModel):
    name: str = Field(..., description="Display name of the required skill")
    category_code: Optional[str] = Field(None, description="Category code (e.g., SQL, OS, SWE)")
    weight: float = Field(1.0, ge=0.0, description="Importance weight (non-negative, default 1.0)")
    importance: Optional[str] = Field(None, description="e.g., required, preferred")

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, value: Any) -> str:
        if not isinstance(value, str):
            value = str(value) if value is not None else ""
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Required skill name cannot be empty")
        return cleaned

    @field_validator("weight", mode="before")
    @classmethod
    def validate_weight(cls, value: Any) -> float:
        if value is None:
            return 1.0
        try:
            val_float = float(value)
        except (ValueError, TypeError):
            raise ValueError(f"Invalid weight: {value}")
        if val_float < 0:
            raise ValueError(f"Weight cannot be negative: {val_float}")
        return val_float

    @model_validator(mode="before")
    @classmethod
    def adapt_role1_skill(cls, data: Any) -> Any:
        if isinstance(data, str):
            return {"name": data}
        if isinstance(data, dict):
            adapted = dict(data)
            # Map Role 1 'skill_name', 'skill', 'title', etc. to 'name'
            if "name" not in adapted:
                for k in ("skill_name", "skill", "title", "skill_title", "label"):
                    if adapted.get(k):
                        adapted["name"] = adapted[k]
                        break

            # Map category
            if not adapted.get("category_code"):
                for k in ("category", "category_name", "cat"):
                    if adapted.get(k):
                        adapted["category_code"] = str(adapted[k]).strip()
                        break

            # Map importance
            if not adapted.get("importance"):
                for k in ("priority", "type", "requirement_level", "level"):
                    if adapted.get(k):
                        adapted["importance"] = str(adapted[k]).strip().lower()
                        break

            # Normalize importance keywords
            imp = str(adapted.get("importance") or "").strip().lower()
            if imp in ("mandatory", "must_have", "must-have", "must have", "essential", "core"):
                adapted["importance"] = "required"
            elif imp in (
                "preferred",
                "optional",
                "nice_to_have",
                "nice-to-have",
                "nice to have",
                "good_to_have",
                "secondary",
            ):
                adapted["importance"] = "preferred"

            # If importance is 'preferred' and weight was not specified, default to 0.5
            if "weight" not in adapted:
                if adapted.get("importance") == "preferred":
                    adapted["weight"] = 0.5
                else:
                    adapted["weight"] = 1.0

            return adapted
        return data


class JobRequirements(BaseModel):
    job_id: str = Field(default="JOB_DEFAULT", description="Unique job ID or file identifier")
    job_title: str = Field(default="Target Role", description="Job role or title")
    company: Optional[str] = Field(None, description="Hiring company name")
    required_skills: List[RequiredSkill] = Field(default_factory=list, description="List of required skills")
    file: Optional[str] = Field(None, description="Source job description file")
    output_file: Optional[str] = Field(None, description="Role 1 output file name")
    category_breakdown: Optional[Dict[str, int]] = Field(None, description="Category count breakdown from Role 1")
    total_skills: Optional[int] = Field(None, description="Total skills reported by Role 1")

    @field_validator("job_id", mode="before")
    @classmethod
    def validate_job_id(cls, value: Any) -> str:
        if value is None:
            return "JOB_DEFAULT"
        cleaned = str(value).strip()
        if not cleaned:
            return "JOB_DEFAULT"
        return cleaned

    @field_validator("job_title", mode="before")
    @classmethod
    def validate_job_title(cls, value: Any) -> str:
        if value is None:
            return "Target Role"
        cleaned = str(value).strip()
        if not cleaned:
            return "Target Role"
        return cleaned

    @model_validator(mode="before")
    @classmethod
    def adapt_role1_job(cls, data: Any) -> Any:
        data = _load_json_data(data)
        if not isinstance(data, dict):
            return data
        adapted = dict(data)

        # Handle nested job wrappers: e.g. {"role1_jd_analytics": {...}}
        for wrapper in ("role1_jd_analytics", "jd_analytics", "job_requirements", "role1", "job", "jd"):
            if wrapper in adapted and isinstance(adapted[wrapper], dict) and (
                "skills" in adapted[wrapper] or "required_skills" in adapted[wrapper]
            ):
                nested = dict(adapted[wrapper])
                for k, v in adapted.items():
                    if k not in nested and k != wrapper:
                        nested[k] = v
                adapted = nested
                break

        # Map job_id from Role 1 output_file, file, id
        if "job_id" not in adapted:
            for k in ("output_file", "file", "id", "job_id", "jobId", "job_file", "jd_file"):
                if adapted.get(k) is not None:
                    adapted["job_id"] = str(adapted[k]).strip()
                    break
            if "job_id" not in adapted:
                adapted["job_id"] = "JOB_DEFAULT"

        # Map job_title from Role 1 role, title, job_title, etc.
        if "job_title" not in adapted:
            for k in ("role", "title", "job_title", "job_name", "position", "designation"):
                if adapted.get(k):
                    adapted["job_title"] = str(adapted[k]).strip()
                    break
            if "job_title" not in adapted:
                adapted["job_title"] = "Target Role"

        # Map company
        if "company" not in adapted:
            for k in ("company", "company_name", "organization", "client"):
                if adapted.get(k):
                    adapted["company"] = str(adapted[k]).strip()
                    break

        # Map required_skills from skills, job_skills, etc.
        if "required_skills" not in adapted:
            for k in (
                "skills",
                "job_skills",
                "required_skills",
                "technical_skills",
                "extracted_skills",
                "skills_required",
            ):
                if k in adapted:
                    adapted["required_skills"] = adapted[k]
                    break

            if "required_skills" not in adapted and "must_have_skills" in adapted:
                must_have = adapted.get("must_have_skills") or []
                good_to_have = adapted.get("good_to_have_skills") or adapted.get("nice_to_have_skills") or []
                combined = []
                for s in must_have:
                    if isinstance(s, dict):
                        item = dict(s)
                        item.setdefault("importance", "required")
                        combined.append(item)
                    elif isinstance(s, str):
                        combined.append({"name": s, "importance": "required"})
                for s in good_to_have:
                    if isinstance(s, dict):
                        item = dict(s)
                        item.setdefault("importance", "preferred")
                        item.setdefault("weight", 0.5)
                        combined.append(item)
                    elif isinstance(s, str):
                        combined.append({"name": s, "importance": "preferred", "weight": 0.5})
                adapted["required_skills"] = combined

        # If required_skills is a dict of category -> list of skills
        if isinstance(adapted.get("required_skills"), dict):
            flattened = []
            for cat, skill_items in adapted["required_skills"].items():
                if isinstance(skill_items, list):
                    for item in skill_items:
                        if isinstance(item, str):
                            flattened.append({"name": item, "category_code": cat})
                        elif isinstance(item, dict):
                            item_copy = dict(item)
                            item_copy.setdefault("category_code", cat)
                            flattened.append(item_copy)
            adapted["required_skills"] = flattened

        return adapted


class SkillMatchRequest(BaseModel):
    candidate_profile: CandidateProfile = Field(
        ..., description="Candidate profile from Role 3 (Candidate Profiling)"
    )
    job_requirements: JobRequirements = Field(
        ..., description="Job requirements from Role 1 (JD Analytics)"
    )

    @model_validator(mode="before")
    @classmethod
    def adapt_request(cls, data: Any) -> Any:
        data = _load_json_data(data)

        # Case 1: List with 2 items [role1, role3] or [role3, role1]
        if isinstance(data, list) and len(data) == 2:
            first, second = data[0], data[1]
            first_data = _load_json_data(first)
            second_data = _load_json_data(second)

            def is_role1(d: Any) -> bool:
                if isinstance(d, dict):
                    return any(
                        k in d
                        for k in (
                            "role",
                            "job_id",
                            "job_title",
                            "output_file",
                            "category_breakdown",
                            "total_skills",
                            "required_skills",
                        )
                    )
                return False

            if is_role1(first_data):
                return {"job_requirements": first_data, "candidate_profile": second_data}
            else:
                return {"job_requirements": second_data, "candidate_profile": first_data}

        if not isinstance(data, dict):
            return data

        adapted = dict(data)

        # 1. Resolve role1 / job input
        role1_val = None
        for key in (
            "job_requirements",
            "role1_jd_analytics",
            "role1_jd",
            "role1_job",
            "role1",
            "jd_analytics",
            "job_analytics",
            "jd",
            "job",
            "job_description",
            "role_1",
            "role1_output",
        ):
            if key in adapted and adapted[key] is not None:
                role1_val = adapted[key]
                break

        # Check for role1 file path keys
        if role1_val is None:
            for path_key in (
                "role1_path",
                "role1_file",
                "role1_file_path",
                "role1_filepath",
                "role1_jd_path",
                "role1_jd_file",
                "role1_jd_analytics_path",
                "role1_jd_analytics_file",
                "jd_path",
                "jd_file",
                "job_path",
                "job_file",
            ):
                if path_key in adapted and adapted[path_key]:
                    role1_val = _load_json_data(adapted[path_key])
                    break

        # 2. Resolve role3 / candidate input
        role3_val = None
        for key in (
            "candidate_profile",
            "role3_candidate_profiling",
            "role3_candidate",
            "role3_profile",
            "role3",
            "candidate_profiling",
            "candidate_profile_builder",
            "profile_builder",
            "candidate",
            "profile",
            "resume",
            "role_3",
            "role3_output",
        ):
            if key in adapted and adapted[key] is not None:
                role3_val = adapted[key]
                break

        # Check for role3 file path keys
        if role3_val is None:
            for path_key in (
                "role3_path",
                "role3_file",
                "role3_file_path",
                "role3_filepath",
                "role3_candidate_path",
                "role3_candidate_file",
                "role3_candidate_profiling_path",
                "role3_candidate_profiling_file",
                "candidate_path",
                "candidate_file",
                "profile_path",
                "profile_file",
                "resume_path",
                "resume_file",
            ):
                if path_key in adapted and adapted[path_key]:
                    role3_val = _load_json_data(adapted[path_key])
                    break

        # Resolve strings / file paths if strings were passed
        if isinstance(role1_val, str):
            role1_val = _load_json_data(role1_val)
        if isinstance(role3_val, str):
            role3_val = _load_json_data(role3_val)

        if role1_val is not None:
            adapted["job_requirements"] = role1_val
        if role3_val is not None:
            adapted["candidate_profile"] = role3_val

        return adapted


class SkillDetail(BaseModel):
    skill: str = Field(..., description="Skill display name as specified in requirement")
    category_code: Optional[str] = Field(None, description="Category code if available")
    status: Literal["matched", "missing_or_unverified"] = Field(..., description="Match status")
    explanation: str = Field(..., description="Factual, explainable justification")
    candidate_skill_matched: Optional[str] = Field(None, description="Matched skill name from profile")
    confidence: Optional[str] = Field(None, description="Candidate confidence (high, medium, low)")
    evidence: Optional[str] = Field(None, description="Candidate evidence snippet")
    evidence_verified: Optional[bool] = Field(None, description="Candidate evidence verified status")


class SkillMatchResponse(BaseModel):
    candidate_id: str = Field(..., description="Candidate ID or name")
    candidate_name: Optional[str] = Field(None, description="Candidate display name")
    job_id: str = Field(..., description="Job ID or file identifier")
    job_title: str = Field(..., description="Job title or role")
    company: Optional[str] = Field(None, description="Hiring company name")
    match_score: float = Field(..., description="Match percentage score from 0.0 to 100.0")
    total_required_skills: int = Field(..., description="Total count of unique required skills")
    matched_skills_count: int = Field(..., description="Count of matched required skills")
    matched_skills: List[str] = Field(..., description="List of matched skill names")
    missing_or_unverified_skills: List[str] = Field(..., description="List of missing/unverified skill names")
    additional_candidate_skills: List[str] = Field(..., description="Candidate skills not listed in job requirements")
    skill_details: List[SkillDetail] = Field(..., description="Per-skill detailed explanations")
    summary: str = Field(..., description="Human-readable factual summary")
    category_summary: Optional[Dict[str, Dict[str, int]]] = Field(
        None, description="Breakdown of matched vs required per category code"
    )
    role1_file: Optional[str] = Field(None, description="Original Role 1 JD file if available")
    role3_file: Optional[str] = Field(None, description="Original Role 3 Candidate file if available")
