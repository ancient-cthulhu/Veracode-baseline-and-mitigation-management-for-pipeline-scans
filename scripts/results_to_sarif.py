#!/usr/bin/env python3
"""Convert Veracode Pipeline Scan results into a single SARIF 2.1.0 report.

Handles several results files in one pass (one per scanned artifact) and merges
them into one run so GitHub code scanning shows a single Veracode tool.

Usage:
    results_to_sarif.py --output veracode.sarif scan-results/*.json
    results_to_sarif.py --output veracode.sarif --source-path-prefix src/main/java results.json
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

TAG_RE = re.compile(r"<[^>]+>")

# Veracode severity -> SARIF level and CVSS-like score used by code scanning
SEVERITY_MAP = {
    5: ("error", "9.0"),
    4: ("error", "7.5"),
    3: ("warning", "5.0"),
    2: ("note", "3.0"),
    1: ("note", "1.0"),
    0: ("none", "0.0"),
}


def plain_text(value: str, limit: int = 1000) -> str:
    text = html.unescape(TAG_RE.sub(" ", value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def source_uri(finding: dict, prefix: str) -> str:
    source = (finding.get("files") or {}).get("source_file") or {}
    path = source.get("file") or source.get("upload_file") or "unknown"
    path = path.lstrip("/")
    if prefix:
        path = f"{prefix.rstrip('/')}/{path}"
    return path


def fingerprint(finding: dict) -> str:
    match = finding.get("flaw_match") or {}
    parts = [
        str(finding.get("cwe_id", "")),
        str(match.get("procedure_hash", "")),
        str(match.get("flaw_hash", "")),
        str(match.get("flaw_hash_ordinal", "")),
    ]
    return "-".join(parts)


def convert(results_files: list[Path], prefix: str) -> dict:
    rules: dict[str, dict] = {}
    results: list[dict] = []

    for results_file in results_files:
        try:
            data = json.loads(results_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"warning: skipping {results_file}: {exc}", file=sys.stderr)
            continue

        artifact = ", ".join(data.get("modules") or []) or results_file.stem

        for finding in data.get("findings") or []:
            cwe = str(finding.get("cwe_id", "unknown"))
            rule_id = f"CWE-{cwe}"
            try:
                severity = int(finding.get("severity", 0))
            except (TypeError, ValueError):
                severity = 0
            level, score = SEVERITY_MAP.get(severity, ("warning", "5.0"))

            if rule_id not in rules:
                rules[rule_id] = {
                    "id": rule_id,
                    "name": rule_id,
                    "shortDescription": {"text": plain_text(finding.get("issue_type", rule_id), 200)},
                    "fullDescription": {"text": plain_text(finding.get("display_text", ""), 900)},
                    "helpUri": finding.get("flaw_details_link")
                    or f"https://cwe.mitre.org/data/definitions/{cwe}.html",
                    "help": {"text": plain_text(finding.get("display_text", ""), 900)},
                    "properties": {
                        "tags": ["security", "veracode", f"external/cwe/cwe-{cwe}"],
                        "security-severity": score,
                    },
                }

            source = (finding.get("files") or {}).get("source_file") or {}
            try:
                line = max(int(source.get("line", 1)), 1)
            except (TypeError, ValueError):
                line = 1

            message = "{title}: {issue}. Found in {artifact}.".format(
                title=finding.get("title", rule_id),
                issue=plain_text(finding.get("issue_type", ""), 200),
                artifact=artifact,
            )

            results.append(
                {
                    "ruleId": rule_id,
                    "level": level,
                    "message": {"text": message},
                    "locations": [
                        {
                            "physicalLocation": {
                                "artifactLocation": {"uri": source_uri(finding, prefix)},
                                "region": {"startLine": line},
                            }
                        }
                    ],
                    "partialFingerprints": {"veracodeFlawMatch": fingerprint(finding)},
                    "properties": {
                        "veracodeSeverity": severity,
                        "veracodeIssueId": finding.get("issue_id"),
                    },
                }
            )

    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "Veracode Pipeline Scan",
                        "informationUri": "https://docs.veracode.com/r/Pipeline_Scan",
                        "rules": list(rules.values()),
                    }
                },
                "results": results,
            }
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", nargs="+", help="Pipeline Scan results JSON files")
    parser.add_argument("--output", required=True, help="SARIF file to write")
    parser.add_argument(
        "--source-path-prefix",
        default="",
        help="Prefix prepended to finding paths so they resolve in the repository",
    )
    args = parser.parse_args()

    files = [Path(p) for p in args.results if Path(p).is_file()]
    sarif = convert(files, args.source_path_prefix)
    Path(args.output).write_text(json.dumps(sarif, indent=2), encoding="utf-8")
    print(f"Wrote {len(sarif['runs'][0]['results'])} result(s) to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
