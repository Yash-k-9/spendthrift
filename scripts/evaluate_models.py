"""Train all six models on the built-in data and the demo family, and print how well each performs.

Run from the project root:  python scripts/evaluate_models.py [--months 12]

See budget/evaluation.py for what each number means.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from budget import evaluation, sample_data  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--months", type=int, default=sample_data.DEFAULT_MONTHS,
                        help="months of demo data to train and test on")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")   # Windows consoles default to cp1252
    print(evaluation.report(evaluation.evaluate_all(months=args.months)))


if __name__ == "__main__":
    main()
