"""LangGraph nodes.

Developer 2: parse_log_node, github_fetch_node, neon_lookup_node  (ingestion & extraction)
Developer 1: analyze_cause_node, evaluate_quality_node            (AI reasoning & quality gate)
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from src.agent.parsing import (
    clean_text,
    compute_fingerprint,
    get_trigger_frame,
    normalize_path,
    split_embedded_trace,
)
from src.agent.patching import (
    PatchError,
    apply_hunks,
    parse_code_window,
    parse_unified_diff,
    path_matches,
)
from src.agent.prompts import RCA_SYSTEM_PROMPT, SEVERITIES, build_rca_user_prompt
from src.agent.state import IncidentState
from src.config import AGENT_VERSION, settings

logger = logging.getLogger(__name__)


# =============================================================================
# DEVELOPER 2 - ingestion & extraction nodes
# =============================================================================

def parse_log_node(state: IncidentState) -> Dict[str, Any]:
    """(1) Clean the raw telemetry and locate the trigger frame / affected file."""
    message, trace = split_embedded_trace(state["error_message"] or "", state["stack_trace"] or "")
    message = clean_text(message, 10_000) or "unknown error"
    trace = clean_text(trace, 60_000)
    frame = get_trigger_frame(trace)
    affected = normalize_path(frame.path) if frame else None
    logger.info("parse_log: trigger=%s", f"{affected}:{frame.line}" if frame else "none")
    return {"error_message": message, "stack_trace": trace, "affected_file": affected}


def github_fetch_node(state: IncidentState) -> Dict[str, Any]:
    """(2) Fetch the failing file (+/- N lines) from GitHub. Degrades gracefully to no context."""
    from src.integrations.github import fetch_source_context

    frame = get_trigger_frame(state["stack_trace"])
    if frame is None:
        return {"code_context": None}
    try:
        ctx = fetch_source_context(state["repo_name"], frame.path, frame.line)
    except Exception:
        logger.exception("github_fetch failed for %s", state["repo_name"])
        return {"code_context": None}
    if ctx is None:
        return {"code_context": None}
    return {"affected_file": ctx.path, "code_context": ctx.render()}


def neon_lookup_node(state: IncidentState) -> Dict[str, Any]:
    """(3) Look up similar historical incidents in Neon. Never blocks the pipeline."""
    from src.db.client import find_similar_incidents

    fingerprint = compute_fingerprint(state["repo_name"], state["error_message"], state["stack_trace"])
    try:
        matches = find_similar_incidents(state["repo_name"], fingerprint, state.get("affected_file"))
    except Exception:
        logger.exception("neon_lookup failed - continuing without history")
        matches = []
    logger.info("neon_lookup: %d historical matches", len(matches))
    return {"historical_matches": matches}


# =============================================================================
# DEVELOPER 1 - AI reasoning & quality gate
# =============================================================================

@lru_cache(maxsize=8)
def _get_llm(temperature: float):
    """ChatGroq (Llama 3.3 70B) in JSON mode. Cached per temperature."""
    from langchain_groq import ChatGroq

    llm = ChatGroq(
        model=settings.groq_model,
        api_key=settings.groq_api_key or os.getenv("GROQ_API_KEY"),
        temperature=temperature,
        max_tokens=4096,
        max_retries=3,
        timeout=90,
    )
    return llm.bind(response_format={"type": "json_object"})


def extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    """Parse the model output into a dict; tolerate stray fences / prose around the object."""
    if not text:
        return None
    candidates = [text.strip()]
    fenced = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
    candidates.append(fenced)
    first, last = text.find("{"), text.rfind("}")
    if first != -1 and last > first:
        candidates.append(text[first:last + 1])
    for cand in candidates:
        try:
            value = json.loads(cand)
        except (ValueError, TypeError):
            continue
        if isinstance(value, dict):
            return value
    return None


def _analysis_digest(analysis: Dict[str, Any]) -> str:
    material = {k: analysis.get(k) for k in ("incident_summary", "hypotheses", "diagnostic_chain", "patch_remediation")}
    return hashlib.sha256(json.dumps(material, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def analyze_cause_node(state: IncidentState, config: RunnableConfig) -> Dict[str, Any]:
    """(4) Multi-hypothesis RCA + patch generation with Groq Llama 3.3. Traced by Langfuse via `config`."""
    iteration = state["iterations"] + 1
    temperature = 0.0 if iteration == 1 else 0.2
    messages = [
        SystemMessage(content=RCA_SYSTEM_PROMPT),
        HumanMessage(content=build_rca_user_prompt(dict(state), state.get("root_cause_analysis") if iteration > 1 else None)),
    ]
    raw_text = ""
    try:
        response = _get_llm(temperature).invoke(messages, config=config)
        raw_text = response.content if isinstance(response.content, str) else json.dumps(response.content)
    except Exception as exc:  # Groq rejects malformed JSON generations with a 400
        if exc.__class__.__name__ != "BadRequestError":
            raise
        logger.warning("Groq rejected the generation (iteration %d): %s", iteration, exc)
        raw_text = ""

    analysis = extract_json_object(raw_text)
    if analysis is None:
        analysis = {"error": "model did not return a valid JSON object", "raw_output_excerpt": raw_text[:500]}
        patch = None
    else:
        remediation = analysis.get("patch_remediation")
        patch = remediation.get("unified_diff") if isinstance(remediation, dict) else None
        patch = patch if isinstance(patch, str) and patch.strip() else None

    analysis["execution_metadata"] = {  # produced in code, never by the LLM
        "agent_version": AGENT_VERSION,
        "node_id": "RCA_ENGINE_NODE",
        "model": settings.groq_model,
        "iteration": iteration,
        "timestamp_iso": datetime.now(timezone.utc).isoformat(),
        "analysis_sha256": _analysis_digest(analysis),
    }
    logger.info("analyze_cause: iteration=%d valid_json=%s patch=%s", iteration, "error" not in analysis, bool(patch))
    return {"root_cause_analysis": analysis, "suggested_patch": patch, "iterations": iteration}


# ----------------------------- deterministic quality gate -----------------------------

CHECK_WEIGHTS: Dict[str, float] = {
    "schema": 0.15,
    "trigger_grounding": 0.15,
    "diff_wellformed": 0.15,
    "diff_applies": 0.25,
    "patch_minimal": 0.05,
    "patch_locality": 0.10,
    "self_assessment": 0.10,
    "patch_effective": 0.05,
}
assert abs(sum(CHECK_WEIGHTS.values()) - 1.0) < 1e-9

LOCALITY_RADIUS = 30
Check = Tuple[float, str]  # (fraction 0..1, detail)


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _check_schema(rca: Dict[str, Any]) -> Check:
    summary = rca.get("incident_summary") if isinstance(rca.get("incident_summary"), dict) else {}
    hyps = rca.get("hypotheses") if isinstance(rca.get("hypotheses"), list) else []
    chain = rca.get("diagnostic_chain") if isinstance(rca.get("diagnostic_chain"), dict) else {}
    primary = chain.get("primary_root_cause") if isinstance(chain.get("primary_root_cause"), dict) else {}
    patch = rca.get("patch_remediation") if isinstance(rca.get("patch_remediation"), dict) else {}
    flow = rca.get("control_flow") if isinstance(rca.get("control_flow"), dict) else {}
    hyp_dicts = [h for h in hyps if isinstance(h, dict)]
    ids = {h.get("id") for h in hyp_dicts}
    conf = flow.get("self_assessed_confidence")
    subchecks = {
        "incident_summary.title": _nonempty(summary.get("title")),
        "incident_summary.severity (CRITICAL|HIGH|MEDIUM|LOW)": summary.get("severity") in SEVERITIES,
        "incident_summary.trigger_frame": _nonempty(summary.get("trigger_frame")),
        "hypotheses has 2-4 items": 2 <= len(hyps) <= 4,
        "every hypothesis has id/description/evidence": bool(hyp_dicts) and len(hyp_dicts) == len(hyps)
        and all(_nonempty(h.get("id")) and _nonempty(h.get("description")) and _nonempty(h.get("evidence")) for h in hyp_dicts),
        "primary_root_cause.technical_explanation": _nonempty(primary.get("technical_explanation")),
        "primary_root_cause.symptom_vs_cause": _nonempty(primary.get("symptom_vs_cause")),
        "primary_root_cause.hypothesis_id references a hypothesis": primary.get("hypothesis_id") in ids,
        "patch_remediation.explanation": _nonempty(patch.get("explanation")),
        "patch_remediation.unified_diff is a string": isinstance(patch.get("unified_diff"), str),
        "control_flow.self_assessed_confidence in [0,1]": isinstance(conf, (int, float))
        and not isinstance(conf, bool) and 0.0 <= conf <= 1.0,
    }
    failed = [name for name, ok in subchecks.items() if not ok]
    return (len(subchecks) - len(failed)) / len(subchecks), ("ok" if not failed else "missing/invalid: " + "; ".join(failed))


def _check_trigger(rca: Dict[str, Any], stack_trace: str) -> Check:
    frame = get_trigger_frame(stack_trace)
    if frame is None:
        return 0.0, "no application frame found in the stack trace"
    summary = rca.get("incident_summary") if isinstance(rca.get("incident_summary"), dict) else {}
    claimed = str(summary.get("trigger_frame", "")).lower()
    base = frame.path.replace("\\", "/").rsplit("/", 1)[-1].lower()
    has_file, has_line = base in claimed, re.search(rf"(?<!\d){frame.line}(?!\d)", claimed) is not None
    problems = []
    if not has_file:
        problems.append(f"trigger_frame must name file {base!r}")
    if not has_line:
        problems.append(f"trigger_frame must include failing line {frame.line}")
    return (0.5 * has_file + 0.5 * has_line), ("ok" if not problems else "; ".join(problems))


def _evaluate_patch(
    patch: Optional[str], affected_file: Optional[str], code_context: Optional[str], failing_line: Optional[int]
) -> Dict[str, Check]:
    results: Dict[str, Check] = {}
    fail = "no patch provided" if not patch else ""
    parsed = None
    if patch:
        try:
            parsed = parse_unified_diff(patch)
        except PatchError as exc:
            fail = f"diff is malformed: {exc}"
    if parsed is None:
        for name in ("diff_wellformed", "diff_applies", "patch_minimal", "patch_locality", "patch_effective"):
            results[name] = (0.0, fail)
        return results

    wf_problems = []
    if not path_matches(parsed.path, affected_file):
        wf_problems.append(f"diff header path {parsed.path!r} must be {affected_file!r}")
    if parsed.file_count != 1:
        wf_problems.append("diff must touch exactly one file")
    results["diff_wellformed"] = (1.0 - 0.5 * len(wf_problems), "ok" if not wf_problems else "; ".join(wf_problems))

    changed = parsed.changed_lines
    results["patch_minimal"] = (1.0 if changed <= 40 else 0.5 if changed <= 80 else 0.0, f"{changed} changed lines")

    if not code_context:
        reason = "source window unavailable - patch cannot be verified against the code"
        results["diff_applies"] = (0.0, reason)
        results["patch_locality"] = (0.0, reason)
        results["patch_effective"] = (0.0, reason)
        return results

    try:
        start, lines = parse_code_window(code_context)
        positions: List[int] = []
        patched = apply_hunks(lines, parsed.hunks, start - 1, positions)
    except PatchError as exc:
        reason = f"patch does not apply to the supplied source: {exc}. Copy context/removed lines verbatim from CODE_CONTEXT"
        results["diff_applies"] = (0.0, reason)
        results["patch_locality"] = (0.0, "patch not applicable")
        results["patch_effective"] = (0.0, "patch not applicable")
        return results

    results["diff_applies"] = (1.0, "ok")
    results["patch_effective"] = (
        (1.0, "ok") if [x.strip() for x in patched] != [x.strip() for x in lines] else (0.0, "patch changes only whitespace / nothing")
    )
    if failing_line is None:
        results["patch_locality"] = (0.4, "no failing line to compare against")
    else:
        near = any(abs(pos - failing_line) <= LOCALITY_RADIUS for pos in positions)
        results["patch_locality"] = (1.0 if near else 0.4, "ok" if near else
                                     f"patch is far (> {LOCALITY_RADIUS} lines) from failing line {failing_line}; justify or move it")
    return results


def _check_self_assessment(rca: Dict[str, Any]) -> Check:
    flow = rca.get("control_flow") if isinstance(rca.get("control_flow"), dict) else {}
    conf = flow.get("self_assessed_confidence")
    if flow.get("needs_human_review") is True:
        return 0.0, "model asked for human review"
    if isinstance(conf, (int, float)) and not isinstance(conf, bool):
        return max(0.0, min(1.0, float(conf))), f"model self-assessed {float(conf):.2f}"
    return 0.0, "self_assessed_confidence missing"


def decide_next(score: float, iterations: int, code_context: Optional[str]) -> str:
    """Single source of truth for routing: 'PR' | 'RETRY' | 'REVIEW'."""
    if score >= settings.confidence_threshold:
        return "PR"
    if iterations < settings.max_iterations and code_context:  # without source a retry cannot add grounding
        return "RETRY"
    return "REVIEW"


def evaluate_quality_node(state: IncidentState) -> Dict[str, Any]:
    """(5) Deterministic quality gate: score is computed in code, not by the LLM."""
    rca = dict(state.get("root_cause_analysis") or {})
    patch = state.get("suggested_patch")
    frame = get_trigger_frame(state["stack_trace"])

    checks: Dict[str, Check] = {}
    if "error" in rca:
        checks["schema"] = (0.0, rca["error"])
        checks["trigger_grounding"] = (0.0, "no valid analysis")
        checks["self_assessment"] = (0.0, "no valid analysis")
        checks.update(_evaluate_patch(None, None, None, None))
    else:
        checks["schema"] = _check_schema(rca)
        checks["trigger_grounding"] = _check_trigger(rca, state["stack_trace"])
        checks["self_assessment"] = _check_self_assessment(rca)
        checks.update(_evaluate_patch(patch, state.get("affected_file"), state.get("code_context"), frame.line if frame else None))

    score = round(sum(CHECK_WEIGHTS[name] * fraction for name, (fraction, _) in checks.items()), 4)
    route = decide_next(score, state["iterations"], state.get("code_context"))
    passed = score >= settings.confidence_threshold

    feedback_lines = [
        f"- {name} ({CHECK_WEIGHTS[name] * fraction:.2f}/{CHECK_WEIGHTS[name]:.2f}): {detail}"
        for name, (fraction, detail) in checks.items() if fraction < 1.0
    ]
    feedback = None
    if not passed:
        feedback = (
            f"Quality gate score {score:.2f} < required {settings.confidence_threshold:.2f} "
            f"(attempt {state['iterations']}/{settings.max_iterations}). Fix these problems:\n" + "\n".join(feedback_lines)
        )

    if "error" not in rca:
        llm_flow = rca.get("control_flow") if isinstance(rca.get("control_flow"), dict) else {}
        llm_conf = llm_flow.get("self_assessed_confidence")
        rca["control_flow"] = {
            "confidence_score": score,
            "quality_gate_passed": passed,
            "next_node": {"PR": "NEON_SAVE_AND_GITHUB_PR", "RETRY": "RCA_ENGINE_NODE", "REVIEW": "NEON_SAVE_HUMAN_REVIEW"}[route],
            "llm_self_assessed_confidence": llm_conf,
            "checks": {n: {"score": round(CHECK_WEIGHTS[n] * f, 4), "max": CHECK_WEIGHTS[n], "detail": d} for n, (f, d) in checks.items()},
        }
    else:
        rca["control_flow"] = {"confidence_score": score, "quality_gate_passed": False, "next_node": "RCA_ENGINE_NODE" if route == "RETRY" else "NEON_SAVE_HUMAN_REVIEW",
                               "checks": {n: {"score": round(CHECK_WEIGHTS[n] * f, 4), "max": CHECK_WEIGHTS[n], "detail": d} for n, (f, d) in checks.items()}}
    logger.info("evaluate_quality: score=%.4f route=%s", score, route)
    return {"confidence_score": score, "previous_feedback": feedback, "root_cause_analysis": rca}
