"""Validate and create the exact submission ZIP layout required by the project."""

import argparse
import zipfile
from pathlib import Path


EXCLUDED_PARTS = {
    ".git",
    ".venv",
    ".pytest_cache",
    "__pycache__",
    "datasets",
    "results",
    "submission",
}


def should_include(
    path: Path,
    repository: Path,
    excluded_files: set[Path] | None = None,
) -> bool:
    relative = path.relative_to(repository)
    if excluded_files and path.resolve() in excluded_files:
        return False
    return not any(part in EXCLUDED_PARTS for part in relative.parts)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the required project ZIP")
    parser.add_argument("--student-id-1", required=True)
    parser.add_argument("--student-id-2", required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, default=Path("submission"))
    args = parser.parse_args()

    repository = args.repository.resolve()
    report = args.report.resolve()
    video = args.video.resolve()
    if not report.is_file() or report.suffix.lower() != ".pdf":
        raise SystemExit("--report must point to an existing PDF")
    if not video.is_file() or video.suffix.lower() != ".mp4":
        raise SystemExit("--video must point to an existing MP4")

    project_name = f"CN-project-{args.student_id_1}-{args.student_id_2}"
    args.output_dir.mkdir(parents=True, exist_ok=True)
    zip_path = args.output_dir / f"{project_name}.zip"
    excluded_files = {report, video, zip_path.resolve()}
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(repository.rglob("*")):
            if path.is_file() and should_include(path, repository, excluded_files):
                archive.write(
                    path,
                    Path(project_name) / "Code" / path.relative_to(repository),
                )
        archive.write(report, Path(project_name) / "Report.pdf")
        archive.write(video, Path(project_name) / "Video.mp4")
    print(zip_path)


if __name__ == "__main__":
    main()
