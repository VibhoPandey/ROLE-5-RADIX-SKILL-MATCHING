import argparse
import json
import sys
from pathlib import Path

from app.services.matcher import match_role1_and_role3


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli",
        description=(
            "RADIX Role 5 Skill Matching Engine — "
            "Evaluates outputs from Role 1 (JD Analytics) against Role 3 (Candidate Profiling) "
            "deterministically without external LLM or database dependencies."
        ),
    )
    parser.add_argument(
        "--role1",
        "-r1",
        "--jd",
        "--job",
        required=True,
        help="Path to Role 1 (JD Analytics) JSON file or raw JSON string",
    )
    parser.add_argument(
        "--role3",
        "-r3",
        "--candidate",
        "--profile",
        required=True,
        help="Path to Role 3 (Candidate Profiling) JSON file or raw JSON string",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Optional file path to write output JSON to",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        default=True,
        help="Pretty-print JSON output (default: True)",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Output compact single-line JSON without indentation",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print a human-readable console summary instead of full JSON",
    )

    args = parser.parse_args()

    try:
        response = match_role1_and_role3(
            role1_input=args.role1,
            role3_input=args.role3,
        )
        data = response.model_dump()

        if args.summary:
            print("\n" + "=" * 60)
            print("RADIX ROLE 5: SKILL MATCHING SUMMARY")
            print("=" * 60)
            print(f"Candidate   : {response.candidate_name or response.candidate_id}")
            print(f"Job Role    : {response.job_title} ({response.company or 'N/A'})")
            print(f"Match Score : {response.match_score}%")
            print(f"Stats       : {response.matched_skills_count}/{response.total_required_skills} required skills matched")
            print(f"Matched     : {', '.join(response.matched_skills) if response.matched_skills else 'None'}")
            print(f"Missing     : {', '.join(response.missing_or_unverified_skills) if response.missing_or_unverified_skills else 'None'}")
            print(f"Additional  : {', '.join(response.additional_candidate_skills) if response.additional_candidate_skills else 'None'}")
            print(f"Summary     : {response.summary}")
            print("=" * 60 + "\n")
        else:
            indent = None if args.compact else 2
            json_text = json.dumps(data, indent=indent)

            if args.output:
                out_path = Path(args.output)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(json_text, encoding="utf-8")
                print(f"Skill match result saved to: {out_path.resolve()}")
            else:
                print(json_text)

    except Exception as exc:
        sys.stderr.write(f"Error during skill matching: {exc}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()

