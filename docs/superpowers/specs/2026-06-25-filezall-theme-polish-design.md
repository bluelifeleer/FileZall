# FileZall Theme Polish Design

## Approved Direction

Use a professional workbench style: a darker, calmer application frame with a compact dual-pane file-transfer layout. Keep the app operational and dense rather than decorative. The visual upgrade should make FileZall feel closer to a mature SFTP/operations tool while preserving the existing workflows.

## Requirements

- File rows must show one coordinated full-row active state on mouse hover, not separate per-cell hover feedback.
- Add a Theme menu that lets the user choose System, Light, or Dark.
- Default to System so the app can follow the platform preference when available.
- Keep the current red, yellow, and green connection status light behavior.
- Keep existing Upload, Download, queue, logs, monitor, and context-menu behavior unchanged.

## Architecture

- Add `src/filezall_desktop/theme.py` as the single place for theme names and Qt stylesheet generation.
- `MainWindow` owns the active theme menu and applies the stylesheet to the whole window.
- `HoverRowTableWidget` remains responsible for row-hover state; its delegate will paint one continuous row background across the viewport, including unused width after the last column.

## Testing

- Desktop tests should assert the Theme menu exists with System, Light, and Dark actions.
- Tests should assert selecting Dark and Light changes the window stylesheet.
- Tests should assert the file table exposes full-row hover colors and uses the hover-row table path.
