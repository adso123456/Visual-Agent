from pathlib import Path

from .gt_store import GroundTruthStore


def main():
    root = Path(__file__).resolve().parents[1]
    print(GroundTruthStore(root).freeze())


if __name__ == "__main__": main()
