"""Thin aioboto3 SQS wrapper for ingress + DLQ (LocalStack or AWS)."""

from __future__ import annotations

from typing import Any

import aioboto3


def _client_kwargs(settings: Any) -> dict[str, Any]:
    kw: dict[str, Any] = {
        "region_name": settings.aws_region,
        "aws_access_key_id": settings.aws_access_key_id,
        "aws_secret_access_key": settings.aws_secret_access_key,
    }
    if settings.aws_endpoint_url:
        kw["endpoint_url"] = settings.aws_endpoint_url
    return kw


class ReceivedMessage:
    __slots__ = ("body", "receipt_handle", "receive_count")

    def __init__(self, *, body: str, receipt_handle: str, receive_count: int) -> None:
        self.body = body
        self.receipt_handle = receipt_handle
        self.receive_count = receive_count


class SqsClient:
    """Send/receive/delete/visibility for two named queues (ingress + DLQ)."""

    def __init__(self, settings: Any) -> None:
        self._settings = settings
        self._session = aioboto3.Session()
        self._ingress_queue_url: str | None = None
        self._dlq_queue_url: str | None = None

    @property
    def ingress_queue_url(self) -> str:
        if self._ingress_queue_url is None:
            msg = "call ensure_queue_urls() before using SqsClient"
            raise RuntimeError(msg)
        return self._ingress_queue_url

    @property
    def dlq_queue_url(self) -> str:
        if self._dlq_queue_url is None:
            msg = "call ensure_queue_urls() before using SqsClient"
            raise RuntimeError(msg)
        return self._dlq_queue_url

    def _sqs_client(self):
        return self._session.client("sqs", **_client_kwargs(self._settings))

    async def ensure_queue_urls(self) -> None:
        if self._ingress_queue_url and self._dlq_queue_url:
            return
        async with self._sqs_client() as sqs:
            in_url = await sqs.get_queue_url(
                QueueName=self._settings.sqs_ingress_queue_name,
            )
            dlq_url = await sqs.get_queue_url(
                QueueName=self._settings.sqs_dlq_queue_name,
            )
            self._ingress_queue_url = in_url["QueueUrl"]
            self._dlq_queue_url = dlq_url["QueueUrl"]

    async def send_message(
        self,
        *,
        queue_url: str,
        body: str,
        message_attributes: dict[str, Any] | None = None,
    ) -> str:
        kwargs: dict[str, Any] = {"QueueUrl": queue_url, "MessageBody": body}
        if message_attributes:
            kwargs["MessageAttributes"] = message_attributes
        async with self._sqs_client() as sqs:
            out = await sqs.send_message(**kwargs)
        return out["MessageId"]

    async def send_ingress_json(self, body: str) -> str:
        return await self.send_message(queue_url=self.ingress_queue_url, body=body)

    async def send_dlq(self, body: str) -> str:
        return await self.send_message(queue_url=self.dlq_queue_url, body=body)

    async def receive_messages(
        self,
        *,
        queue_url: str,
        max_messages: int,
        visibility_timeout: int,
        wait_time_seconds: int,
        attribute_names: list[str] | None = None,
    ) -> list[ReceivedMessage]:
        attrs = attribute_names or ["ApproximateReceiveCount"]
        async with self._sqs_client() as sqs:
            out = await sqs.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=min(max(1, max_messages), 10),
                VisibilityTimeout=visibility_timeout,
                WaitTimeSeconds=wait_time_seconds,
                MessageSystemAttributeNames=attrs,
            )
        raw = out.get("Messages") or []
        result: list[ReceivedMessage] = []
        for m in raw:
            rh = m["ReceiptHandle"]
            b = m.get("Body") or ""
            rc_str = (m.get("Attributes") or {}).get("ApproximateReceiveCount", "1")
            try:
                rc = max(1, int(rc_str))
            except ValueError:
                rc = 1
            result.append(
                ReceivedMessage(body=b, receipt_handle=rh, receive_count=rc),
            )
        return result

    async def delete_message(self, *, queue_url: str, receipt_handle: str) -> None:
        async with self._sqs_client() as sqs:
            await sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)

    async def change_visibility(
        self,
        *,
        queue_url: str,
        receipt_handle: str,
        visibility_timeout: int,
    ) -> None:
        async with self._sqs_client() as sqs:
            await sqs.change_message_visibility(
                QueueUrl=queue_url,
                ReceiptHandle=receipt_handle,
                VisibilityTimeout=visibility_timeout,
            )
