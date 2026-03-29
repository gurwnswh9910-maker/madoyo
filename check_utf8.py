from pathlib import Path
import sys


TEXT_SUFFIXES = {
    ".py",
    ".md",
    ".txt",
    ".json",
    ".yml",
    ".yaml",
    ".toml",
    ".ini",
    ".cfg",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".css",
    ".scss",
    ".html",
    ".sql",
    ".sh",
    ".ps1",
    ".bat",
}

SKIP_DIR_NAMES = {
    ".git",
    "__pycache__",
    "node_modules",
    ".next",
    "dist",
    "build",
}


def should_check(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in TEXT_SUFFIXES


def iter_files(root: Path):
    for path in root.rglob("*"):
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        if should_check(path):
            yield path


def main() -> int:
    root = Path(__file__).resolve().parent
    failed_paths = []

    for path in iter_files(root):
        try:
            path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            failed_paths.append(path.relative_to(root))

    if failed_paths:
        print("Non-UTF-8 files found:")
        for failed_path in failed_paths:
            print(f" - {failed_path}")
        return 1

    print("All checked text files are valid UTF-8.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
