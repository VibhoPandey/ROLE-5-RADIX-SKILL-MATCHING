import re
from typing import Dict

# Explicit, documented alias dictionary for known equivalent skill names
KNOWN_ALIASES: Dict[str, str] = {
    # JavaScript / TypeScript / Node
    "js": "javascript",
    "javascript": "javascript",
    "ts": "typescript",
    "typescript": "typescript",
    "react": "react",
    "reactjs": "react",
    "react.js": "react",
    "node": "node.js",
    "nodejs": "node.js",
    "node.js": "node.js",

    # Python
    "py": "python",
    "python": "python",
    "python3": "python",

    # Languages
    "cpp": "c++",
    "c++": "c++",
    "c/c++": "c++",
    "c#": "c#",
    "csharp": "c#",
    "golang": "golang",
    "go": "golang",

    # Web & Frontend
    "html": "html",
    "html5": "html",
    "css": "css",
    "css3": "css",

    # Databases
    "postgres": "postgresql",
    "postgresql": "postgresql",
    "psql": "postgresql",
    "mysql": "mysql",
    "sql": "sql",
    "mongodb": "mongodb",
    "mongo": "mongodb",

    # APIs & Web Services
    "rest": "rest api",
    "rest api": "rest api",
    "rest apis": "rest api",
    "restful": "rest api",
    "restful api": "rest api",
    "restful apis": "rest api",

    # Operating Systems
    "linux": "linux",
    "linux basics": "linux",
    "linux os": "linux",
    "unix": "unix",
    "bash": "shell scripting",
    "shell": "shell scripting",
    "shell scripting": "shell scripting",

    # Networking
    "networking": "computer networks",
    "networking fundamentals": "computer networks",
    "computer networks": "computer networks",
    "computer networking": "computer networks",
    "network fundamentals": "computer networks",

    # Cloud & DevOps
    "k8s": "kubernetes",
    "kubernetes": "kubernetes",
    "aws": "aws",
    "amazon web services": "aws",
    "gcp": "google cloud",
    "google cloud platform": "google cloud",
    "google cloud": "google cloud",
    "docker": "docker",
    "ci/cd": "ci/cd",
    "cicd": "ci/cd",
    "ci cd": "ci/cd",

    # Office & Tools
    "excel": "excel",
    "ms excel": "excel",
    "microsoft excel": "excel",
    "ticketing tools": "ticketing tools",
    "ticketing systems": "ticketing tools",
    "ticketing": "ticketing tools",

    # Professional & General Skills
    "software engineering": "software engineering",
    "software development": "software engineering",
    "swe": "software engineering",
    "problem solving": "aptitude and problem solving",
    "problem-solving": "aptitude and problem solving",
    "aptitude": "aptitude and problem solving",
    "aptitude and problem solving": "aptitude and problem solving",
    "communication": "communication",
    "communication skills": "communication",

    # Machine Learning / AI
    "ml": "machine learning",
    "machine learning": "machine learning",
    "ai": "artificial intelligence",
    "artificial intelligence": "artificial intelligence",

    # Version Control (Note: git is distinct from github/gitlab)
    "git": "git",
    "github": "github",
    "gitlab": "gitlab",
}


def normalize_skill_name(name: str) -> str:
    """
    Normalizes a skill name for deterministic, case-insensitive comparison.

    Pipeline:
    1. Strip leading and trailing whitespace.
    2. Lowercase all characters.
    3. Collapse multiple whitespace characters into a single space.
    4. Remove parenthetical descriptions (e.g. 'SQL (basic)' -> 'sql').
    5. Resolve known aliases via KNOWN_ALIASES.

    Does NOT equate distinct skills (e.g., Java != JavaScript, Git != GitHub).
    """
    if not name or not isinstance(name, str):
        return ""

    raw = name.strip().lower()
    # Normalize internal whitespace
    raw = re.sub(r"\s+", " ", raw)

    # Check direct alias match first
    if raw in KNOWN_ALIASES:
        return KNOWN_ALIASES[raw]

    # Strip harmless parenthetical annotations, e.g. "sql (basic)" -> "sql"
    without_parens = re.sub(r"\s*\([^)]*\)", "", raw).strip()
    without_parens = re.sub(r"\s+", " ", without_parens)
    if without_parens in KNOWN_ALIASES:
        return KNOWN_ALIASES[without_parens]

    return without_parens if without_parens else raw
