#!/usr/bin/env python3

# Copyright (c) Juniper Networks, Inc. 2026. All rights reserved.
# MINIMUM PYTHON: 3.6 — keep this script free of 3.7+ features (no from __future__
# import annotations, no dataclasses, no walrus operator, no match statements).
# Use typing.List/Dict/Optional/Set, not list[]/dict[]/set[] builtin generics.
# Consumer repos (ssn-ssr-plugins, mist-agent) run on RHEL7 where python3 = 3.6.x.
"""Standalone drift checker for ai-keel synced resources.

This script detects modifications to files tracked in .ai-keel.lock
by comparing SHA256 checksums. No external dependencies — stdlib only.

When drift is detected, users are provided with clear instructions on how to
contribute improvements back to the ai-keel repository so all consumer repos
benefit from their enhancements.

Usage:
    python3 check-drift.py [--config .ai-keel.json] [--json]

    Exits with 0 if no drift detected, 1 if drift found.

    When drift is detected, a "How to contribute" guide is displayed with
    instructions for forking ai-keel, making changes, and opening a PR.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

if sys.version_info < (3, 6):
    sys.exit(
        "check-drift.py requires Python 3.6+. "
        "On RHEL7: use 'python36 check-drift.py' or upgrade to RHEL8/9."
    )


class DriftReport:
    """Result of drift detection analysis."""

    def __init__(
        self, clean: bool, modified: List[str], deleted: List[str], added: List[str]
    ) -> None:
        self.clean = clean
        self.modified = modified  # Files with different SHA256
        self.deleted = deleted  # Files in lockfile but missing on disk
        self.added = added  # Files in managed dirs but not in lockfile

    def to_dict(self) -> Dict[str, Any]:
        return {
            "clean": self.clean,
            "modified": self.modified,
            "deleted": self.deleted,
            "added": self.added,
        }


def compute_sha256(path: Path) -> str:
    """Compute SHA256 hash of a file using 8KB chunks."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def read_lockfile(lockfile_path: Path) -> Optional[Dict[str, Any]]:
    """Read and parse .ai-keel.lock JSON file."""
    if not lockfile_path.exists():
        return None
    try:
        with open(lockfile_path) as f:
            return json.load(f)  # type: ignore[no-any-return]
    except (json.JSONDecodeError, IOError) as e:
        print(f"Error reading lockfile {lockfile_path}: {e}", file=sys.stderr)
        return None


def check_drift(lockfile_data: Dict[str, Any], resources_dir: Path) -> DriftReport:
    """Compare current files against lockfile checksums.

    Args:
        lockfile_data: Parsed .ai-keel.lock (must have 'artifact_checksums' key)
        resources_dir: Repository root directory

    Returns:
        DriftReport with modified, deleted, and added file lists
    """
    artifact_checksums = lockfile_data.get("artifact_checksums", {})
    resources_deployed = lockfile_data.get("resources_deployed", [])

    modified: List[str] = []
    deleted: List[str] = []

    # Check for modified or deleted files
    for rel_path, expected_sha in artifact_checksums.items():
        full_path = resources_dir / rel_path
        if not full_path.exists():
            deleted.append(rel_path)
        else:
            try:
                actual_sha = compute_sha256(full_path)
                if actual_sha != expected_sha:
                    modified.append(rel_path)
            except (OSError, IOError) as e:
                print(f"Warning: Could not read {rel_path}: {e}", file=sys.stderr)
                modified.append(rel_path)

    # Detect added files — only in directories fully managed by ai-keel
    added: List[str] = []
    _OWNED_PREFIXES = (
        ".resources",
        ".claude",
        ".github/instructions",
        ".github/skills",
        ".github/agents",
        ".github/prompts",
        ".github/mcp-servers",
        "mcp-servers",
    )

    managed_dirs: Set[Path] = set()
    for rel_path in resources_deployed:
        parent = (resources_dir / rel_path).parent
        if parent == resources_dir:
            continue
        rel_parent = str(parent.relative_to(resources_dir))
        if any(rel_parent == p or rel_parent.startswith(p + "/") for p in _OWNED_PREFIXES):
            managed_dirs.add(parent)

    known_files: Set[str] = set(artifact_checksums.keys())
    for managed_dir in managed_dirs:
        if not managed_dir.exists():
            continue
        try:
            for f in managed_dir.rglob("*"):
                if not f.is_file():
                    continue
                rel = str(f.relative_to(resources_dir))
                if rel not in known_files:
                    added.append(rel)
        except OSError as e:
            print(f"Warning: Could not scan {managed_dir}: {e}", file=sys.stderr)

    clean = not modified and not deleted and not added
    return DriftReport(
        clean=clean,
        modified=sorted(modified),
        deleted=sorted(deleted),
        added=sorted(added),
    )


