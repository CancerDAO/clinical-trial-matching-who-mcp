from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"
CONFLICT_MARKERS = ("<<<<<<<", "=======", ">>>>>>>")
IGNORED_PARTS = {".git", "__pycache__", ".pytest_cache"}
FORBIDDEN_SUFFIXES = {".pyc", ".db", ".sqlite", ".sqlite3"}
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
PUBLIC_FRONTMATTER_FIELDS = {"name", "description"}


def repository_files() -> list[Path]:
    return [
        path
        for path in ROOT.rglob("*")
        if path.is_file() and not (set(path.relative_to(ROOT).parts) & IGNORED_PARTS)
    ]


def parse_frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError("missing opening YAML frontmatter delimiter")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ValueError("missing closing YAML frontmatter delimiter")
    values: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if line and not line.startswith((" ", "\t")) and ":" in line:
            key, value = line.split(":", 1)
            values[key.strip()] = value.strip().strip("\"'")
    return values


def validate() -> list[str]:
    errors: list[str] = []
    files = repository_files()

    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            errors.append(f"generated or database artifact is not allowed: {rel}")
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for marker in CONFLICT_MARKERS:
            if any(line.startswith(marker) for line in text.splitlines()):
                errors.append(f"unresolved merge marker {marker!r}: {rel}")

    skill_dirs = sorted(path for path in SKILLS_DIR.iterdir() if path.is_dir())
    if not skill_dirs:
        errors.append("no skills found under skills/")
    for skill_dir in skill_dirs:
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            errors.append(f"skill directory lacks SKILL.md: {skill_dir.name}")
            continue
        try:
            frontmatter = parse_frontmatter(skill_file)
        except ValueError as exc:
            errors.append(f"{skill_file.relative_to(ROOT).as_posix()}: {exc}")
            continue
        unsupported_fields = sorted(set(frontmatter) - PUBLIC_FRONTMATTER_FIELDS)
        if unsupported_fields:
            errors.append(
                f"unsupported public skill frontmatter fields in {skill_dir.name}: "
                + ", ".join(unsupported_fields)
            )
        name = frontmatter.get("name", "")
        description = frontmatter.get("description", "")
        if name != skill_dir.name:
            errors.append(f"skill name {name!r} does not match directory {skill_dir.name!r}")
        if not NAME_RE.fullmatch(name) or len(name) > 64:
            errors.append(f"invalid skill name: {name!r}")
        if not description or len(description) > 1024:
            errors.append(f"skill description must contain 1-1024 characters: {skill_dir.name}")

        text = skill_file.read_text(encoding="utf-8")

        for target in LINK_RE.findall(text):
            target = target.split("#", 1)[0].strip()
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            resolved = (skill_file.parent / target).resolve()
            if not resolved.exists():
                errors.append(
                    f"broken local link in {skill_file.relative_to(ROOT).as_posix()}: {target}"
                )

    for path in files:
        if path.suffix.lower() == ".json":
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                errors.append(f"invalid JSON {path.relative_to(ROOT).as_posix()}: {exc}")
    return errors


def main() -> int:
    errors = validate()
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(f"Repository validation passed: {len(list(SKILLS_DIR.glob('*/SKILL.md')))} skills")
    return 0


if __name__ == "__main__":
    sys.exit(main())
