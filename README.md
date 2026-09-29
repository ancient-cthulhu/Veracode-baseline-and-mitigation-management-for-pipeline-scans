# Veracode Baseline and Mitigations Management for Pipeline Scans

**English** | [Español](README.es.md)

Reusable GitHub Actions workflow for Veracode Pipeline Scan with centralised, branch based baseline management.

The default branch of each consuming repository is the security baseline. Every push to it refreshes the stored baselines. Every other branch and pull request is scanned as a delta against those baselines, so a build only fails on findings the change actually introduced.

## Why

Pipeline Scan is stateless. On an existing application the first scan returns a backlog of findings nobody introduced today, so a plain "fail on High" gate breaks every pull request and teams end up disabling it.

A baseline filters out known findings and gates only on new ones. The rule becomes **"do not make it worse"**:

- Developers only fix what their change introduces.
- The gate can be blocking from day one, even with existing debt.
- Existing debt is still tracked and remediated through Veracode policy scans and platform mitigations, not in each pull request.

Baselines are generated only from the baseline branch, stored in a separate repository written only by CI, and every refresh is a git commit. A feature branch cannot baseline away its own findings, and every change is auditable.

## The model

| Event | Mode | What happens |
|---|---|---|
| Push to the baseline branch | `baseline` | Rescan and overwrite the stored baselines. Never gates |
| Pull request / push to any other branch | `delta` | Scan against the stored baselines and gate on new findings |
| `workflow_dispatch` or weekly `schedule` on the baseline branch | `baseline` | On demand or weekly refresh (picks up newly approved mitigations) |

Baselines are keyed by the **baseline branch**, never by the running branch, so every branch and pull request compares against the same source of truth.

```
baselines/<owner>_<repo>/<baseline-branch>/<artifact-file-name>/
  ├── baseline.json                     # full scan results
  └── baseline-mitigated-findings.json  # approved mitigations only
```

## Quick start

