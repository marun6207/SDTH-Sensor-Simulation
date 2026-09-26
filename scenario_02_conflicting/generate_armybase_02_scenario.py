"""Read Airbase-created Scenario 2 truth, generate Army/Navy observations and replay."""
from __future__ import annotations

import argparse
import hashlib

import generate_airbase_02_scenario as shared


def load_airbase_inputs():
    names = shared.airbase_file_names()
    missing = [name for name in names if not (shared.OUTPUT / name).is_file()]
    if missing:
        raise FileNotFoundError(
            "Scenario 2 shared ground truth or Airbase inputs not found. "
            "Run generate_airbase_02_scenario.py first. Missing: " + ", ".join(missing)
        )
    return {name: shared.read(shared.OUTPUT / name) for name in names}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate-only", action="store_true", help="Validate the complete saved scenario without writing")
    args = parser.parse_args()
    shared.validate_scenario_01()
    files = load_airbase_inputs()
    # Protect all upstream inputs, including positions, associations and evaluation metadata.
    before = {name: hashlib.sha256((shared.OUTPUT / name).read_bytes()).hexdigest() for name in files}
    shared.validate(files, folders=(shared.AIR,))
    army_names = [f"{shared.ARMY}/{name}.json" for name in
                  ("eoir", "cctv", "ew", "all_sensor_events", "scenario_config")]
    army_names += [f"{shared.NAVY}/{name}.json" for name in
                   ("ais", "coastal_radar", "glint_sar", "all_sensor_events", "scenario_config")]
    combined_name = "scenario_02_all_sensor_events.json"
    if args.validate_only:
        outputs = {name: shared.read(shared.OUTPUT / name) for name in army_names + [combined_name]}
    else:
        # The only source of positions and associations is the saved Airbase input.
        derived = shared.build(
            files["shared_ground_truth/ground_truth_positions.json"],
            files["shared_ground_truth/ground_truth_associations.json"],
            folders=(shared.ARMY, shared.NAVY),
        )
        outputs = {name: derived[name] for name in army_names}
        outputs[combined_name] = shared.combine([
            files[f"{shared.AIR}/all_sensor_events.json"],
            outputs[f"{shared.ARMY}/all_sensor_events.json"],
            outputs[f"{shared.NAVY}/all_sensor_events.json"],
        ])
    files.update(outputs)
    shared.validate(files)
    if not args.validate_only:
        shared.save_files(outputs)
        shared.validate({name: shared.read(shared.OUTPUT / name) for name in files})
    after = {name: hashlib.sha256((shared.OUTPUT / name).read_bytes()).hexdigest() for name in before}
    shared.require(before == after, "Army generator modified Airbase/shared inputs")
    print("PASS: complete Scenario 2 schemas, schedules, geometry, identities, evidence and event ordering.")
    print("PASS: Airbase/shared inputs and all original Scenario 1 files unchanged (SHA-256).")
    print(f"Raw combined observations: {len(files[combined_name])}")


if __name__ == "__main__":
    main()
