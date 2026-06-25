# FileZall M20 Session, Status, and File List Polish

## Goal

Finish the confirmed UI behavior updates:

- Make the bottom-right connection light visibly blink during heartbeat checks.
- Wire the Disconnect button to a real controller disconnect flow and log it.
- Add a Session menu action that opens a new independent connection window.
- Add file-list icons for parent rows, directories, and file extensions.
- Force the compact local directory picker button to show `...`.

## Steps

1. Add failing regression tests for the five requested behaviors.
2. Implement controller and main-window disconnect behavior.
3. Add Session/New Session menu plumbing.
4. Add compact path-button styling and file-list icons.
5. Run targeted desktop/controller tests, then full test suite.
6. Merge, push, rebuild Windows installer and portable ZIP, and smoke-launch the packaged app.
