from fastapi import APIRouter, HTTPException, status
from app.schemas.skill_match import SkillMatchRequest, SkillMatchResponse
from app.services.matcher import match_candidate_to_job

router = APIRouter(prefix="/api/v1", tags=["Skill Matching"])


@router.post(
    "/skill-match",
    response_model=SkillMatchResponse,
    status_code=status.HTTP_200_OK,
    summary="Match Role 1 (JD Analytics) with Role 3 (Candidate Profiling)",
    description=(
        "Compares a candidate profile against job requirements, computes a deterministic match score, "
        "identifies matched, missing/unverified, and additional skills, and returns factual justifications.\n\n"
        "**Flexible Input Formats Accepted**:\n"
        "1. **Role 1 & Role 3 Direct Format**:\n"
        "   `{\"role1_jd_analytics\": {...}, \"role3_candidate_profiling\": {...}}` or `{\"role1\": {...}, \"role3\": {...}}`\n"
        "2. **File Path References**:\n"
        "   `{\"role1_path\": \"sample_data/role1_job_sample.json\", \"role3_path\": \"sample_data/role3_candidate_sample.json\"}`\n"
        "3. **Standard / Conceptual Format**:\n"
        "   `{\"candidate_profile\": {...}, \"job_requirements\": {...}}`"
    ),
)
@router.post(
    "/role1-role3-match",
    response_model=SkillMatchResponse,
    status_code=status.HTTP_200_OK,
    summary="Match Role 1 JD Analytics against Role 3 Candidate Profiling (Alias)",
    description="Dedicated alias endpoint for matching Role 1 JD Analytics output against Role 3 Candidate Profiling output.",
)
@router.post(
    "/match",
    response_model=SkillMatchResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
def skill_match_endpoint(request: SkillMatchRequest) -> SkillMatchResponse:
    try:
        result = match_candidate_to_job(
            candidate_profile=request.candidate_profile,
            job_requirements=request.job_requirements,
        )
        return result
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve),
        )
    except Exception as e:
        # Prevent leaking raw system exception details
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while evaluating skill match.",
        )
