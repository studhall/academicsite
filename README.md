# Academic Site

## Run Quarto Tasks in VS Code

This repo includes VS Code tasks for the existing Quarto CLI workflow.

1. Open the Command Palette (`Ctrl+Shift+P`) and run `Tasks: Run Task`.
2. Choose one of:
   - `Quarto: Preview Site` to run `quarto preview`
   - `Quarto: Render Site` to run `quarto render`
   - `Quarto: Publish gh-pages` to run `quarto render` and then `quarto publish gh-pages`

All tasks run from the repository root (`${workspaceFolder}`), which matches the current publishing setup.
