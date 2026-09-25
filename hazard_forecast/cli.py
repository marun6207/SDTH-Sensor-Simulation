from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .artifacts import render_html, write_artifacts
from .engine import assess_latest, run_replay
from .models import ForecastConfig, infer_domain, interpolate_track, parse_track
from .profiles import load_type_mapping
from .snapshot import canonical_json, load_snapshot, refresh_snapshot


def _read_json(path: str | Path) -> Any:
    if str(path) == "-":
        return json.load(sys.stdin)
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hazard-forecast", description="Deterministic civil-infrastructure danger forecasting")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate", help="validate a track JSON array")
    validate.add_argument("track")
    validate.add_argument("--domain", choices=("air", "surface"))

    refresh = subparsers.add_parser("osm-refresh", help="create an immutable OSM infrastructure snapshot")
    refresh.add_argument("spec")
    refresh.add_argument("--output", required=True)

    replay = subparsers.add_parser("replay", help="replay observations and generate artifacts")
    replay.add_argument("track")
    replay.add_argument("--snapshot", required=True)
    replay.add_argument("--output", required=True)
    replay.add_argument("--horizon-s", type=int, default=900)
    replay.add_argument("--step-s", type=int, default=30)
    replay.add_argument("--observation-step-s", type=int, help="interpolate the input and forecast at this cadence")
    replay.add_argument("--domain", choices=("air", "surface"))
    replay.add_argument("--track-id", default="track-001")
    replay.add_argument("--type-map", help="JSON object mapping opaque type tokens to generic mobility profiles")
    replay.add_argument("--likely-only", action="store_true", help="exclude the possible band from coverage and harm assessment")

    assess = subparsers.add_parser("assess", help="assess only the latest item in a cumulative live history")
    assess.add_argument("track", help="history JSON array, or - to read it from standard input")
    assess.add_argument("--snapshot", required=True)
    assess.add_argument("--output", help="write the current assessment to this file instead of standard output")
    assess.add_argument("--horizon-s", type=int, default=900)
    assess.add_argument("--step-s", type=int, default=30)
    assess.add_argument("--observation-step-s", type=int, help="interpolate sparse history at this cadence before assessment")
    assess.add_argument("--domain", choices=("air", "surface"))
    assess.add_argument("--track-id", default="track-001")
    assess.add_argument("--type-map", help="JSON object mapping opaque type tokens to generic mobility profiles")
    assess.add_argument("--likely-only", action="store_true", help="exclude the possible band from coverage and harm assessment")

    render = subparsers.add_parser("render", help="render an existing replay result as a Leaflet map")
    render.add_argument("result")
    render.add_argument("--output", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            observations = parse_track(_read_json(args.track))
            domain = infer_domain(observations, args.domain)
            print(json.dumps({"valid": True, "observations": len(observations), "domain": domain.model_dump()}, sort_keys=True))
            return 0
        if args.command == "osm-refresh":
            snapshot = refresh_snapshot(_read_json(args.spec), args.output)
            print(json.dumps({"snapshot_id": snapshot.manifest.snapshot_id, "features": len(snapshot.features),
                              "path": snapshot.path}, sort_keys=True))
            return 0
        if args.command == "replay":
            observations = parse_track(_read_json(args.track))
            if args.observation_step_s is not None:
                observations = interpolate_track(observations, args.observation_step_s)
            snapshot = load_snapshot(args.snapshot)
            config = ForecastConfig(horizon_s=args.horizon_s, step_s=args.step_s,
                                    include_possible_band=not args.likely_only)
            result = run_replay(observations, snapshot, config=config, domain_override=args.domain,
                                track_id=args.track_id, type_mapping=load_type_mapping(args.type_map))
            manifest = write_artifacts(result, args.output)
            print(json.dumps({"track_id": args.track_id, "snapshots": len(result["snapshots"]),
                              "output": str(Path(args.output).resolve()), "files": manifest["files"]}, sort_keys=True))
            return 0
        if args.command == "assess":
            observations = parse_track(_read_json(args.track))
            if args.observation_step_s is not None:
                observations = interpolate_track(observations, args.observation_step_s)
            snapshot = load_snapshot(args.snapshot)
            config = ForecastConfig(horizon_s=args.horizon_s, step_s=args.step_s,
                                    include_possible_band=not args.likely_only)
            result = assess_latest(observations, snapshot, config=config, domain_override=args.domain,
                                   track_id=args.track_id, type_mapping=load_type_mapping(args.type_map))
            encoded = canonical_json(result) + b"\n"
            if args.output:
                output = Path(args.output)
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(encoded)
            else:
                sys.stdout.buffer.write(encoded)
            return 0
        if args.command == "render":
            result = _read_json(args.result)
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(render_html(result), encoding="utf-8")
            print(json.dumps({"output": str(output.resolve())}, sort_keys=True))
            return 0
    except (OSError, ValueError, ValidationError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
