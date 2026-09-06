# Code style

Write for the person who will read and maintain the code. Use clear names,
ordinary control flow, and enough line breaks to make each step easy to follow.
Avoid semicolon chains, compressed functions, deeply nested expressions, and
large inline objects or JSX trees. Apply the same standard to tests, scripts,
and evaluation helpers.

Use focused patches for routine edits. Scripted transformations are useful for
mechanical work, but their output still needs review and formatting.

## Format and check

From the repository root, format Python application code, tests, and tools:

```bash
uv run --project pipelines ruff format api pipelines
```

Check without writing:

```bash
uv run --project pipelines ruff format --check --output-format concise api pipelines
```

From `frontend/`, run `npm run format` to format source and configuration, or
`npm run format:check` to check without writing. Ruff and Prettier versions are
locked in the dependency files. CI checks both; `.editorconfig` supplies basic
editor defaults. ESLint requires braces around frontend control-flow bodies,
including short early returns.

Formatters do not replace judgment. Break up complicated expressions, name
intermediate results when that clarifies their meaning, and write SQL and prompt
definitions in readable blocks. Preserve behavior and exact prompt values during
formatting-only changes.

Archived evaluation requests, responses, sources, and hash-bound experiment
files retain their original bytes for reproducibility. New maintained helpers
follow these formatting rules from the start.
