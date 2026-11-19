import argparse
import sys
from pathlib import Path

# root directory
root_path = Path(__file__).resolve().parent.resolve().parents[2]

pipeline_services_path = Path(__file__).resolve().parent
src_path = pipeline_services_path / "src"

# Insert into sys.path so Python can find all packages
sys.path.insert(0, str(src_path))
sys.path.insert(0, str(pipeline_services_path))
sys.path.insert(0, str(root_path))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="City Air Tracker Pipeline Runner")
    parser.add_argument(
        "--phase",
        choices=["etl", "enrichment", "all"],
        default="etl",
        help="Specify which pipeline phase to execute: 'etl', 'enrichment', or 'all'."
    )
    parser.add_argument(
        "--mode",
        choices=["backfill", "incremental"],
        default=None,
        help="Specify the ETL mode (only used when --phase is 'etl' or 'all'). Defaults to 'incremental'."
    )
    parser.add_argument(
        "--cities",
        nargs="+",
        default=None,
        help="Optional list of cities to process (only used when --phase is 'etl' or 'all'). Defaults to config/cities.txt."
    )
    
    args = parser.parse_args()

    if (args.mode is not None or args.cities is not None) and args.phase == "enrichment":
        parser.error("--mode and --cities can only be used when --phase is 'etl' or 'all'.")

    if args.phase in ("etl", "all"):
        from pipeline.orchestration.flow import main_etl_flow
        etl_mode = args.mode or "incremental"
        print("Running Phase 1: Main ETL Flow...")
        main_etl_flow(cities=args.cities, mode=etl_mode)

    if args.phase in ("enrichment", "all"):
        from pipeline.orchestration.flow import llm_enrichment_flow
        print("Running Phase 2: LLM Enrichment Flow...")
        llm_enrichment_flow()