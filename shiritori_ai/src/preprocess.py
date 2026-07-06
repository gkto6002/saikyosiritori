"""Compatibility wrapper for building a normalized reading dictionary."""

from __future__ import annotations

import argparse
from pathlib import Path

from dataset import build_and_write_dataset, parse_jmdict, read_csv_records, write_records_csv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--input", help="CSV file with a reading column")
    source_group.add_argument("--jmdict", help="JMdict XML file")
    parser.add_argument("--output", required=True, help="Output CSV path")
    parser.add_argument("--max_words", type=int, help="Maximum number of normalized words")
    parser.add_argument("--random-seed", type=int, default=0)
    parser.add_argument("--pool-multiplier", type=int, default=1)
    parser.add_argument(
        "--no-prefer-common",
        action="store_true",
        help="Accepted for backwards compatibility; priority ordering is always explicit.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.input:
        records = read_csv_records(args.input)
    else:
        records, _stats = parse_jmdict(args.jmdict)

    if args.max_words is not None:
        records = build_and_write_dataset(
            records,
            dict_size=args.max_words,
            random_seed=args.random_seed,
            output_path=args.output,
            pool_multiplier=args.pool_multiplier,
        )
    else:
        write_records_csv(records, args.output)

    print(f"processed_words={len(records)}")
    print(f"output={args.output}")


if __name__ == "__main__":
    main()
