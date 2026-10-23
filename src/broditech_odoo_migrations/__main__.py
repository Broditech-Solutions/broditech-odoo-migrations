"""Print installed paths without importing Odoo or connecting to a database."""

import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--pre-upgrade-script", action="store_true")
    group.add_argument("--upgrade-path", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    if args.pre_upgrade_script:
        print(root / "pre_upgrade.py")
    else:
        print(root.parent / "odoo" / "upgrade")


if __name__ == "__main__":
    main()
