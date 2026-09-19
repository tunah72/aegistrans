"""Medical Specialty Profile manager for AegisTrans."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import NamedTuple

logger = logging.getLogger(__name__)


class ProfileAssets(NamedTuple):
    name: str
    dir_path: Path
    system_prompt: Path | None
    glossary: Path | None


def find_project_root() -> Path:
    """Resolve the AegisTrans root directory."""
    return Path(__file__).resolve().parents[1]


def get_profiles_base_dir(root: Path | None = None) -> Path:
    """Return the medical-translation/profiles directory."""
    project_root = root or find_project_root()
    return project_root / "medical-translation" / "profiles"


def list_available_profiles(root: Path | None = None) -> list[str]:
    """List names of all available specialty profiles."""
    base_dir = get_profiles_base_dir(root)
    if not base_dir.is_dir():
        return []
    profiles = [
        p.name
        for p in base_dir.iterdir()
        if p.is_dir() and not p.name.startswith(".")
    ]
    return sorted(profiles)


def resolve_profile_dir(profile_name_or_path: str, root: Path | None = None) -> Path | None:
    """Resolve a profile name or directory path to its directory Path.

    Checks:
    1. medical-translation/profiles/<name>
    2. Path given directly as absolute or relative path
    3. Project root / <name>
    """
    if not profile_name_or_path:
        return None

    base_dir = get_profiles_base_dir(root)
    candidate = base_dir / profile_name_or_path
    if candidate.is_dir():
        return candidate

    direct_path = Path(profile_name_or_path)
    if direct_path.is_dir():
        return direct_path

    project_root = root or find_project_root()
    root_candidate = project_root / profile_name_or_path
    if root_candidate.is_dir():
        return root_candidate

    return None


def load_profile(
    profile_name_or_path: str,
    root: Path | None = None,
) -> ProfileAssets | None:
    """Load a profile's assets (system_prompt and glossary_base).

    Returns ProfileAssets if directory found, else None.
    """
    p_dir = resolve_profile_dir(profile_name_or_path, root)
    if not p_dir:
        return None

    prompt_path = p_dir / "system_prompt.txt"
    glossary_path = p_dir / "glossary_base.jsonl"

    return ProfileAssets(
        name=p_dir.name,
        dir_path=p_dir,
        system_prompt=prompt_path if prompt_path.is_file() else None,
        glossary=glossary_path if glossary_path.is_file() else None,
    )


def validate_profile(profile_dir: Path) -> dict[str, str | int | bool]:
    """Validate a profile directory structure and glossary contents."""
    result: dict[str, str | int | bool] = {
        "valid": False,
        "name": profile_dir.name,
        "has_prompt": False,
        "has_glossary": False,
        "glossary_terms": 0,
        "error": "",
    }

    if not profile_dir.is_dir():
        result["error"] = f"Directory not found: {profile_dir}"
        return result

    prompt_file = profile_dir / "system_prompt.txt"
    if prompt_file.is_file() and prompt_file.stat().st_size > 0:
        result["has_prompt"] = True
    else:
        result["error"] = "Missing or empty system_prompt.txt"
        return result

    glossary_file = profile_dir / "glossary_base.jsonl"
    if glossary_file.is_file():
        result["has_glossary"] = True
        count = 0
        with open(glossary_file, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    if "en" not in data or "vi" not in data:
                        result["error"] = f"Line {line_no} in glossary missing 'en' or 'vi'"
                        return result
                    count += 1
                except json.JSONDecodeError as exc:
                    result["error"] = f"Line {line_no} invalid JSON: {exc}"
                    return result
        result["glossary_terms"] = count
    else:
        result["error"] = "Missing glossary_base.jsonl"
        return result

    result["valid"] = True
    return result
