# FileZall M16 - Logs, Row Hover, Context Transfers

## Goal

Fix three desktop interaction gaps:

- Connection attempts should write visible process logs.
- File table hover feedback should read as a full active row.
- Local context menus should expose Upload, and remote context menus should expose Download, wired to the existing transfer handlers.

## Implementation

1. Add regression tests for connection logging, heartbeat failure logging, panel transfer action labels, and row-hover support.
2. Reuse each `FilePanel` action label for the context transfer action.
3. Add connection attempt/failure logs in `MainWindow`, and log heartbeat disconnects once until recovery.
4. Replace plain file tables with a hover-row table/delegate so every cell in the hovered row receives the same active background.
5. Run desktop tests, package smoke, commit, merge, push, and rebuild Windows artifacts.

## Verification

- `python -m pytest tests/desktop/test_main_window.py -v`
- `python -m pytest tests/desktop/test_main_window.py tests/desktop/test_controller.py -v`
- Windows package build and packaged app smoke launch.
