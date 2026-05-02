"""CLI entry: `ais-demo` or `python -m ais.demo.cli`."""

from __future__ import annotations

import asyncio
import json
import os
import sys


def main() -> None:
    base = os.environ.get("AIS_BASE_URL", "http://127.0.0.1:8000")
    delivery_id = os.environ.get("DEMO_DELIVERY_ID", "D-demo-bike")

    async def _run() -> None:
        from ais.demo.scenario import run_bike_breakdown_demo

        out = await run_bike_breakdown_demo(base_url=base, delivery_id=delivery_id)
        json.dump(out, sys.stdout, indent=2)
        sys.stdout.write("\n")

    asyncio.run(_run())


if __name__ == "__main__":
    main()
