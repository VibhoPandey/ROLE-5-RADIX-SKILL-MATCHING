from fastapi import APIRouter, HTTPException, status
from app.schemas.skill_match import SkillMatchRequest, SkillMatchResponse
from app.services.matcher import match_candidate_to_job

router = APIRouter(prefix="/api/v1", tags=["Skill Matching"])


@router.post(
    "/skill-match",
    response_model=SkillMatchResponse,
    status_code=status.HTTP_200_OK,
    summary="Match Candidate Profile against Job Requirements",
    description=(
        "Compares a candidate's profile (from Role 3) against the requirements of a specific job "
        "(from Role 1), computes a deterministic match score, identifies matched, missing/unverified, "
        "and additional skills, and provides factual per-skill explanations."
    ),
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

