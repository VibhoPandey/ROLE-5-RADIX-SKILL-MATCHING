from collections import defaultdict
from typing import Dict, List, Set

from app.schemas.skill_match import (
    CandidateProfile,
    CandidateSkill,
    JobRequirements,
    RequiredSkill,
    SkillDetail,
    SkillMatchResponse,
)
from app.services.normalizer import normalize_skill_name
from app.services.scorer import calculate_match_score


def match_candidate_to_job(
    candidate_profile: CandidateProfile,
    job_requirements: JobRequirements,
) -> SkillMatchResponse:
    """
    Executes the deterministic skill matching pipeline:
    1. Normalizes and indexes candidate skills.
    2. Deduplicates required skills.
    3. Evaluates each required skill against candidate profile.
    4. Identifies matched, missing/unverified, and additional skills.
    5. Calculates deterministic match score.
    6. Builds factual explanations and summary.
    """
    # 1. Normalize and index candidate skills
    # Map normalized_key -> CandidateSkill
    candidate_skill_map: Dict[str, CandidateSkill] = {}
    candidate_norm_to_original: Dict[str, str] = {}

    confidence_rank = {"high": 3, "medium": 2, "low": 1}

    for skill in candidate_profile.skills:
        norm_key = normalize_skill_name(skill.name)
        if not norm_key:
            continue

        if norm_key in candidate_skill_map:
            # If candidate lists the same skill multiple times, retain the one with higher confidence/verification
            existing = candidate_skill_map[norm_key]
            existing_rank = confidence_rank.get(str(existing.confidence).lower(), 0)
            new_rank = confidence_rank.get(str(skill.confidence).lower(), 0)
            if new_rank > existing_rank or (skill.evidence_verified and not existing.evidence_verified):
                candidate_skill_map[norm_key] = skill
                candidate_norm_to_original[norm_key] = skill.name
        else:
            candidate_skill_map[norm_key] = skill
            candidate_norm_to_original[norm_key] = skill.name

    # 2. Deduplicate required skills by normalized skill name, preserving order
    deduped_requirements: List[RequiredSkill] = []
    seen_req_keys: Set[str] = set()

    for req in job_requirements.required_skills:
        req_norm = normalize_skill_name(req.name)
        if not req_norm:
            continue
        if req_norm not in seen_req_keys:
            seen_req_keys.add(req_norm)
            deduped_requirements.append(req)

    # 3. Match evaluation
    matched_skills: List[str] = []
    missing_skills: List[str] = []
    skill_details: List[SkillDetail] = []
    matched_req_names: Set[str] = set()
    matched_cand_norm_keys: Set[str] = set()

    # Category breakdown tracker
    category_tracker = defaultdict(lambda: {"required": 0, "matched": 0})

    for req in deduped_requirements:
        req_norm = normalize_skill_name(req.name)
        category = req.category_code

        if category:
            category_tracker[category]["required"] += 1

        if req_norm in candidate_skill_map:
            cand_skill = candidate_skill_map[req_norm]
            matched_req_names.add(req.name)
            matched_cand_norm_keys.add(req_norm)
            matched_skills.append(req.name)

            if category:
                category_tracker[category]["matched"] += 1

            # Construct factual explanation
            explanation_parts = [f"'{req.name}' is present in the candidate profile"]
            if cand_skill.source_section:
                explanation_parts.append(f"under '{cand_skill.source_section}'")
            if cand_skill.evidence:
                explanation_parts.append(f"(evidence: '{cand_skill.evidence}')")
            if cand_skill.confidence:
                explanation_parts.append(f"with {cand_skill.confidence} confidence")

            explanation = " ".join(explanation_parts) + "."

            skill_details.append(
                SkillDetail(
                    skill=req.name,
                    category_code=category or cand_skill.category_code,
                    status="matched",
                    explanation=explanation,
                    candidate_skill_matched=cand_skill.name,
                    confidence=cand_skill.confidence,
                    evidence=cand_skill.evidence,
                    evidence_verified=cand_skill.evidence_verified,
                )
            )
        else:
            missing_skills.append(req.name)
            skill_details.append(
                SkillDetail(
                    skill=req.name,
                    category_code=category,
                    status="missing_or_unverified",
                    explanation=f"'{req.name}' was not found in the available candidate profile.",
                    candidate_skill_matched=None,
                    confidence=None,
                    evidence=None,
                    evidence_verified=None,
                )
            )

    # 4. Identify additional candidate skills (skills candidate has that job did not require)
    additional_candidate_skills: List[str] = []
    for norm_key, cand_skill in candidate_skill_map.items():
        if norm_key not in matched_cand_norm_keys:
            additional_candidate_skills.append(cand_skill.name)

    # 5. Calculate match score
    match_score = calculate_match_score(
        required_skills=deduped_requirements,
        matched_skill_names=matched_req_names,
    )

    # 6. Build summary
    total_req = len(deduped_requirements)
    total_matched = len(matched_skills)
    if total_req == 0:
        summary = "No required skills were specified in the job requirements."
    else:
        summary = f"{total_matched} of {total_req} required skills were found in the candidate profile."

    # Format category summary if categories were present
    category_summary_out = dict(category_tracker) if category_tracker else None

    return SkillMatchResponse(
        candidate_id=candidate_profile.candidate_id,
        candidate_name=candidate_profile.candidate_name,
        job_id=job_requirements.job_id,
        job_title=job_requirements.job_title,
        company=job_requirements.company,
        match_score=match_score,
        total_required_skills=total_req,
        matched_skills_count=total_matched,
        matched_skills=matched_skills,
        missing_or_unverified_skills=missing_skills,
        additional_candidate_skills=additional_candidate_skills,
        skill_details=skill_details,
        summary=summary,
        category_summary=category_summary_out,
    )

