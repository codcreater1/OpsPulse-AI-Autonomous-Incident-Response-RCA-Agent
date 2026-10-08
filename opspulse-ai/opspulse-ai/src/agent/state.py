"""Shared contract between Developer 1 and Developer 2. Do not change field names/types."""
from typing import Any, Dict, List, Optional, TypedDict


class IncidentState(TypedDict):
    error_message: str
    stack_trace: str
    repo_name: str
    affected_file: Optional[str]
    code_context: Optional[str]
    historical_matches: Optional[List[Dict[str, Any]]]
    root_cause_analysis: Optional[Dict[str, Any]]
    suggested_patch: Optional[str]
    confidence_score: float
    iterations: int
    previous_feedback: Optional[str]


def initial_state(error_message: str, stack_trace: str, repo_name: str) -> IncidentState:
    """Build the entry state for the graph."""
    return IncidentState(
        error_message=error_message,
        stack_trace=stack_trace,
        repo_name=repo_name,
        affected_file=None,
        code_context=None,
        historical_matches=None,
        root_cause_analysis=None,
        suggested_patch=None,
        confidence_score=0.0,
        iterations=0,
        previous_feedback=None,
    )
