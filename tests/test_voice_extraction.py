import json

import pytest

from ais.models import IssueType
from ais.voice import extract_issue_type


@pytest.mark.parametrize(
    ("transcript", "expected"),
    [
        ("My bike broke down", IssueType.MECHANICAL_FAILURE),
        ("stuck in traffic again", IssueType.TRAFFIC_DELAY),
        ("wrong address on the app", IssueType.WRONG_ADDRESS),
        ("customer not picking up", IssueType.CUSTOMER_UNREACHABLE),
        ("something else happened", IssueType.OTHER),
        ("", IssueType.UNKNOWN),
    ],
)
def test_keyword_extraction(transcript: str, expected: IssueType) -> None:
    got = extract_issue_type(transcript)
    assert got.issue_type == expected


def test_json_transcript_body() -> None:
    t = json.dumps({"issueType": "traffic_delay", "note": "x"})
    got = extract_issue_type(t)
    assert got.issue_type == IssueType.TRAFFIC_DELAY
    assert got.method == "json"


def test_structured_override() -> None:
    got = extract_issue_type(
        "noise",
        structured={"issueType": "mechanical_failure"},
    )
    assert got.issue_type == IssueType.MECHANICAL_FAILURE
    assert got.method == "structured"
