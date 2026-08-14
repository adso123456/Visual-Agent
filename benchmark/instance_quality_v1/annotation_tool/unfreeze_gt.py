import argparse
from pathlib import Path

from .gt_store import GroundTruthStore


def main():
    parser = argparse.ArgumentParser(description="Developer-only audited GT correction command")
    parser.add_argument("--reason", required=True)
    parser.add_argument("--image-id", required=True)
    parser.add_argument("--changed-field", action="append", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    GroundTruthStore(root).unfreeze(args.reason, args.image_id, args.changed_field)
    print("GT unfrozen; correction event appended.")


if __name__ == "__main__": main()
