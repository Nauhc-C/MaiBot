"""Core scanner and loader for standard ``SKILL.md`` skill bundles."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


_PLUGIN_DIR = Path(__file__).resolve().parent
_MAIBOT_ROOT = _PLUGIN_DIR.parents[1]
_WORKSPACE_ROOT = _MAIBOT_ROOT.parents[1]

DEFAULT_SKILL_ROOTS = [
    str(_WORKSPACE_ROOT / ".codex" / "skills"),
    str(_WORKSPACE_ROOT / ".agents" / "skills"),
    str(_MAIBOT_ROOT / ".codex" / "skills"),
    str(_MAIBOT_ROOT / ".agents" / "skills"),
]

_FRONTMATTER_DELIMITER = "---"
_WORD_RE = re.compile(r"[A-Za-z0-9_+.-]+|[\u4e00-\u9fff]+")
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", re.MULTILINE)
_MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+?\.md(?:#[^)]+)?)\)", re.IGNORECASE)
_PATH_RE = re.compile(
    r"(?:\{baseDir\}/|skills/[A-Za-z0-9_.-]+/|references/|[\w./{}-]*?)"
    r"[A-Za-z0-9_.{}-]+\.md(?:#[A-Za-z0-9_.-]+)?",
    re.IGNORECASE,
)
_SCRIPT_HINT_RE = re.compile(r"(?:^|[`\s])((?:scripts/|[\w./{}-]*scripts/)[\w./{}-]+)", re.IGNORECASE)


@dataclass(slots=True)
class SkillEntry:
    """A parsed local skill bundle."""

    name: str
    description: str
    skill_dir: Path
    skill_file: Path
    body: str
    raw_content: str
    headings: list[str]
    referenced_files: list[Path] = field(default_factory=list)
    script_files: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    mtime_ns: int = 0

    @property
    def trigger_keywords(self) -> list[str]:
        """Return compact trigger words for the resident catalog."""

        text = f"{self.name} {self.description} {' '.join(self.headings[:6])}"
        ignored = {
            "the",
            "and",
            "with",
            "when",
            "use",
            "for",
            "from",
            "this",
            "that",
            "skill",
            "skills",
            "using",
            "需要",
            "使用",
            "支持",
            "工具",
        }
        keywords: list[str] = []
        for token in _tokenize(text):
            if len(token) <= 2 or token in ignored or token in keywords:
                continue
            keywords.append(token)
            if len(keywords) >= 8:
                break
        return keywords

    def catalog_line(self) -> str:
        """Return one compact catalog line."""

        keywords = ", ".join(self.trigger_keywords)
        description = _single_line(self.description) or "(no description)"
        return f"- {self.name}: {description} | triggers: {keywords or self.name}"


class SkillBroker:
    """Scans standard skill directories and exposes catalog/search/load operations."""

    def __init__(
        self,
        skill_roots: list[str] | None = None,
        *,
        max_search_results: int = 5,
        max_body_chars: int = 20000,
        allow_reference_files: bool = True,
        allow_script_execution: bool = False,
    ) -> None:
        self.skill_roots = list(skill_roots or DEFAULT_SKILL_ROOTS)
        self.max_search_results = max(1, int(max_search_results or 5))
        self.max_body_chars = max(1000, int(max_body_chars or 20000))
        self.allow_reference_files = bool(allow_reference_files)
        self.allow_script_execution = bool(allow_script_execution)
        self._skills_by_name: dict[str, SkillEntry] = {}
        self._signature: tuple[tuple[str, int], ...] = tuple()

    def refresh(self, *, force: bool = False) -> None:
        """Refresh cached skills when the discovered ``SKILL.md`` files changed."""

        signature = self._build_signature()
        if not force and signature == self._signature:
            return

        skills: dict[str, SkillEntry] = {}
        for skill_path, _mtime_ns in signature:
            entry = self._load_skill_file(Path(skill_path))
            if entry is None:
                continue
            key = entry.name.lower()
            if key in skills:
                entry.warnings.append(f"duplicate skill name shadowed earlier entry: {entry.name}")
                continue
            skills[key] = entry

        self._skills_by_name = dict(sorted(skills.items(), key=lambda item: item[1].name.lower()))
        self._signature = signature

    def catalog(self) -> dict[str, Any]:
        """Return a compact resident catalog for planner coarse selection."""

        self.refresh()
        content = self.catalog_text()
        return {
            "success": True,
            "content": content,
            "matched_skills": [self._summary(entry) for entry in self._skills_by_name.values()],
            "safety_notes": self._global_safety_notes(),
        }

    def catalog_text(self, *, max_lines: int | None = None) -> str:
        """Return compact catalog text suitable for a tool description."""

        self.refresh()
        entries = list(self._skills_by_name.values())
        max_skill_lines = len(entries) if max_lines is None else max(0, int(max_lines))
        lines = [entry.catalog_line() for entry in entries[:max_skill_lines]]
        if max_skill_lines < len(entries):
            lines.append(f"- ... {len(entries) - max_skill_lines} more project skills omitted from this compact list")
        content = "\n".join(
            [
                f"Project skill catalog contains {len(entries)} local skills.",
                "Use skill_search(query) to narrow candidates and skill_load(name) to read SKILL.md.",
                *lines,
            ]
        )
        return content

    def search(self, query: str, *, limit: int | None = None) -> dict[str, Any]:
        """Search skills by name, description, headings, and body text."""

        self.refresh()
        query = str(query or "").strip()
        max_results = max(1, int(limit or self.max_search_results))
        if not query:
            return {
                "success": False,
                "content": "skill_search requires a non-empty query.",
                "matched_skills": [],
                "safety_notes": self._global_safety_notes(),
            }

        scored: list[tuple[float, SkillEntry]] = []
        for entry in self._skills_by_name.values():
            score = self._score(entry, query)
            if score > 0:
                scored.append((score, entry))

        scored.sort(key=lambda item: (-item[0], item[1].name.lower()))
        matches = [self._summary(entry, score=score) for score, entry in scored[:max_results]]
        if not matches:
            content = f"No local skills matched query: {query}"
        else:
            content = "\n".join(
                [
                    f"Matched {len(matches)} skill(s) for query: {query}",
                    *[
                        f"- {match['name']}: {match['description']} (score={match['score']:.1f})"
                        for match in matches
                    ],
                    "Call skill_load(name) for the selected skill before applying its workflow.",
                ]
            )
        return {
            "success": True,
            "content": content,
            "matched_skills": matches,
            "safety_notes": self._global_safety_notes(),
        }

    def load(self, name: str, *, include_references: bool = False) -> dict[str, Any]:
        """Load one skill body and optionally referenced Markdown files."""

        self.refresh()
        name = str(name or "").strip()
        entry = self._resolve_skill(name)
        if entry is None:
            return {
                "success": False,
                "content": f"Skill not found: {name}",
                "matched_skills": [],
                "skill_name": name,
                "description": "",
                "body": "",
                "referenced_files": [],
                "unsupported_capabilities": [],
                "safety_notes": self._global_safety_notes(),
            }

        body, body_truncated = _truncate(entry.raw_content, self.max_body_chars)
        references = self._load_references(entry) if include_references and self.allow_reference_files else []
        unsupported_capabilities = self._detect_unsupported_capabilities(entry)
        safety_notes = self._global_safety_notes()
        if body_truncated:
            safety_notes.append(f"SKILL.md content truncated to {self.max_body_chars} characters.")
        if include_references and not self.allow_reference_files:
            safety_notes.append("Reference file loading is disabled by configuration.")
        if entry.script_files and not self.allow_script_execution:
            safety_notes.append("Scripts are listed for awareness only and were not executed.")

        content_sections = [
            f"skill_name: {entry.name}",
            f"description: {_single_line(entry.description)}",
            "body:",
            body,
        ]
        if references:
            content_sections.append("referenced_files:")
            for reference in references:
                content_sections.append(f"--- {reference['relative_path']} ---")
                content_sections.append(str(reference["content"]))
        if unsupported_capabilities:
            content_sections.append("unsupported_capabilities:")
            content_sections.extend(f"- {item}" for item in unsupported_capabilities)
        if safety_notes:
            content_sections.append("safety_notes:")
            content_sections.extend(f"- {item}" for item in safety_notes)

        return {
            "success": True,
            "content": "\n".join(content_sections),
            "matched_skills": [self._summary(entry)],
            "skill_name": entry.name,
            "description": entry.description,
            "body": body,
            "referenced_files": references,
            "unsupported_capabilities": unsupported_capabilities,
            "safety_notes": safety_notes,
        }

    def _build_signature(self) -> tuple[tuple[str, int], ...]:
        skill_files: list[tuple[str, int]] = []
        for root in self._normalized_roots():
            if not root.is_dir():
                continue
            candidates = [path for path in root.rglob("SKILL.md") if path.is_file()]
            for skill_file in candidates:
                try:
                    stat = skill_file.stat()
                except OSError:
                    continue
                skill_files.append((str(skill_file.resolve()), int(stat.st_mtime_ns)))
        return tuple(sorted(skill_files))

    def _normalized_roots(self) -> list[Path]:
        roots: list[Path] = []
        seen: set[str] = set()
        for raw_root in self.skill_roots:
            raw_text = str(raw_root or "").strip()
            if not raw_text:
                continue
            try:
                root = Path(raw_text).expanduser().resolve()
            except OSError:
                continue
            root_key = str(root).lower()
            if root_key in seen:
                continue
            seen.add(root_key)
            roots.append(root)
        return roots

    def _load_skill_file(self, skill_file: Path) -> SkillEntry | None:
        warnings: list[str] = []
        try:
            raw_content = skill_file.read_text(encoding="utf-8")
            mtime_ns = int(skill_file.stat().st_mtime_ns)
        except OSError as exc:
            return SkillEntry(
                name=skill_file.parent.name,
                description="",
                skill_dir=skill_file.parent,
                skill_file=skill_file,
                body="",
                raw_content="",
                headings=[],
                warnings=[f"failed to read SKILL.md: {exc}"],
            )

        metadata, body, parse_warnings = _parse_skill_markdown(raw_content)
        warnings.extend(parse_warnings)
        name = str(metadata.get("name") or skill_file.parent.name).strip() or skill_file.parent.name
        description = str(metadata.get("description") or "").strip()
        referenced_files, reference_warnings = _find_referenced_markdown_files(skill_file.parent, body)
        warnings.extend(reference_warnings)
        script_files = _find_script_hints(skill_file.parent, body)
        return SkillEntry(
            name=name,
            description=description,
            skill_dir=skill_file.parent,
            skill_file=skill_file,
            body=body,
            raw_content=raw_content,
            headings=[_single_line(heading) for heading in _HEADING_RE.findall(body)],
            referenced_files=referenced_files,
            script_files=script_files,
            warnings=warnings,
            mtime_ns=mtime_ns,
        )

    def _resolve_skill(self, name: str) -> SkillEntry | None:
        if not name:
            return None
        key = name.lower()
        if key in self._skills_by_name:
            return self._skills_by_name[key]
        normalized = _normalize_name(name)
        for entry in self._skills_by_name.values():
            if _normalize_name(entry.name) == normalized or _normalize_name(entry.skill_dir.name) == normalized:
                return entry
        matches = [
            entry
            for entry in self._skills_by_name.values()
            if normalized in _normalize_name(entry.name) or normalized in _normalize_name(entry.skill_dir.name)
        ]
        return matches[0] if len(matches) == 1 else None

    def _score(self, entry: SkillEntry, query: str) -> float:
        query_normalized = query.lower()
        tokens = _tokenize(query)
        if not tokens:
            return 0.0

        name_text = entry.name.lower()
        description_text = entry.description.lower()
        heading_text = " ".join(entry.headings).lower()
        body_text = entry.body.lower()

        score = 0.0
        if query_normalized == name_text:
            score += 150.0
        if query_normalized in name_text:
            score += 70.0
        if query_normalized and query_normalized in description_text:
            score += 35.0
        for token in tokens:
            if token in name_text:
                score += 25.0
            if token in description_text:
                score += 10.0
            if token in heading_text:
                score += 5.0
            if token in body_text:
                score += min(4.0, body_text.count(token) * 0.5)
        return score

    def _summary(self, entry: SkillEntry, *, score: float | None = None) -> dict[str, Any]:
        result: dict[str, Any] = {
            "name": entry.name,
            "description": _single_line(entry.description),
            "path": str(entry.skill_dir),
            "trigger_keywords": entry.trigger_keywords,
            "referenced_files": [_relative_to_skill(entry, path) for path in entry.referenced_files],
            "script_files": [_relative_to_skill(entry, path) for path in entry.script_files],
            "warnings": list(entry.warnings),
        }
        if score is not None:
            result["score"] = score
        return result

    def _load_references(self, entry: SkillEntry) -> list[dict[str, Any]]:
        references: list[dict[str, Any]] = []
        for reference_path in entry.referenced_files:
            try:
                resolved_path = reference_path.resolve()
                resolved_path.relative_to(entry.skill_dir.resolve())
                text = resolved_path.read_text(encoding="utf-8")
            except (OSError, ValueError) as exc:
                references.append(
                    {
                        "relative_path": _relative_to_skill(entry, reference_path),
                        "content": "",
                        "truncated": False,
                        "error": str(exc),
                    }
                )
                continue
            content, truncated = _truncate(text, self.max_body_chars)
            references.append(
                {
                    "relative_path": _relative_to_skill(entry, resolved_path),
                    "content": content,
                    "truncated": truncated,
                    "error": "",
                }
            )
        return references

    def _detect_unsupported_capabilities(self, entry: SkillEntry) -> list[str]:
        body_lower = entry.body.lower()
        unsupported: list[str] = []
        if entry.script_files and not self.allow_script_execution:
            unsupported.append("script_execution")
        if any(term in body_lower for term in ["browser", "playwright", "screenshot", "agent-browser"]):
            unsupported.append("browser_or_playwright_tooling")
        if any(term in body_lower for term in ["mcp__", "mcp server", "mcp tools", "mcp tool"]):
            unsupported.append("mcp_tooling")
        if any(term in body_lower for term in ["subagent", "sub-agent", "multi-agent", "子代理"]):
            unsupported.append("subagent_or_multi_agent_runtime")
        if any(term in body_lower for term in ["automation", "thread", "create_thread", "send_message_to_thread"]):
            unsupported.append("codex_thread_or_automation_runtime")
        return list(dict.fromkeys(unsupported))

    def _global_safety_notes(self) -> list[str]:
        notes = ["Skill Broker reads local SKILL.md instructions; it does not execute skill workflows by itself."]
        if not self.allow_script_execution:
            notes.append("Script execution is disabled.")
        return notes


def _parse_skill_markdown(raw_content: str) -> tuple[dict[str, str], str, list[str]]:
    warnings: list[str] = []
    normalized_content = raw_content.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized_content.startswith(f"{_FRONTMATTER_DELIMITER}\n"):
        return {}, raw_content, warnings

    lines = normalized_content.split("\n")
    closing_index = -1
    for index in range(1, len(lines)):
        if lines[index].strip() == _FRONTMATTER_DELIMITER:
            closing_index = index
            break

    if closing_index < 0:
        return {}, raw_content, ["frontmatter opening delimiter found without closing delimiter"]

    metadata_lines = lines[1:closing_index]
    body = "\n".join(lines[closing_index + 1 :]).lstrip("\n")
    return _parse_frontmatter_subset(metadata_lines, warnings), body, warnings


def _parse_frontmatter_subset(lines: list[str], warnings: list[str]) -> dict[str, str]:
    metadata: dict[str, str] = {}
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip() or line.lstrip().startswith("#"):
            index += 1
            continue
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:\s*(.*)$", line)
        if match is None:
            warnings.append(f"ignored unsupported frontmatter line: {line.strip()}")
            index += 1
            continue

        key = match.group(1).strip()
        value = match.group(2).strip()
        if value in {">", "|"}:
            block_lines: list[str] = []
            index += 1
            while index < len(lines):
                next_line = lines[index]
                if re.match(r"^[A-Za-z_][A-Za-z0-9_-]*\s*:", next_line):
                    break
                block_lines.append(next_line.strip())
                index += 1
            if value == ">":
                metadata[key] = _single_line(" ".join(block_lines))
            else:
                metadata[key] = "\n".join(block_lines).strip()
            continue

        metadata[key] = _strip_yaml_scalar(value)
        index += 1
    return metadata


def _strip_yaml_scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _find_referenced_markdown_files(skill_dir: Path, body: str) -> tuple[list[Path], list[str]]:
    candidates = set(_MARKDOWN_LINK_RE.findall(body))
    candidates.update(_PATH_RE.findall(body))

    resolved: list[Path] = []
    warnings: list[str] = []
    for candidate in sorted(candidates):
        candidate_path = _normalize_reference_candidate(candidate, skill_dir.name)
        if not candidate_path:
            continue
        reference_path = (skill_dir / candidate_path).resolve()
        try:
            reference_path.relative_to(skill_dir.resolve())
        except ValueError:
            warnings.append(f"blocked out-of-skill reference: {candidate}")
            continue
        if reference_path == (skill_dir / "SKILL.md").resolve():
            continue
        if reference_path.is_file() and reference_path.suffix.lower() == ".md" and reference_path not in resolved:
            resolved.append(reference_path)
    return resolved, warnings


def _find_script_hints(skill_dir: Path, body: str) -> list[Path]:
    scripts: list[Path] = []
    for candidate in sorted(set(_SCRIPT_HINT_RE.findall(body))):
        candidate_path = _normalize_reference_candidate(candidate, skill_dir.name)
        if not candidate_path:
            continue
        script_path = (skill_dir / candidate_path).resolve()
        try:
            script_path.relative_to(skill_dir.resolve())
        except ValueError:
            continue
        if script_path.exists() and script_path not in scripts:
            scripts.append(script_path)
    scripts_dir = skill_dir / "scripts"
    if scripts_dir.is_dir():
        for script_file in sorted(path for path in scripts_dir.rglob("*") if path.is_file()):
            if script_file.resolve() not in scripts:
                scripts.append(script_file.resolve())
    return scripts


def _normalize_reference_candidate(candidate: str, skill_dir_name: str) -> Path | None:
    text = str(candidate or "").strip().strip("`'\"<>")
    if not text:
        return None
    if "://" in text or text.startswith("//"):
        return None
    text = text.split("#", 1)[0].split("?", 1)[0]
    text = text.replace("\\", "/")
    text = text.replace("{baseDir}/", "")
    skill_prefix = f"skills/{skill_dir_name}/"
    if text.startswith(skill_prefix):
        text = text[len(skill_prefix) :]
    if text.startswith("./"):
        text = text[2:]
    path = Path(text)
    if path.is_absolute() or any(part == ".." for part in path.parts):
        return path
    return path


def _tokenize(text: str) -> list[str]:
    return [match.group(0).lower() for match in _WORD_RE.finditer(str(text or ""))]


def _single_line(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _normalize_name(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(text or "").lower())


def _truncate(text: str, max_chars: int) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars].rstrip() + "\n...[truncated]", True


def _relative_to_skill(entry: SkillEntry, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(entry.skill_dir.resolve())).replace("\\", "/")
    except ValueError:
        return str(path)


def to_json_content(payload: dict[str, Any]) -> str:
    """Return pretty JSON for tests or debug surfaces."""

    return json.dumps(payload, ensure_ascii=False, indent=2)
