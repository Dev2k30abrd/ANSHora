#!/usr/bin/env python3
"""
Agensi Marketplace Package Validation Script for:
ANSHora — Business Intelligence Analyst (anshora-business-intelligence-analyst)

Validates:
1. Required directory layout and file existence.
2. SKILL.md YAML frontmatter and section completeness.
3. Reference documentation existence and internal link integrity.
4. scripts/analyze_csv.py syntax, size (<20 KB), stdlib-only imports, and safety.
5. Security scan: secret tokens, banned files (.env, .git, caches, credentials).
6. ZIP archive structure (SKILL.md at root, no forbidden entries, SHA-256).
"""

import ast
import hashlib
import json
import os
import re
import sys
import zipfile
from pathlib import Path

REQUIRED_FILES = [
    "SKILL.md",
    "README.md",
    "requirements.txt",
    "references/analytical-methodology.md",
    "references/financial-formulas.md",
    "references/data-quality-rules.md",
    "references/evidence-and-reporting.md",
    "references/optional-agensi-tools.md",
    "references/privacy-and-safety.md",
    "scripts/analyze_csv.py",
    "examples/sample-business-data.csv",
    "examples/expected-analysis.md",
]

FORBIDDEN_FILE_PATTERNS = [
    r"\.git($|/|\\)",
    r"\.env($|\..*)",
    r"node_modules",
    r"__pycache__",
    r"\.py[co]$",
    r"\.sqlite3?$",
    r"\.db$",
    r"\.DS_Store",
    r"\.log$",
]

SECRET_PATTERNS = [
    (r"sk-[a-zA-Z0-9]{20,}", "OpenAI API Key pattern"),
    (r"ghp_[a-zA-Z0-9]{20,}", "GitHub Personal Access Token"),
    (r"AIza[0-9A-Za-z-_]{35}", "Google API Key"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "Private Key"),
    (r"(?i)client_secret\s*[:=]\s*['\"][a-zA-Z0-9_-]{16,}['\"]", "OAuth client secret"),
    (r"(?i)bearer\s+[a-zA-Z0-9_\-\.]{30,}", "Bearer Token"),
]

STDLIB_ALLOWLIST = {
    "argparse", "csv", "json", "math", "re", "sys", "os", "collections",
    "datetime", "pathlib", "typing", "io", "copy", "itertools", "functools",
    "string", "decimal", "fractions", "statistics"
}


def validate_source_directory(pkg_dir: Path) -> dict:
    results = {"errors": [], "warnings": [], "passed": []}

    # 1. Required files
    for rel_path in REQUIRED_FILES:
        target = pkg_dir / rel_path
        if not target.exists():
            results["errors"].append(f"Missing required file: {rel_path}")
        else:
            results["passed"].append(f"Found required file: {rel_path}")

    # 2. Validate SKILL.md
    skill_md = pkg_dir / "SKILL.md"
    if skill_md.exists():
        content = skill_md.read_text(encoding="utf-8")
        if not content.startswith("---"):
            results["errors"].append("SKILL.md missing opening YAML frontmatter '---'")
        else:
            parts = content.split("---", 2)
            if len(parts) < 3:
                results["errors"].append("SKILL.md missing closing YAML frontmatter '---'")
            else:
                frontmatter = parts[1]
                required_fm_keys = ["name", "description", "summary", "version", "tags", "keywords", "use_cases"]
                for k in required_fm_keys:
                    if f"{k}:" not in frontmatter:
                        results["errors"].append(f"SKILL.md frontmatter missing key: {k}")
                    else:
                        results["passed"].append(f"SKILL.md frontmatter contains: {k}")

        # Check references mentioned in SKILL.md
        refs_found = re.findall(r"references/([a-zA-Z0-9_\-]+\.md)", content)
        for ref in refs_found:
            ref_path = pkg_dir / "references" / ref
            if not ref_path.exists():
                results["errors"].append(f"Broken reference link in SKILL.md: references/{ref}")
            else:
                results["passed"].append(f"Verified reference exists: references/{ref}")

    # 3. Validate scripts/analyze_csv.py
    script_path = pkg_dir / "scripts" / "analyze_csv.py"
    if script_path.exists():
        size_bytes = script_path.stat().st_size
        if size_bytes > 20480:
            results["errors"].append(f"scripts/analyze_csv.py exceeds 20 KB guideline: {size_bytes} bytes")
        else:
            results["passed"].append(f"scripts/analyze_csv.py size within limit: {size_bytes} bytes (<20 KB)")

        code = script_path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(code, filename=str(script_path))
            results["passed"].append("scripts/analyze_csv.py is valid Python syntax")
            
            # Check imports and dangerous calls
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        base = alias.name.split(".")[0]
                        if base not in STDLIB_ALLOWLIST:
                            results["errors"].append(f"Non-allowlisted import in analyze_csv.py: {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        base = node.module.split(".")[0]
                        if base not in STDLIB_ALLOWLIST:
                            results["errors"].append(f"Non-allowlisted import-from in analyze_csv.py: {node.module}")
                elif isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name) and node.func.id in ("eval", "exec", "__import__"):
                        results["errors"].append(f"Forbidden dynamic execution call in analyze_csv.py: {node.func.id}")
        except SyntaxError as e:
            results["errors"].append(f"Syntax error in scripts/analyze_csv.py: {e}")

    # 4. Security and hygiene scan across package directory
    for root, dirs, files in os.walk(pkg_dir):
        rel_root = Path(root).relative_to(pkg_dir)
        for pattern in FORBIDDEN_FILE_PATTERNS:
            if re.search(pattern, str(rel_root), re.IGNORECASE):
                results["errors"].append(f"Prohibited directory detected: {rel_root}")

        for file_name in files:
            file_rel = rel_root / file_name
            file_str = str(file_rel)
            for pattern in FORBIDDEN_FILE_PATTERNS:
                if re.search(pattern, file_str, re.IGNORECASE):
                    results["errors"].append(f"Prohibited file detected: {file_str}")

            full_file_path = Path(root) / file_name
            if full_file_path.is_file() and full_file_path.stat().st_size < 1000000:
                try:
                    text = full_file_path.read_text(encoding="utf-8", errors="ignore")
                    for pattern, label in SECRET_PATTERNS:
                        if re.search(pattern, text):
                            results["errors"].append(f"Potential secret ({label}) in {file_str}")
                except Exception as e:
                    results["warnings"].append(f"Could not scan {file_str}: {e}")

    return results


