"""
verify_configs.py - prove the database gives the same answers as the old code.

The bay configurations used to be 22 hard-coded methods. They now live in the
database. This compares the two, one against the other, across every vessel
and every bay, so the move is provably a change of storage and not a change
of behaviour.

    python verify_configs.py

Exit code 0 means every answer matches. If you have since edited a vessel in
the app, that vessel will show as different - which is correct, and the run
tells you exactly which one and where.
"""
import sys

import db
from core import ListLogic
from legacy_reference import LegacyLogic
from seed_data import ORIGINAL_CONFIGS

# Stow locations chosen to exercise both sides of the " U" suffix rule
# (which looks at the second-to-last digit) plus the values that fall over.
STOW_SAMPLES = ["160882", "120004", "60206", "280182", "100302", "999999",
                "12", "", "nan", None]

# extract_bay_safely() returns either an int or the string 'Unknown', so those
# are the values worth testing. The odd strings cover the defensive branches.
BAYS = list(range(0, 121)) + ["Unknown", "", "7A", "33"]


def main():
    db.init_db()
    old = LegacyLogic()
    new = ListLogic(range_provider=db.get_ranges)

    configs = list(ORIGINAL_CONFIGS)
    configs += ["1, 3-5, Generic", "1-3, 5-7, Generic", "4-6, 8-10, Generic"]
    configs += ["1-3, 5-7, 9-11", "2, 4-6", "not a config", ""]

    checks = 0
    bad = []
    for cfg in configs:
        for bay in BAYS:
            for stow in STOW_SAMPLES:
                a = old.get_custom_bay_range(bay, stow, cfg)
                b = new.get_custom_bay_range(bay, stow, cfg)
                checks += 1
                if a != b:
                    bad.append((cfg, bay, stow, a, b))

    print(f"vessels and configurations tested : {len(configs)}")
    print(f"bay values per configuration      : {len(BAYS)}")
    print(f"stow locations per bay            : {len(STOW_SAMPLES)}")
    print(f"total comparisons                 : {checks:,}")

    if not bad:
        print("\nIDENTICAL - the database returns exactly what the old code "
              "returned, for every case tested.")
        return 0

    print(f"\n{len(bad)} DIFFERENCES:")
    seen = set()
    for cfg, bay, stow, a, b in bad:
        if cfg not in seen:
            seen.add(cfg)
            print(f'\n  configuration "{cfg}"')
        if len(seen) <= 5:
            print(f"    bay={bay!r} stow={stow!r}  old={a!r}  now={b!r}")
    print(f"\nAffected configurations: {', '.join(sorted(seen))}")
    print("If you edited one of these on purpose, this is expected.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
