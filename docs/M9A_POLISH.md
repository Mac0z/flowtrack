# M9A interaction, accessibility, and performance notes

M9A is a targeted polish pass; it does not change FlowTrack's domain or persistence
semantics.

## Interaction and accessibility

- Qt standard keys continue to provide platform-aware New and Find shortcuts; the
  command palette remains available through the portable Command/Control+K sequence.
- Keyboard focus is now visible across text editors, selectors, date/progress inputs,
  lists, and tables using the existing semantic focus token.
- Icon-only calendar navigation and inspector controls, plus Gantt zoom controls, have
  explicit accessible names and useful tooltips.
- Calendar and Gantt date confirmations default to Cancel and use explicit action text.
  Dependency removal also names the relationship and defaults to Cancel.
- In read-only sessions, task/project creation and editing, completion, board movement,
  calendar dragging, Gantt persistence, dependency editing, and owner/tag management
  are unavailable while navigation and inspection remain usable.

## Lightweight performance review

Query surfaces already use eager loading and bounded list queries rather than per-row
fetches. The audit found one structural scale issue: hierarchy ordering used recursive
tree traversal and could fail on a valid hierarchy near Python's recursion limit. It
now uses a linear explicit-stack traversal, covered at a deterministic depth of 1,500.
No timing threshold was added because shared CI wall-clock measurements are noisy.

## Acceptance gaps

No genuine non-packaging functional acceptance gap was identified during M9A. Clean
machine, high-DPI visual, and both-platform validation remain M9C work; installers and
packaged-runtime acceptance remain M9B work. Therefore `docs/M9_ACCEPTANCE_GAPS.md` was
not required.
