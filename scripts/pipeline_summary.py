#!/usr/bin/env python3
"""Render a Markdown summary for Veracode Pipeline Scan runs.

Reads a TSV control file produced by the workflow and writes a Markdown table
(one row per artifact) plus a severity breakdown taken from each artifact's
Pipeline Scan results file.

TSV columns (tab separated, no header):
    artifact_name <TAB> status <TAB> results_file

`results_file` may be empty when no scan output was produced.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

SEVERITY_NAMES = {
    5: "Very High",
    4: "High",
    3: "Medium",
    2: "Low",
    1: "Very Low",
    0: "Informational",
}

STATUS_ICONS = {
    "PASSED": "✅ Passed",
    "FAILED": "❌ Failed",
    "CREATED": "✅ Created",
    "MISSING": "⚠️ No baseline",
    "ERROR": "❌ Error",
    "SKIPPED": "➖ Skipped",
}


def load_findings(results_file: str) -> list[dict]:
    if not results_file:
        return []
    path = Path(results_file)
    if not path.is_file():
        return []
    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:  # pragma: no cover - defensive
        print(f"warning: could not read {path}: {exc}", file=sys.stderr)
        return []
    findings = data.get("findings")
    return findings if isinstance(findings, list) else []


def severity_counts(findings: list[dict]) -> dict[int, int]:
    counts: dict[int, int] = {}
    for finding in findings:
        try:
            severity = int(finding.get("severity", -1))
        except (TypeError, ValueError):
            severity = -1
        counts[severity] = counts.get(severity, 0) + 1
    return counts


def read_rows(rows_file: str) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    path = Path(rows_file)
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        while len(parts) < 3:
            parts.append("")
        rows.append((parts[0], parts[1], parts[2]))
    return rows


def render(rows: list[tuple[str, str, str]], title: str, findings_header: str) -> str:
    out: list[str] = [f"## {title}", ""]

    if not rows:
        out.append("No artifacts were processed.")
        out.append("")
        return "\n".join(out)

    out.append(f"| Artifact | Result | {findings_header} | Very High | High | Medium | Low |")
    out.append("|---|---|---:|---:|---:|---:|---:|")

    totals: dict[int, int] = {}
    total_findings = 0

    for name, status, results_file in rows:
        findings = load_findings(results_file)
        counts = severity_counts(findings)
        total_findings += len(findings)
        for severity, count in counts.items():
            totals[severity] = totals.get(severity, 0) + count
        label = STATUS_ICONS.get(status.upper(), status)
        out.append(
            "| `{name}` | {label} | {total} | {vh} | {h} | {m} | {low} |".format(
                name=name,
                label=label,
                total=len(findings),
                vh=counts.get(5, 0),
                h=counts.get(4, 0),
                m=counts.get(3, 0),
                low=counts.get(2, 0),
            )
        )

    out.append(
        "| **Total** | | **{total}** | **{vh}** | **{h}** | **{m}** | **{low}** |".format(
            total=total_findings,
            vh=totals.get(5, 0),
            h=totals.get(4, 0),
            m=totals.get(3, 0),
            low=totals.get(2, 0),
        )
    )
    out.append("")
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", required=True, help="TSV control file")
    parser.add_argument("--title", default="Veracode Pipeline Scan", help="Summary heading")
    parser.add_argument(
        "--findings-header",
        default="Findings",
        help="Column header for the findings count",
    )
    parser.add_argument(
        "--output",
        default=os.environ.get("GITHUB_STEP_SUMMARY", "-"),
        help="File to append the summary to, or - for stdout",
    )
    parser.add_argument("--note", action="append", default=[], help="Extra note appended below the table")
    args = parser.parse_args()

    markdown = render(read_rows(args.rows), args.title, args.findings_header)
    for note in args.note:
        markdown += f"\n_{note}_\n"

    if args.output == "-":
        sys.stdout.write(markdown)
    else:
        with open(args.output, "a", encoding="utf-8") as handle:
            handle.write(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
