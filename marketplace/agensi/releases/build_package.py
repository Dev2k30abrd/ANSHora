#!/usr/bin/env python3
"""
Release Packager for Agensi Marketplace Skill:
ANSHora — Business Intelligence Analyst (anshora-business-intelligence-analyst)

Builds versioned release ZIP archives with SKILL.md at the archive root.
Preserves existing releases.
"""

import argparse
import hashlib
import os
import sys
import zipfile
from pathlib import Path

# Fix Windows console encoding
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

BASE_DIR = Path(__file__).resolve().parent.parent
SOURCE_DIR = BASE_DIR / "anshora-business-intelligence-analyst"
RELEASES_DIR = BASE_DIR / "releases"

EXCLUDED_NAMES = {
    "__pycache__", ".git", ".env", ".DS_Store", "Thumbs.db", ".pytest_cache"
}
EXCLUDED_EXTENSIONS = {
    ".pyc", ".pyo", ".pyd", ".sqlite", ".sqlite3", ".db", ".log"
}


def build_release_zip(version="v1.0.3"):
    zip_name = f"anshora-business-intelligence-analyst-{version}.zip"
    zip_output_path = RELEASES_DIR / zip_name

    print(f"Building release ZIP from: {SOURCE_DIR}")
    print(f"Target destination:       {zip_output_path}")

    if not SOURCE_DIR.exists():
        print(f"ERROR: Source directory not found: {SOURCE_DIR}")
        return 1

    RELEASES_DIR.mkdir(parents=True, exist_ok=True)
    if zip_output_path.exists():
        zip_output_path.unlink()

    included_entries = []

    with zipfile.ZipFile(zip_output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(SOURCE_DIR):
            dirs[:] = [d for d in dirs if d not in EXCLUDED_NAMES and not d.startswith(".")]

            for file_name in sorted(files):
                if file_name in EXCLUDED_NAMES:
                    continue
                ext = os.path.splitext(file_name)[1].lower()
                if ext in EXCLUDED_EXTENSIONS:
                    continue

                full_path = Path(root) / file_name
                arcname = str(full_path.relative_to(SOURCE_DIR)).replace("\\", "/")
                zf.write(full_path, arcname=arcname)
                included_entries.append((arcname, full_path.stat().st_size))

    h = hashlib.sha256()
    with open(zip_output_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    sha256 = h.hexdigest()
    zip_size = zip_output_path.stat().st_size

    print("\nPackage build successful!")
    print(f"Total entries packaged: {len(included_entries)}")
    for arcname, sz in included_entries:
        print(f"  - {arcname} ({sz:,} bytes)")
    print(f"\nArchive File:   {zip_output_path.name}")
    print(f"Archive Size:   {zip_size:,} bytes")
    print(f"SHA-256 Digest: {sha256}")

    checksum_file = zip_output_path.with_suffix(".zip.sha256")
    checksum_file.write_text(f"{sha256}  {zip_output_path.name}\n", encoding="utf-8")
    print(f"Checksum File:  {checksum_file.name}")

    return 0


def main():
    parser = argparse.ArgumentParser(description="Build Agensi Skill Release Archive")
    parser.add_argument("--version", default="v1.0.3", help="Release version tag (e.g. v1.0.3)")
    args = parser.parse_args()
    return build_release_zip(args.version)


if __name__ == "__main__":
    sys.exit(main())
