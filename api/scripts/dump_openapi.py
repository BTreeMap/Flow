"""Dump the OpenAPI schema from the FastAPI application to a JSON file.

Usage:
    python -m scripts.dump_openapi [--out path/to/openapi.json]

Default output: ../api/openapi.json (relative to repo root).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Dump OpenAPI JSON from the app")
    parser.add_argument(
        "--out",
        type=str,
        default=str(Path(__file__).resolve().parent.parent / "openapi.json"),
        help="Output path for the OpenAPI JSON file",
    )
    args = parser.parse_args()

    # Import the app to extract its OpenAPI schema
    from app.main import app  # noqa: E402

    schema = app.openapi()
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
    print(f"OpenAPI schema written to {out_path}")


if __name__ == "__main__":
    main()
