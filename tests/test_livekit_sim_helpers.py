from ais.voice.livekit_sim import normalize_livekit_url, slug_delivery_id


def test_normalize_livekit_url() -> None:
    assert normalize_livekit_url("https://x.livekit.cloud") == "wss://x.livekit.cloud"
    assert normalize_livekit_url("wss://x.livekit.cloud/path") == "wss://x.livekit.cloud/path"


def test_slug_delivery_id() -> None:
    assert slug_delivery_id("D_123-x") == "D-123-x"
