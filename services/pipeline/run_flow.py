import sys
from pathlib import Path

# Define root directory
root_path = Path(__file__).parent.resolve().parents[2]

pipeline_services_path = Path(__file__).resolve().parent
src_path = pipeline_services_path / "src"


# Insert into sys.path so Python can find all packages
sys.path.insert(0, str(src_path))
sys.path.insert(0, str(pipeline_services_path))
sys.path.insert(0, str(root_path))


if __name__ == "__main__":
    # Import and run flow module
    from pipeline.orchestration.flow import main_etl_flow

    main_etl_flow(mode='backfill')