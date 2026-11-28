from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile


SERVICE_DIR = Path(__file__).resolve().parent
BUILD_DIR = SERVICE_DIR / "build"
ARCHIVE_PATH = BUILD_DIR / "city_air_tracker_lambda.zip"


def main() -> None:
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="lambda-package-") as temp_dir:
        package_dir = Path(temp_dir)
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--requirement",
                str(SERVICE_DIR / "requirements-lambda.txt"),
                "--target",
                str(package_dir),
            ],
            check=True,
        )

        shutil.copytree(
            SERVICE_DIR / "src" / "pipeline",
            package_dir / "pipeline",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        shutil.copytree(SERVICE_DIR / "contracts", package_dir / "contracts")

        with zipfile.ZipFile(ARCHIVE_PATH, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in package_dir.rglob("*"):
                if path.is_file():
                    archive.write(path, path.relative_to(package_dir))

    print(f"Created Lambda deployment package: {ARCHIVE_PATH}")


if __name__ == "__main__":
    main()
