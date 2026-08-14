import argparse


def main():
    parser = argparse.ArgumentParser(description="Visual Agent manual benchmark annotation tool")
    parser.add_argument("--review", action="store_true", help="Open candidate review mode (requires frozen GT)")
    args = parser.parse_args()
    if args.review:
        from .review_app import main as run
    else:
        from .gt_app import main as run
    run()


if __name__ == "__main__": main()
