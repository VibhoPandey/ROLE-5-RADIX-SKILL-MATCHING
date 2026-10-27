from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


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
            raise ValueError("Skill name must be a string")
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Skill name cannot be empty")
        return cleaned

    @model_validator(mode="before")
    @classmethod
    def adapt_role3_skill(cls, data: Any) -> Any:
        if isinstance(data, str):
            return {"name": data}
        if isinstance(data, dict):
            adapted = dict(data)
            # Map Role 3 'skill_name' or legacy 'skill' to 'name'
            if "name" not in adapted:
                if "skill_name" in adapted:
                    adapted["name"] = adapted["skill_name"]
                elif "skill" in adapted:
                    adapted["name"] = adapted["skill"]
            return adapted
        return data


class CandidateProfile(BaseModel):
    candidate_id: str = Field(..., description="Unique identifier or name for the candidate")
    candidate_name: Optional[str] = Field(None, description="Display name of candidate")
    skills: List[CandidateSkill] = Field(default_factory=list, description="Skills present in profile")

    @field_validator("candidate_id", mode="before")
    @classmethod
    def validate_candidate_id(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("candidate_id must be a string")
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("candidate_id cannot be empty")
        return cleaned

    @model_validator(mode="before")
    @classmethod
    def adapt_role3_profile(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        adapted = dict(data)

        # Derive candidate_id and candidate_name from Role 3 format if not explicitly provided
        if "candidate_id" not in adapted:
            prefill = adapted.get("profile_prefill")
            if isinstance(prefill, dict) and prefill.get("name"):
                name = str(prefill["name"]).strip()
                adapted["candidate_id"] = name
                adapted["candidate_name"] = name
            elif adapted.get("source_file"):
                src = str(adapted["source_file"]).strip()
                adapted["candidate_id"] = src
                adapted["candidate_name"] = src
            elif adapted.get("name"):
                name = str(adapted["name"]).strip()
                adapted["candidate_id"] = name
                adapted["candidate_name"] = name

        # Map skills if candidate profile provided skills in alternative keys
        if "skills" not in adapted:
            if "technical_skills" in adapted and isinstance(adapted["technical_skills"], list):
                adapted["skills"] = adapted["technical_skills"]
            elif "skills_list" in adapted and isinstance(adapted["skills_list"], list):
                adapted["skills"] = adapted["skills_list"]

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
            raise ValueError("Required skill name must be a string")
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Required skill name cannot be empty")
        return cleaned

    @model_validator(mode="before")
    @classmethod
    def adapt_role1_skill(cls, data: Any) -> Any:
        if isinstance(data, str):
            return {"name": data}
        if isinstance(data, dict):
            adapted = dict(data)
            # Map Role 1 'skill_name' or 'skill' to 'name'
            if "name" not in adapted:
                if "skill_name" in adapted:
                    adapted["name"] = adapted["skill_name"]
                elif "skill" in adapted:
                    adapted["name"] = adapted["skill"]

            # If importance is 'preferred' and weight was not specified, default to 0.5
            if "weight" not in adapted and adapted.get("importance") == "preferred":
                adapted["weight"] = 0.5
            return adapted
        return data


class JobRequirements(BaseModel):
    job_id: str = Field(..., description="Unique job ID or file identifier")
    job_title: str = Field(..., description="Job role or title")
    company: Optional[str] = Field(None, description="Hiring company name")
    required_skills: List[RequiredSkill] = Field(default_factory=list, description="List of required skills")

    @field_validator("job_id", mode="before")
    @classmethod
    def validate_job_id(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("job_id must be a string")
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("job_id cannot be empty")
        return cleaned

    @field_validator("job_title", mode="before")
    @classmethod
    def validate_job_title(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("job_title must be a string")
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("job_title cannot be empty")
        return cleaned

    @model_validator(mode="before")
    @classmethod
    def adapt_role1_job(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        adapted = dict(data)

        # Map job_id from Role 1 output_file or file
        if "job_id" not in adapted:
            if adapted.get("output_file"):
                adapted["job_id"] = str(adapted["output_file"]).strip()
            elif adapted.get("file"):
                adapted["job_id"] = str(adapted["file"]).strip()
            elif adapted.get("id"):
                adapted["job_id"] = str(adapted["id"]).strip()

        # Map job_title from Role 1 role or title
        if "job_title" not in adapted:
            if adapted.get("role"):
                adapted["job_title"] = str(adapted["role"]).strip()
            elif adapted.get("title"):
                adapted["job_title"] = str(adapted["title"]).strip()

        # Map required_skills from skills
        if "required_skills" not in adapted and "skills" in adapted:
            adapted["required_skills"] = adapted["skills"]

        return adapted


class SkillMatchRequest(BaseModel):
    candidate_profile: CandidateProfile = Field(..., description="Candidate profile from Role 3")
    job_requirements: JobRequirements = Field(..., description="Job requirements from Role 1")


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

