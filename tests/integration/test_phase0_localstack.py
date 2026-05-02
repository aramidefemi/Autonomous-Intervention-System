"""Run with: docker compose up -d && AWS_* from .env.example pytest -m integration -v"""

import os

import boto3
import pytest

from ais.config import Settings


@pytest.mark.integration
def test_list_sqs_queues_against_config() -> None:
    endpoint = os.getenv("AWS_ENDPOINT_URL")
    if not endpoint:
        pytest.skip("Set AWS_ENDPOINT_URL (e.g. http://localhost:4566) for LocalStack")

    s = Settings(
        mongo_uri="mongodb://localhost:27017",
        aws_endpoint_url=endpoint,
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID", "test"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY", "test"),
        aws_region=os.getenv("AWS_REGION", "eu-west-1"),
    )
    client = boto3.client(
        "sqs",
        endpoint_url=s.aws_endpoint_url,
        region_name=s.aws_region,
        aws_access_key_id=s.aws_access_key_id,
        aws_secret_access_key=s.aws_secret_access_key,
    )
    out = client.list_queues()
    queue_urls = out.get("QueueUrls") or []
    assert any(s.sqs_ingress_queue_name in u for u in queue_urls), (
        f"expected queue {s.sqs_ingress_queue_name!r} in {queue_urls!r}"
    )
