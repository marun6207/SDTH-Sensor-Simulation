"""Read Navy-created shared Scenario 3 truth and generate Army feeds/combined replay."""
import argparse

import generate_navybase_03_scenario as shared


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate-only", action="store_true", help="Validate complete saved scenario without writing")
    args = parser.parse_args()
    names = shared.navy_file_names() + shared.site_file_names(shared.AIR)
    missing = [name for name in names if not (shared.OUTPUT / name).is_file()]
    if missing:
        raise FileNotFoundError("Run generate_navybase_03_scenario.py then generate_airbase_03_scenario.py first. Missing: " + ", ".join(missing))
    before = shared.file_hashes(names)
    files = {name: shared.read(shared.OUTPUT / name) for name in names}
    shared.validate(files, (shared.NAVY, shared.AIR))
    army_names = [f"{shared.ARMY}/{name}.json" for name in ("eoir", "ew", "cctv", "all_sensor_events", "scenario_config")]
    replay = "scenario_03_all_sensor_events.json"
    if args.validate_only:
        outputs = {name: shared.read(shared.OUTPUT / name) for name in army_names + [replay]}
    else:
        derived = shared.build(files["shared_ground_truth/ground_truth_positions.json"],
                               files["shared_ground_truth/ground_truth_associations.json"], (shared.ARMY,))
        outputs = {name: derived[name] for name in army_names}
        outputs[replay] = shared.combine([files[f"{shared.NAVY}/all_sensor_events.json"], files[f"{shared.AIR}/all_sensor_events.json"], outputs[f"{shared.ARMY}/all_sensor_events.json"]])
    files.update(outputs)
    shared.validate(files)
    if not args.validate_only:
        shared.save_files(outputs)
        shared.validate({name: shared.read(shared.OUTPUT / name) for name in files})
    shared.require(before == shared.file_hashes(names), "Army generation changed Navy/shared inputs")
    print(f"PASS: complete Scenario 3 validation; {len(outputs[replay])} raw observations; Navy/shared inputs unchanged.")


if __name__ == "__main__":
    main()