1. Add the [secrets](#secrets).
2. Copy [`examples/veracode.yml`](examples/veracode.yml) to `.github/workflows/veracode.yml` and set the push branch to your default branch. Minimum caller:

   ```yaml
   on:
     push:
       branches: [main]
     pull_request:
     workflow_dispatch:

   permissions:
     contents: read

   jobs:
     veracode:
       uses: Veracode-CSE-Demos/veracode-ci-templates/.github/workflows/veracode-pipeline.yml@main
       secrets: inherit
   ```

3. Run the workflow once on the default branch with `mode: baseline`. Until then, delta scans report `No baseline` and pass (unless `strict_baselines: true`).
4. Make the Veracode job a **required status check** on the default branch.

**Using your own copy (recommended for production):** fork this repo and set `templates_repo` (must match the repo in `uses:`) and `baseline_repo` (can be a separate private repo).

## Baseline types

| `baseline_type` | Compares against | Fails the build on | Needs app name | Scans per artifact |
|---|---|---|---|---|
| `full` (default) | `baseline.json` | New findings only | No | 1 |
| `mitigated` | `baseline-mitigated-findings.json` | Any unmitigated finding, old or new | Yes | 1 |
| `both` | Both files | Either comparison failing | Yes | 2 |

- **`full`**: the delta gate. Use it for applications with existing debt. This is the normal choice.
- **`mitigated`**: a policy style gate, not a delta gate. Only findings with an **approved** mitigation in the Veracode platform are suppressed (proposed ones are ignored). Built by [`vcpipemit.py`](https://github.com/veracode/veracode-pipeline-mitigation), matching by CWE, file and line (±3 lines). Use it for mature applications where anything not formally accepted must block. Needs a completed policy scan on the application profile.
- **`both`**: shows both views in the summary. Gates as strictly as `mitigated`. Useful when migrating from `full` to `mitigated`.

When an app name is set, baseline runs always produce both files, so you can switch type later without a new refresh.

## Inputs

| Input | Default | Purpose |
|---|---|---|
| `mode` | `auto` | `auto`, `baseline` or `delta`. `delta` on the baseline branch tests the gate without overwriting |
| `baseline_branch` | repo default branch | Branch that owns the baselines (for example `develop` in GitFlow) |
| `baseline_repo` | `Veracode-CSE-Demos/veracode-ci-templates` | Repository that stores baseline files |
| `baseline_store_branch` | store default branch | Branch in the store where baselines are committed |
| `baseline_type` | `full` | `full`, `mitigated` or `both` |
| `templates_repo` | `Veracode-CSE-Demos/veracode-ci-templates` | Repo holding this workflow. Must match `uses:` |
| `fail_on_severity` | `Very High, High` | Severities that fail a delta scan |
| `fail_on_cwe` | empty | CWEs that fail regardless of severity, for example `80` for XSS |
| `policy_name` | empty | Veracode policy to rate findings. Veracode default policies only |
| `strict_baselines` | `false` | Fail when an artifact has no baseline. Enable once all repos have one |
| `artifacts_glob` | empty | Scan existing artifacts and skip the autopackager. Only sees files in the repo checkout |
| `package_source` | `.` | Source path for `veracode package` |
| `artifact_extensions` | `jar war ear dll exe nupkg zip tar tgz tar.gz` | Extensions treated as scannable |
| `scan_timeout` | `60` | Timeout in minutes |
| `java_version` / `python_version` | `17` / `3.12` | Toolchain versions |
| `runs_on` | `ubuntu-latest` | Runner label |
| `upload_results` | `true` | Attach raw results to the run (14 days) |
| `upload_sarif` | `false` | Publish delta findings to code scanning. Needs `security-events: write` |
| `source_path_prefix` | empty | Prefix so SARIF paths resolve, for example `src/main/java` |
| `app_name` | empty | Veracode application profile name. Overrides `VERACODE_APP_NAME` |

Baselines are keyed by artifact **file name**. Keep names stable (no versions or build IDs), or every build will miss its baseline.

## Secrets

| Secret | Required | Purpose |
|---|---|---|
| `VERACODE_API_ID` / `VERACODE_API_KEY` | yes | Veracode API credentials |
| `CI_PUSH_TOKEN_VCT` | yes | Fine grained token: read on the templates repo, read and write on the baseline repo |
| `VERACODE_APP_NAME` | for `mitigated` / `both` | Exact application profile name |

Credentials are written to `~/.veracode/credentials`, never to a command line. Pull requests from forks get no secrets and fail with an explanation; do not work around it with `pull_request_target`.

## Good practice

- **Require the check.** If a failing pull request is merged, the next refresh absorbs its findings into the baseline.
- **Keep running policy scans** on the baseline branch. The baseline hides debt from pull requests by design; the platform is where it stays visible.
- **Keep the weekly refresh** so the mitigated baseline follows platform decisions.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Every artifact reports `No baseline` | No refresh yet. Run on the baseline branch with `mode: baseline` |
| Baselines exist but are not found | Artifact file name changed. Check the store path in the run plan table |
| Mitigated baseline is empty | No completed policy scan, profile name mismatch, or no `APPROVED` mitigations |
| `veracode package` finds nothing | Project not buildable by the autopackager. Fix packaging or use `artifacts_glob` |
| Could not push baselines | Token lacks write access to the baseline repo |

## Repository layout

```
.github/workflows/veracode-pipeline.yml   reusable workflow
.github/workflows/validate.yml            lint and self test
scripts/                                  summary and SARIF helpers
examples/veracode.yml                     caller template
baselines/                                baseline store
```

## References

- [Pipeline Scan](https://docs.veracode.com/r/Pipeline_Scan)
- [Pipeline Scan parameters](https://docs.veracode.com/r/r_pipeline_scan_commands)
- [veracode package](https://docs.veracode.com/r/veracode_package)
- [veracode/veracode-pipeline-mitigation](https://github.com/veracode/veracode-pipeline-mitigation)
