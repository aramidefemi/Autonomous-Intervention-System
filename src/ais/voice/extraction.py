import json
import re
from dataclasses import dataclass

from ais.models import IssueType


@dataclass(frozen=True)
class IssueExtraction:
    issue_type: IssueType
    confidence: float
    method: str  # json | keyword | default


_JSON_START = re.compile(r"^\s*[\{\[]")


def extract_issue_type(transcript: str, *, structured: dict | None = None) -> IssueExtraction:
    """Map NL transcript (or agent JSON) to a stable issue type; pure, no I/O."""
    if structured and "issueType" in structured:
        raw = structured["issueType"]
        if isinstance(raw, str) and raw:
            try:
                it = IssueType(raw)
            except ValueError:
                it = IssueType.UNKNOWN
            return IssueExtraction(issue_type=it, confidence=0.95, method="structured")

    t = (transcript or "").strip()
    if t and _JSON_START.search(t):
        try:
            data = json.loads(t)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict) and "issueType" in data:
            raw = data["issueType"]
            if isinstance(raw, str) and raw:
                try:
                    it = IssueType(raw)
                except ValueError:
                    it = IssueType.UNKNOWN
                return IssueExtraction(issue_type=it, confidence=0.9, method="json")

    lower = t.lower()
    if any(k in lower for k in ("broke down", "bike broke", "flat tire", "mechanical")):
        return IssueExtraction(
            issue_type=IssueType.MECHANICAL_FAILURE,
            confidence=0.85,
            method="keyword",
        )
    if any(k in lower for k in ("traffic", "stuck in traffic", "jam")):
        return IssueExtraction(
            issue_type=IssueType.TRAFFIC_DELAY,
            confidence=0.8,
            method="keyword",
        )
    if any(k in lower for k in ("wrong address", "can't find", "cannot find the address")):
        return IssueExtraction(
            issue_type=IssueType.WRONG_ADDRESS,
            confidence=0.75,
            method="keyword",
        )
    if any(k in lower for k in ("no answer", "voicemail", "not picking up")):
        return IssueExtraction(
            issue_type=IssueType.CUSTOMER_UNREACHABLE,
            confidence=0.7,
            method="keyword",
        )
    if t:
        return IssueExtraction(
            issue_type=IssueType.OTHER,
            confidence=0.5,
            method="keyword",
        )
    return IssueExtraction(issue_type=IssueType.UNKNOWN, confidence=0.0, method="default")
