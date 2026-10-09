"""Deterministic log / stack-trace parsing (Developer 2). Pure functions, no I/O."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")

PY_FRAME_RE = re.compile(r'File "(?P<path>[^"]+)", line (?P<line>\d+)(?:, in (?P<func>[^\n]+))?')
JS_FRAME_RE = re.compile(
    r"^\s*at\s+(?:async\s+)?(?:(?P<func>[^\s()]+(?:\s\[as\s[^\]]+\])?)\s+\()?"
    r"(?P<path>(?:file://)?(?:[A-Za-z]:)?[^\s():]+):(?P<line>\d+)(?::\d+)?\)?\s*$",
    re.MULTILINE,
)
JAVA_FRAME_RE = re.compile(
    r"^\s*at\s+(?P<qual>[\w$.]+)\.(?P<func>[\w$<>]+)\((?P<file>[\w$]+\.(?:java|kt|scala)):(?P<line>\d+)\)",
    re.MULTILINE,
)
GO_FRAME_RE = re.compile(r"^\s+(?P<path>/[^\s:]+\.go):(?P<line>\d+)", re.MULTILINE)
EXC_TYPE_RE = re.compile(r"^\s*(?:Uncaught\s+)?(?P<type>[A-Za-z_][\w.$]*(?:Error|Exception|Panic|Failure|Exit))\b")

INTERNAL_MARKERS = (
    "site-packages",
    "dist-packages",
    "/usr/lib/python",
    "/usr/local/lib/python",
    "<frozen",
    "<string>",
    "<stdin>",
    "node_modules",
    "node:internal",
    "internal/",
    "/usr/local/go/src",
    "/usr/lib/go",
    "/go/pkg/mod",
    "lib/python3",
)
INTERNAL_JAVA_PREFIXES = ("java.", "javax.", "jdk.", "sun.", "kotlin.", "scala.", "org.junit.")

STRIP_PREFIXES = (
    "/app/",
    "/usr/src/app/",
    "/usr/src/",
    "/workspace/",
    "/workdir/",
    "/srv/",
    "/code/",
    "/build/",
    "/opt/app/",
)


@dataclass(frozen=True)
class Frame:
    path: str
    line: int
    function: str
    language: str


def clean_text(text: str, max_chars: int = 60_000) -> str:
    """Strip ANSI codes / NULs, normalise newlines and cap size (keeps head and tail)."""
    text = ANSI_RE.sub("", text or "").replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    text = text.strip()
    if len(text) > max_chars:
        half = max_chars // 2
        text = text[:half] + "\n...[truncated]...\n" + text[-half:]
    return text


def split_embedded_trace(error_message: str, stack_trace: str) -> tuple[str, str]:
    """If the sender put the traceback inside error_message, separate them."""
    if stack_trace.strip() or not error_message:
        return error_message, stack_trace
    marker = error_message.find("Traceback (most recent call last):")
    if marker > 0:
        return error_message[:marker].strip() or error_message, error_message[marker:]
    lines = error_message.splitlines()
    for idx, line in enumerate(lines):
        if idx > 0 and re.match(r"^\s*at\s+\S", line):
            return "\n".join(lines[:idx]).strip(), "\n".join(lines[idx:])
    return error_message, stack_trace


def _is_internal(path: str) -> bool:
    low = path.replace("\\", "/")
    return any(marker in low for marker in INTERNAL_MARKERS)


def normalize_path(path: str) -> str:
    """Make a runtime path look like a repo-relative path (best effort)."""
    p = path.strip().replace("\\", "/")
    if p.startswith("file://"):
        p = p[len("file://") :]
    p = re.sub(r"^[A-Za-z]:", "", p)
    for prefix in STRIP_PREFIXES:
        if p.startswith(prefix):
            p = p[len(prefix) :]
            break
    return p.lstrip("/")


def path_candidates(path: str) -> list[str]:
    """Longest-to-shortest suffixes of a path, used to resolve it inside a repo tree."""
    parts = [seg for seg in normalize_path(path).split("/") if seg]
    return ["/".join(parts[i:]) for i in range(len(parts))]


def _java_path(qualified_class: str, filename: str) -> str:
    """com.acme.Foo$Inner -> com/acme/<filename> (package directory + source file name)."""
    cls = qualified_class.split("$")[0]
    package = cls.rsplit(".", 1)[0] if "." in cls else ""
    return f"{package.replace('.', '/')}/{filename}".lstrip("/")


def extract_frames(stack_trace: str) -> tuple[list[Frame], str]:
    """Return (frames ordered most-recent-first, detected language)."""
    text = stack_trace or ""
    py_blocks = text.split("Traceback (most recent call last):")
    if len(py_blocks) > 1 or PY_FRAME_RE.search(text):
        block = py_blocks[-1] if len(py_blocks) > 1 else text
        frames = [
            Frame(m.group("path"), int(m.group("line")), (m.group("func") or "").strip(), "python")
            for m in PY_FRAME_RE.finditer(block)
        ]
        return list(reversed(frames)), "python"
    java = [
        Frame(
            _java_path(m.group("qual"), m.group("file")),
            int(m.group("line")),
            f"{m.group('qual')}.{m.group('func')}",
            "java",
        )
        for m in JAVA_FRAME_RE.finditer(text)
    ]
    if java:
        return java, "java"
    go = [Frame(m.group("path"), int(m.group("line")), "", "go") for m in GO_FRAME_RE.finditer(text)]
    if go:
        return go, "go"
    js = [
        Frame(m.group("path"), int(m.group("line")), (m.group("func") or "").strip(), "javascript")
        for m in JS_FRAME_RE.finditer(text)
    ]
    return js, "javascript"


def get_trigger_frame(stack_trace: str) -> Frame | None:
    """First application (non-library) frame closest to the crash."""
    frames, _ = extract_frames(stack_trace)
    for frame in frames:
        if _is_internal(frame.path):
            continue
        if frame.language == "java" and frame.function.startswith(INTERNAL_JAVA_PREFIXES):
            continue
        return frame
    return None


def extract_exception_type(error_message: str, stack_trace: str) -> str:
    """Exception class name from the message's first line, else from the trace (last line first)."""
    first = (error_message or "").strip().splitlines()[:1]
    candidates = first + list(reversed((stack_trace or "").splitlines()))
    for line in candidates:
        m = EXC_TYPE_RE.match(line)
        if m:
            return m.group("type")
    return "UnknownError"


_VOLATILE_RE = re.compile(
    r"0x[0-9a-fA-F]+|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|\d+"
)


def compute_fingerprint(repo_name: str, error_message: str, stack_trace: str) -> str:
    """Stable SHA-256 incident fingerprint (independent of line numbers, ids and timestamps)."""
    exc_type = extract_exception_type(error_message, stack_trace)
    frame = get_trigger_frame(stack_trace)
    if frame:
        basis = f"{normalize_path(frame.path)}|{frame.function}"
    else:
        basis = _VOLATILE_RE.sub("#", (error_message or "").strip().lower())[:300]
    raw = f"{repo_name.lower()}|{exc_type}|{basis}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
