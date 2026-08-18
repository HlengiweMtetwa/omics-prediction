"""Command-line entry point.

    python -m omics_wbe.cli check-sources
    python -m omics_wbe.cli stage-one [--force]
    python -m omics_wbe.cli run [--force]
    python -m omics_wbe.cli report
    python -m omics_wbe.cli verify
    python -m omics_wbe.cli catalog [--layer genomics] [--class non_communicable]
    python -m omics_wbe.cli archives
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

from omics_wbe.config import DEFAULT_CONFIG, RESULTS_DIR


def _cmd_check_sources(args) -> int:
    from omics_wbe.ingest.sources import REGISTRY, availability_report

    report = availability_report()
    missing_any = False
    for key, status in report.items():
        source = REGISTRY[key]
        mark = "OK  " if status["available"] else "MISS"
        print(f"[{mark}] {key:14s} {source.title}")
        print(f"        licence: {source.licence}")
        print(f"        scope:   {source.spatial_scope} | {source.temporal_scope}")
        for criterion in source.selection_criteria:
            print(f"        - {criterion}")
        for path in status["missing"]:
            missing_any = True
            print(f"        MISSING: {path}")
        print()
    if missing_any:
        print("Some raw inputs are missing. See docs/DATA_ACQUISITION.md for how to obtain them.")
        return 1
    return 0


def _cmd_stage_one(args) -> int:
    from omics_wbe.pipeline import run_stage_one

    out = run_stage_one(DEFAULT_CONFIG, force=args.force)
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "reports"}
                      for k, v in out.items()}, indent=2, default=str))
    return 0


def _cmd_run(args) -> int:
    from omics_wbe.reporting.report import write_reports
    from omics_wbe.study import headline_findings, run_study

    warnings.filterwarnings("ignore")
    results = run_study(DEFAULT_CONFIG, force=args.force)
    paths = write_reports(results["_serialisable"])
    print(json.dumps(headline_findings(results), indent=2, default=str))
    print(f"\nreport: {paths['markdown']}\n        {paths['html']}")
    return 0


def _cmd_report(args) -> int:
    from omics_wbe.reporting.report import write_reports

    results_path = RESULTS_DIR / "study_results.json"
    if not results_path.exists():
        print(f"{results_path} not found; run `python -m omics_wbe.cli run` first.", file=sys.stderr)
        return 1
    paths = write_reports()
    print(json.dumps(paths, indent=2))
    return 0


def _cmd_verify(args) -> int:
    from omics_wbe.provenance import verify_manifest

    manifest_dir = RESULTS_DIR / "manifests"
    if not manifest_dir.exists():
        print("no manifests found; run the pipeline first.", file=sys.stderr)
        return 1
    failed = 0
    for path in sorted(manifest_dir.glob("*.manifest.json")):
        report = verify_manifest(path)
        status = "OK" if not report["changed"] and not report["missing"] else "DRIFT"
        if status == "DRIFT":
            failed += 1
        print(f"[{status:5s}] {path.name}: {len(report['ok'])} ok, "
              f"{len(report['changed'])} changed, {len(report['missing'])} missing")
        for label in report["changed"]:
            print(f"          changed: {label}")
        for label in report["missing"]:
            print(f"          missing: {label}")
    return 1 if failed else 0


def _cmd_catalog(args) -> int:
    from omics_wbe.biomarkers.catalog import default_catalog

    catalog = default_catalog()
    if args.summary:
        print(json.dumps(catalog.summary(), indent=2))
        return 0
    selected = catalog.select(
        omics_layer=args.layer, disease_class=args.disease_class,
        min_tier=args.min_tier, include_normalisers=args.include_normalisers,
    )
    for bm in selected:
        print(f"{bm['biomarker_id']:26s} {bm['omics_layer']:14s} {bm['evidence_tier']:12s} {bm['name']}")
        for caveat in bm.get("caveats", []):
            print(f"{'':26s} ! {caveat}")
    print(f"\n{len(selected)} biomarker(s)")
    return 0


def _cmd_archives(args) -> int:
    from omics_wbe.ingest.sequence_archives import ArchiveQuery, build_run_inventory, check_connectivity

    query = ArchiveQuery()
    print(json.dumps(query.describe(), indent=2))
    print("\nconnectivity:")
    print(json.dumps(check_connectivity(timeout=args.timeout), indent=2))
    if args.search:
        inventory, report = build_run_inventory(query, limit=args.limit, timeout=args.timeout)
        print("\nsearch:")
        print(json.dumps(report, indent=2, default=str))
        if len(inventory):
            out = Path(args.output or "sequence_run_inventory.csv")
            inventory.to_csv(out, index=False)
            print(f"\nwrote {len(inventory)} runs to {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="omics_wbe", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check-sources", help="report which raw inputs are present").set_defaults(func=_cmd_check_sources)

    p = sub.add_parser("stage-one", help="build the analysis panels from raw inputs")
    p.add_argument("--force", action="store_true", help="rebuild even if cached")
    p.set_defaults(func=_cmd_stage_one)

    p = sub.add_parser("run", help="run the full study and write the report")
    p.add_argument("--force", action="store_true", help="rebuild panels from raw inputs")
    p.set_defaults(func=_cmd_run)

    sub.add_parser("report", help="regenerate the report from existing results").set_defaults(func=_cmd_report)
    sub.add_parser("verify", help="re-hash every manifest input and output").set_defaults(func=_cmd_verify)

    p = sub.add_parser("catalog", help="inspect the biomarker catalogue")
    p.add_argument("--layer", choices=["genomics", "transcriptomics", "proteomics", "metabolomics"])
    p.add_argument("--class", dest="disease_class",
                   choices=["communicable", "non_communicable", "amr", "exposure", "normaliser"])
    p.add_argument("--min-tier", dest="min_tier", choices=["prospective", "emerging", "established"])
    p.add_argument("--include-normalisers", action="store_true")
    p.add_argument("--summary", action="store_true", help="print catalogue summary counts only")
    p.set_defaults(func=_cmd_catalog)

    p = sub.add_parser("archives", help="show and optionally run the sequence-archive queries")
    p.add_argument("--search", action="store_true", help="execute the search (needs network access)")
    p.add_argument("--limit", type=int, default=1000)
    p.add_argument("--timeout", type=float, default=30.0)
    p.add_argument("--output")
    p.set_defaults(func=_cmd_archives)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