def validate_zip_archive(zip_path: Path, expected_pkg_dir: Path) -> dict:
    results = {"errors": [], "warnings": [], "passed": [], "sha256": None, "size_bytes": 0, "entries": []}
    if not zip_path.exists():
        results["errors"].append(f"ZIP file does not exist: {zip_path}")
        return results

    results["size_bytes"] = zip_path.stat().st_size
    h = hashlib.sha256()
    with open(zip_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    results["sha256"] = h.hexdigest()
    results["passed"].append(f"ZIP SHA-256 computed: {results['sha256']}")

    with zipfile.ZipFile(zip_path, "r") as zf:
        namelist = zf.namelist()
        results["entries"] = namelist

        # 1. SKILL.md must be at archive root
        if "SKILL.md" not in namelist:
            results["errors"].append("SKILL.md is NOT at the root of the ZIP archive! Found entries: " + ", ".join(namelist[:5]))
        else:
            results["passed"].append("Verified SKILL.md is at archive root")

        # 2. Check no outer top-level folder wrapping the files
        has_outer_wrapping = any("/SKILL.md" in name for name in namelist) and ("SKILL.md" not in namelist)
        if has_outer_wrapping:
            results["errors"].append("ZIP archive contains an unnecessary outer wrapping folder.")
        else:
            results["passed"].append("ZIP archive structure has flat root layout (no outer folder wrapper)")

        # 3. Check all required files are in ZIP
        for req in REQUIRED_FILES:
            norm_req = req.replace("\\", "/")
            if norm_req not in namelist:
                results["errors"].append(f"Required file missing from ZIP: {norm_req}")
            else:
                results["passed"].append(f"ZIP contains required file: {norm_req}")

        # 4. Check for forbidden file patterns in ZIP
        for name in namelist:
            for pattern in FORBIDDEN_FILE_PATTERNS:
                if re.search(pattern, name, re.IGNORECASE):
                    results["errors"].append(f"Forbidden file pattern in ZIP entry: {name}")

    return results


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    import argparse
    parser = argparse.ArgumentParser(description="Package Validator")
    parser.add_argument("--version", default="v1.0.3", help="Target release version tag")
    args, _ = parser.parse_known_args()

    base_dir = Path(__file__).resolve().parent.parent
    pkg_dir = base_dir / "anshora-business-intelligence-analyst"
    releases_dir = base_dir / "releases"
    zip_path = releases_dir / f"anshora-business-intelligence-analyst-{args.version}.zip"

    print("=" * 70)
    print("ANSHORA — AGENSI MARKETPLACE SKILL PACKAGE VALIDATOR")
    print("=" * 70)
    print(f"Source Directory: {pkg_dir}")
    print(f"Target ZIP:      {zip_path}\n")

    print("[1] Validating source directory...")
    dir_results = validate_source_directory(pkg_dir)
    print(f"  Passed checks:   {len(dir_results['passed'])}")
    print(f"  Warnings:        {len(dir_results['warnings'])}")
    print(f"  Errors:          {len(dir_results['errors'])}")
    for err in dir_results["errors"]:
        print(f"    ERROR: {err}")
    for warn in dir_results["warnings"]:
        print(f"    WARNING: {warn}")

    if zip_path.exists():
        print("\n[2] Validating ZIP archive...")
        zip_results = validate_zip_archive(zip_path, pkg_dir)
        print(f"  Archive Size:    {zip_results['size_bytes']:,} bytes")
        print(f"  SHA-256:         {zip_results['sha256']}")
        print(f"  Passed checks:   {len(zip_results['passed'])}")
        print(f"  Errors:          {len(zip_results['errors'])}")
        for err in zip_results["errors"]:
            print(f"    ERROR: {err}")
    else:
        print(f"\n[2] ZIP archive not yet built at: {zip_path}")
        zip_results = {"errors": []}

    total_errors = len(dir_results["errors"]) + len(zip_results["errors"])
    print("\n" + "=" * 70)
    if total_errors == 0:
        print("RESULT: VALIDATION PASSED (0 errors)")
    else:
        print(f"RESULT: VALIDATION FAILED ({total_errors} errors)")
    print("=" * 70)

    return 0 if total_errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