def format_drift_report(report: DriftReport, json_output: bool = False) -> str:
    """Format drift report for display."""
    if json_output:
        return json.dumps(report.to_dict(), indent=2)

    if report.clean:
        return "✓ No drift detected — all files match lockfile checksums."

    lines: List[str] = ["Drift detected:"]
    if report.modified:
        lines.append(f"\n  Modified ({len(report.modified)}):")
        for f in report.modified:
            lines.append(f"    ~ {f}")
    if report.deleted:
        lines.append(f"\n  Deleted ({len(report.deleted)}):")
        for f in report.deleted:
            lines.append(f"    - {f}")
    if report.added:
        lines.append(f"\n  Added ({len(report.added)}):")
        for f in report.added:
            lines.append(f"    + {f}")

    # Add contribution instructions
    lines.append("\n" + "=" * 70)
    lines.append("HOW TO CONTRIBUTE YOUR CHANGES")
    lines.append("=" * 70)
    lines.append("""
These files are managed by ai-keel and synced from the upstream repository.
If you've made improvements, please contribute them back to ai-keel so all
consumer repos benefit.

WORKFLOW:
  1. Fork ai-keel: https://github.com/Juniper-SSN/ai-keel

  2. In your fork, navigate to the corresponding file path and apply your
     improvements. For example, if you modified `.resources/check-drift.py`,
     edit `/.resources/check-drift.py` in your fork.

  3. Commit your changes with a clear message:
     git commit -m "improve(check-drift): [your improvement]"

  4. Push to a feature branch:
     git push origin improve/your-feature-name

  5. Open a pull request on the ai-keel repo:
     https://github.com/Juniper-SSN/ai-keel/compare/main...your-fork:improve/your-feature-name

  6. The ai-keel maintainers will review and merge your improvements.

  7. After merge, run 'ai-keel sync' in your repo to pull the updated files.

GUIDELINES:
  - Keep changes focused on the specific improvement
  - Add tests if applicable (see tests/ in ai-keel for patterns)
  - Document any new functionality or configuration
  - Follow the project's coding standards (see CONTRIBUTING.md)

RESOURCES:
  - ai-keel repository: https://github.com/Juniper-SSN/ai-keel
  - CONTRIBUTING guide: https://github.com/Juniper-SSN/ai-keel/blob/main/CONTRIBUTING.md
  - Issues / feature requests: https://github.com/Juniper-SSN/ai-keel/issues

Questions? Open an issue on the ai-keel repo or consult GETTING_STARTED.md.
""")

    return "\n".join(lines)


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Detect modifications to ai-keel synced files",
        epilog="Exits with 0 if no drift, 1 if drift detected",
    )
    parser.add_argument(
        "--config",
        default=".ai-keel.json",
        help="Path to .ai-keel.json config file (default: .ai-keel.json)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output report as JSON",
    )

    args = parser.parse_args()

    config_path = Path(args.config)
    lockfile_path = config_path.parent / ".ai-keel.lock"
    resources_dir = config_path.parent

    # Read lockfile
    lockfile_data = read_lockfile(lockfile_path)
    if lockfile_data is None:
        print(
            f"Error: {lockfile_path} not found or invalid.\n"
            "Run 'ai-keel sync' first to initialize.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Detect drift
    report = check_drift(lockfile_data, resources_dir)

    # Output report
    print(format_drift_report(report, json_output=args.json))

    # Exit with appropriate code
    sys.exit(0 if report.clean else 1)


if __name__ == "__main__":
    main()
