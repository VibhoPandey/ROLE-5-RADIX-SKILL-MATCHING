from typing import List, Set
from app.schemas.skill_match import RequiredSkill


def calculate_match_score(
    required_skills: List[RequiredSkill],
    matched_skill_names: Set[str],
) -> float:
    """
    Calculates a deterministic, explainable match score as a percentage (0.0 to 100.0).

    Rules:
    - Deduplication: Caller must provide deduplicated required skills.
    - Zero Division: If total required skills is 0, score is defined as 0.0 (not 100.0).
    - Unweighted Baseline: (Matched Required Skills / Total Required Skills) * 100.
    - Weighted Mode: When custom weights are present (weight != 1.0),
      Score = (Sum of weights of matched skills / Total sum of weights) * 100.
    - Precision: Rounded to two decimal places.
    """
    if not required_skills:
        return 0.0

    total_weight = sum(skill.weight for skill in required_skills)
    if total_weight <= 0:
        return 0.0

    has_custom_weights = any(skill.weight != 1.0 for skill in required_skills)

    if not has_custom_weights:
        # Standard unweighted baseline
        matched_count = sum(1 for skill in required_skills if skill.name in matched_skill_names)
        raw_score = (matched_count / len(required_skills)) * 100.0
    else:
        # Weighted formula
        matched_weight = sum(
            skill.weight for skill in required_skills if skill.name in matched_skill_names
        )
        raw_score = (matched_weight / total_weight) * 100.0

    return round(raw_score, 2)

