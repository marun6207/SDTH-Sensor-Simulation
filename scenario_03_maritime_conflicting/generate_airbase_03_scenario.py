"""Read Navy-created Scenario 3 truth and generate Airbase observations."""
import argparse

import generate_navybase_03_scenario as shared


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate-only", action="store_true", help="Validate saved Navy/shared/Airbase inputs without writing")
    args = parser.parse_args()
    names = shared.navy_file_names()
    missing = [name for name in names if not (shared.OUTPUT / name).is_file()]
    if missing:
        raise FileNotFoundError("Run generate_navybase_03_scenario.py first. Missing: " + ", ".join(missing))
    before = shared.file_hashes(names)
    files = {name: shared.read(shared.OUTPUT / name) for name in names}
    shared.validate(files, (shared.NAVY,))
    output_names = shared.site_file_names(shared.AIR)
    if args.validate_only:
        outputs = {name: shared.read(shared.OUTPUT / name) for name in output_names}
    else:
        derived = shared.build(files["shared_ground_truth/ground_truth_positions.json"],
                               files["shared_ground_truth/ground_truth_associations.json"], (shared.AIR,))
        outputs = {name: derived[name] for name in output_names}
    files.update(outputs)
    shared.validate(files, (shared.NAVY, shared.AIR))
    if not args.validate_only:
        shared.save_files(outputs)
        shared.validate({name: shared.read(shared.OUTPUT / name) for name in files}, (shared.NAVY, shared.AIR))
    shared.require(before == shared.file_hashes(names), "Airbase generation changed Navy/shared inputs")
    print("PASS: Airbase schemas, schedules, geometry and classification; Navy/shared inputs unchanged.")
    print("Run generate_armybase_03_scenario.py next for Army feeds and complete replay.")


if __name__ == "__main__":
    main()
