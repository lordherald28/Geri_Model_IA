from __future__ import annotations

import argparse
import json
from pathlib import Path

from .pipeline import dimension_tokenizer, prepare, validate, verify_offline


def main() -> None:
    parser = argparse.ArgumentParser(prog="geri-data", description="Prepare and audit the approved Geri 2.0 Spanish corpus")
    parser.add_argument("command", choices=["prepare", "validate", "tokenizer", "offline-check"])
    parser.add_argument("--config", type=Path, default=Path("configs/data-pipeline.json"))
    parser.add_argument("--output", type=Path, default=Path("data"))
    parser.add_argument("--source", action="append", dest="sources")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare(args.config, args.output, set(args.sources) if args.sources else None, args.offline)
    elif args.command == "validate":
        result = validate(args.output)
    elif args.command == "tokenizer":
        result = dimension_tokenizer(args.output)
    else:
        result = verify_offline(args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
