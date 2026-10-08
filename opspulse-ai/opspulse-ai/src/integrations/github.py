"""GitHub REST integration via PyGithub (Developer 2): fetch source code, open fix PRs."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from github import Auth, Github, GithubException
from github.Repository import Repository

from src.agent.parsing import path_candidates
from src.agent.patching import PatchError, apply_unified_diff, format_code_window
from src.config import settings

logger = logging.getLogger(__name__)

MAX_FILE_BYTES = 2_000_000
PR_LABEL = "opspulse-ai"


class GitHubError(RuntimeError):
    pass


@dataclass
class SourceContext:
    path: str
    commit_sha: str
    start_line: int
    end_line: int
    failing_line: int
    window_text: str
    recent_commits: List[str]

    def render(self) -> str:
        header = [
            f"FILE: {self.path}",
            f"COMMIT: {self.commit_sha}",
            f"WINDOW: lines {self.start_line}-{self.end_line} (failing line: {self.failing_line})",
        ]
        if self.recent_commits:
            header.append("RECENT COMMITS TOUCHING THIS FILE (14 days):")
            header.extend(f"  - {c}" for c in self.recent_commits)
        header.append("-----")
        return "\n".join(header) + "\n" + self.window_text


def get_client() -> Github:
    if not settings.github_token:
        raise GitHubError("GITHUB_TOKEN is not set")
    return Github(auth=Auth.Token(settings.github_token), per_page=100, retry=3, timeout=20)


def get_repo(gh: Github, repo_name: str) -> Repository:
    try:
        return gh.get_repo(repo_name)
    except GithubException as exc:
        raise GitHubError(f"cannot open repository {repo_name!r}: {exc.status} {exc.data}") from exc


def resolve_repo_path(repo: Repository, runtime_path: str, ref: str) -> Optional[str]:
    """Map a runtime path (e.g. /app/src/x.py) to a real file in the repo tree."""
    tree = repo.get_git_tree(ref, recursive=True)
    blobs = [e.path for e in tree.tree if e.type == "blob"]
    blob_set = set(blobs)
    for candidate in path_candidates(runtime_path):
        if candidate in blob_set:
            return candidate
        suffix = "/" + candidate
        matches = [p for p in blobs if p.endswith(suffix)]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1 and "/" in candidate:
            return min(matches, key=len)
    return None


def _read_text(repo: Repository, content_file: Any) -> str:
    if getattr(content_file, "size", 0) > MAX_FILE_BYTES:
        raise GitHubError(f"{content_file.path} is larger than {MAX_FILE_BYTES} bytes")
    try:
        raw = content_file.decoded_content
    except Exception:
        import base64

        blob = repo.get_git_blob(content_file.sha)
        raw = base64.b64decode(blob.content) if blob.encoding == "base64" else blob.content.encode()
    return raw.decode("utf-8", errors="replace")


def _recent_commits(repo: Repository, path: str, limit: int = 5) -> List[str]:
    try:
        since = datetime.now(timezone.utc) - timedelta(days=14)
        out = []
        for commit in repo.get_commits(path=path, since=since)[:limit]:
            when = commit.commit.author.date.strftime("%Y-%m-%d")
            subject = (commit.commit.message or "").splitlines()[0][:100]
            out.append(f"{commit.sha[:7]} {when} {subject}")
        return out
    except Exception:
        logger.debug("recent commits lookup failed", exc_info=True)
        return []


def fetch_source_context(
    repo_name: str, runtime_path: str, failing_line: int, radius: Optional[int] = None
) -> Optional[SourceContext]:
    """Fetch the file that crashed and return a numbered window around the failing line.

    Returns None when the file cannot be located in the repository.
    """
    radius = radius or settings.context_radius
    gh = get_client()
    repo = get_repo(gh, repo_name)
    branch = repo.default_branch
    commit_sha = repo.get_branch(branch).commit.sha
    path = resolve_repo_path(repo, runtime_path, commit_sha)
    if path is None:
        logger.warning("could not resolve %s inside %s", runtime_path, repo_name)
        return None
    content_file = repo.get_contents(path, ref=commit_sha)
    if isinstance(content_file, list):
        return None
    lines = _read_text(repo, content_file).splitlines()
    if not lines:
        return None
    failing_line = min(max(failing_line, 1), len(lines))
    start = max(1, failing_line - radius)
    end = min(len(lines), failing_line + radius)
    return SourceContext(
        path=path,
        commit_sha=commit_sha[:12],
        start_line=start,
        end_line=end,
        failing_line=failing_line,
        window_text=format_code_window(lines[start - 1:end], start),
        recent_commits=_recent_commits(repo, path),
    )


def create_fix_pull_request(
    repo_name: str,
    file_path: str,
    unified_diff: str,
    title: str,
    body: str,
    fingerprint: str,
) -> Dict[str, Any]:
    """Apply `unified_diff` to `file_path` on a new branch and open a (draft) pull request."""
    gh = get_client()
    repo = get_repo(gh, repo_name)
    base = repo.default_branch
    base_sha = repo.get_branch(base).commit.sha

    current = repo.get_contents(file_path, ref=base_sha)
    if isinstance(current, list):
        raise GitHubError(f"{file_path} is a directory")
    original = _read_text(repo, current)
    try:
        patched = apply_unified_diff(original, unified_diff)
    except PatchError as exc:
        raise GitHubError(f"patch does not apply to {file_path}@{base_sha[:7]}: {exc}") from exc
    if patched == original:
        raise GitHubError("patch produces no change")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    branch = f"opspulse/fix-{fingerprint[:8]}-{stamp}"
    repo.create_git_ref(ref=f"refs/heads/{branch}", sha=base_sha)
    repo.update_file(
        path=file_path,
        message=f"fix: {title[:60]}\n\nAutomated fix proposed by OpsPulse AI (fingerprint {fingerprint[:12]}).",
        content=patched,
        sha=current.sha,
        branch=branch,
    )

    try:
        pr = repo.create_pull(base=base, head=branch, title=title[:200], body=body, draft=settings.github_pr_draft)
    except GithubException as exc:
        if settings.github_pr_draft and exc.status == 422:  # drafts unsupported on this repo/plan
            pr = repo.create_pull(base=base, head=branch, title=title[:200], body=body, draft=False)
        else:
            raise GitHubError(f"cannot create pull request: {exc.status} {exc.data}") from exc

    try:
        try:
            repo.get_label(PR_LABEL)
        except GithubException:
            repo.create_label(PR_LABEL, "0e8a16", "Automated fix proposed by OpsPulse AI")
        pr.add_to_labels(PR_LABEL)
    except Exception:
        logger.debug("could not label PR", exc_info=True)

    return {"pr_url": pr.html_url, "pr_number": pr.number, "branch": branch}
