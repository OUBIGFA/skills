# Language Profile Reference

The executable values live in `config/language_profiles.json`. This file explains how
to choose and override them; it is not a second configuration source.

## Fields

- `target_language`: human-readable name used in reports and fallback notices.
- `counting`: `cjk` counts full-width characters as 1, Latin letters/digits as 0.5,
  and punctuation as 0; `raw` counts every visible character including spaces.
- `final_punctuation`: `none` warns on ordinary sentence-final punctuation; `standard`
  follows the target language's normal subtitle practice.
- `max_cps`: reading-speed review threshold in display-cost units per second.
- `max_width`: one-glance scan-width review threshold in display-cost units.
- `spacing`: whether the checker reports missing CJK/Latin or CJK/digit spacing.
- `ban_exclamation`: whether exclamation marks are reported as a style violation.

## Resolution

Language codes are normalized to lowercase and `_` becomes `-`. An exact profile wins;
otherwise a regional code such as `en-US` uses `en`; an unknown code uses `default`.
The checker reports the requested code, so an unknown-language fallback is visible rather
than silently treated as a supported locale.

## Custom profiles

Pass a project-specific JSON file with `--lang-config`. Keep the same required fields
and use `--lang <code>` to select a profile. A malformed file is an error; the checker
does not silently fall back to built-in settings when an explicitly supplied file cannot
be loaded.

The numerical values are review triggers, not hard subtitle quotas. Human judgement
still decides whether a natural phrase should remain intact or be re-segmented.
