# FileZall UX Roadmap Execution Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute the FileZall UX productization roadmap in ordered, testable milestones.

**Architecture:** This is an index plan. Each milestone has its own implementation plan and should be executed on a clean branch or a fresh continuation of `codex/ux-experience-roadmap`. Do not start a later milestone until the previous milestone is committed and tests pass.

**Tech Stack:** Python 3.12, PySide6, pytest, pytest-qt, PyInstaller, Inno Setup for final Windows package smoke.

---

## Milestone Order

1. `docs/superpowers/plans/2026-06-26-filezall-first-use-workflow.md`
2. `docs/superpowers/plans/2026-06-26-filezall-connection-manager.md`
3. `docs/superpowers/plans/2026-06-26-filezall-file-operations-experience.md`
4. `docs/superpowers/plans/2026-06-26-filezall-transfer-center.md`
5. `docs/superpowers/plans/2026-06-26-filezall-agent-resource-experience.md`
6. `docs/superpowers/plans/2026-06-26-filezall-logs-diagnostics-experience.md`
7. `docs/superpowers/plans/2026-06-26-filezall-visual-usability-polish.md`

## Completion Contract

Each milestone is complete only when:

- Its plan tasks are implemented.
- Its focused tests pass.
- Full `.\.venv\Scripts\python.exe -m pytest` passes.
- Any live integration test skipped because of missing environment variables is reported.
- The milestone is committed.

After milestone 7, run:

```powershell
powershell -ExecutionPolicy Bypass -File packaging\windows\release.ps1
```

Then smoke launch:

```powershell
$env:FILEZALL_HOME = (Join-Path (Get-Location) '.filezall-smoke-package')
$exe = Join-Path (Get-Location) 'dist\FileZall\FileZall.exe'
$process = Start-Process -FilePath $exe -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 5
if ($process.HasExited -and $process.ExitCode -ne 0) {
    throw "Packaged FileZall exited with code $($process.ExitCode)"
}
if (-not $process.HasExited) {
    Stop-Process -Id $process.Id -Force
}
```

## Risk Controls

- Keep Quick Connect behavior working after every milestone.
- Do not store plaintext passwords in JSON exports.
- Do not make Agent install mandatory.
- Do not turn Help -> Getting Started into a blocking modal for experienced users.
- Keep destructive operations confirmed.
- Keep English and Simplified Chinese translations complete.
