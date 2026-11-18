import argparse
import sys
from pathlib import Path

# Define root directory
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
    
    args = parser.parse_args()

    if args.phase in ("etl", "all"):
        from pipeline.orchestration.flow import main_etl_flow
        print("Running Phase 1: Main ETL Flow...")
        main_etl_flow(mode='backfill')

    if args.phase in ("enrichment", "all"):
        from pipeline.orchestration.flow import llm_enrichment_flow
        print("Running Phase 2: LLM Enrichment Flow...")
        llm_enrichment_flow()