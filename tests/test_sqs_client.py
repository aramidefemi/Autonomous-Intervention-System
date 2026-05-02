from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ais.config import Settings
from ais.sqs.client import SqsClient


@pytest.mark.asyncio
async def test_send_ingress_delegates_to_boto() -> None:
    s = Settings(
        mongo_uri="mongodb://localhost:27017",
        aws_endpoint_url="http://localhost:4566",
    )
    c = SqsClient(s)
    c._ingress_queue_url = "http://q/ingress"  # noqa: SLF001
    c._dlq_queue_url = "http://q/dlq"  # noqa: SLF001
    mock_sqs = AsyncMock()
    mock_sqs.send_message = AsyncMock(
        return_value={"MessageId": "mid-1"},
    )
    enter = MagicMock()
    enter.__aenter__ = AsyncMock(return_value=mock_sqs)
    enter.__aexit__ = AsyncMock(return_value=None)
    with patch.object(c, "_sqs_client", return_value=enter):
        mid = await c.send_ingress_json('{"a":1}')
    assert mid == "mid-1"
    mock_sqs.send_message.assert_awaited_once()
    call_kw = mock_sqs.send_message.await_args.kwargs
    assert call_kw["QueueUrl"] == "http://q/ingress"
    assert call_kw["MessageBody"] == '{"a":1}'
