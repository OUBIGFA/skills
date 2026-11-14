# Probe Fingerprint Purity & FoFa Login Persistent Profile Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enhance probe client HTTP/TLS fingerprint purity to eliminate anti-bot anomalies on API endpoints, and upgrade FoFa reconnaissance crawler login to support persistent browser profiles (User Data Dir) for resilient Cloudflare Turnstile handling.

**Architecture:** 
1. In `scripts/core/tls_fingerprint.py`, replace static document-level headers with context-aware client hints (differentiating `navigate` vs `fetch/cors` modes), ensuring REST API calls like OpenAI Sentinel and Reddit JSON do not leak document navigation markers while preserving `curl_cffi` Chrome 131 BoringSSL JA4 fingerprints.
2. In `scripts/core/fofa_login.py`, transition from ephemeral disposable contexts to Playwright's `launch_persistent_context`, defaulting to a dedicated project profile directory with optional `--user-data-dir` override, combined with stealth anti-detection and iframe-aware Turnstile interaction.

**Tech Stack:** Python 3.9+, `curl_cffi`, Playwright, BoringSSL / Chrome 131 impersonation, standard library `urllib` / `ssl` fallback, unittest.

**Spec:** Brainstorming recommendations aligned with user preferences for persistent browser configuration reuse.

## Global Constraints

- Zero regression on existing 5-station WAF shield scoring (`OpenAI Sentinel`, `Google/YouTube`, `Reddit Fastly`, `TikTok`, `Cloudflare Strict`).
- The probe test pipeline (`probe_services.py`) must remain completely separate from spatial reconnaissance login (`fofa_login.py`); no persistent browser dependencies shall be introduced into node quality evaluation.
- Local loopback and dynamic port isolation rules must be preserved.

## Review Focus

1. `request_streaming(..., mode="fetch")` must not send `sec-fetch-mode: navigate` or `sec-fetch-dest: document` to JSON API endpoints.
2. `fofa_login.py` must support custom `--user-data-dir` and fall back gracefully if directory does not exist yet.
3. Fallback `urllib` mode must match the requested `mode` (`navigate` vs `fetch`) without breaking existing proxy or response streaming mechanisms.
4. Turnstile detection must look into Cloudflare challenge iframes rather than solely relying on outer container bounding boxes.
5. All unit tests in `tests/` must pass cleanly without network flakiness.

---

### Task 1: Context-Aware Client Hints & Fingerprint Purity in Probe Engine

**Files:**
- Modify: `scripts/core/tls_fingerprint.py`
- Modify: `scripts/core/waf_shield_probe.py`
- Modify: `tests/test_tls_fingerprint.py`
- Modify: `tests/test_waf_shield_probe.py`

- [x] **Step 1.1: Write failing test for context-aware headers**
  - Add tests in `tests/test_tls_fingerprint.py` asserting that `request_streaming` with `mode="fetch"` sends `sec-fetch-mode: cors`, `sec-fetch-dest: empty`, `sec-fetch-site: same-origin`, and omits document-only headers like `upgrade-insecure-requests`.
  - Add tests asserting that `mode="navigate"` retains document navigation hints.

- [x] **Step 1.2: Implement `build_chrome_headers` and update `request_streaming`**
  - In `scripts/core/tls_fingerprint.py`, define `build_chrome_headers(mode: str = "navigate", headers: Optional[Dict[str, str]] = None) -> Dict[str, str]`.
  - Support `mode="navigate"` and `mode="fetch"`.
  - Update `request_streaming` signature to accept `mode: str = "navigate"`.
  - Ensure `headers` passed in override default hints cleanly without duplicate or inconsistent casing.

- [x] **Step 1.3: Update WAF probe endpoints in `scripts/core/waf_shield_probe.py`**
  - Update `probe_openai_sentinel` to invoke `request_streaming(..., mode="fetch")`.
  - Update `probe_reddit_fastly` to invoke `request_streaming(..., mode="fetch")`.
  - Update `probe_cf_strict_trace` trace endpoint to `mode="fetch"`, keeping website check as `mode="navigate"`.

- [x] **Step 1.4: Run tests and verify**
  - Run `python -m unittest tests/test_tls_fingerprint.py tests/test_waf_shield_probe.py` and confirm all tests pass.

---

### Task 2: Persistent Browser Profile & Enhanced Turnstile in `fofa_login.py`

**Files:**
- Modify: `scripts/core/fofa_login.py`
- Create: `tests/test_fofa_login_profile.py`

- [x] **Step 2.1: Write test for profile resolution and CLI parsing**
  - In `tests/test_fofa_login_profile.py`, test default profile path resolution (`data/fofa_profile`), custom `--user-data-dir` argument parsing, and credential loading.

- [x] **Step 2.2: Upgrade `fofa_login.py` to `launch_persistent_context`**
  - Add `user_data_dir: Optional[str] = None` to `login_fofa_and_extract_token` and CLI argument `--user-data-dir`.
  - Switch from `p.chromium.launch() + browser.new_context()` to `p.chromium.launch_persistent_context(user_data_dir=...)`.
  - Add enhanced anti-detection init scripts (`navigator.webdriver` removal, `window.chrome` mocking, notification permissions mock).

- [x] **Step 2.3: Upgrade Cloudflare Turnstile handling**
  - Search both `frame_locator('iframe[src*="challenges.cloudflare.com"]')` and outer `div.cf-turnstile`.
  - Add randomized bezier jitter during mouse movement to simulate human interaction.
  - Automatically detect when `cf-turnstile-response` length > 20 and trigger form submit if credentials are provided.

- [x] **Step 2.4: Run unit tests**
  - Run `python -m unittest tests/test_fofa_login_profile.py` and verify profile handling.

---

### Task 3: Comprehensive Regression Testing & Verification

**Files:**
- Verify: Full test suite in `tests/`
- Verify: CLI execution test of `scripts/core/fofa_login.py --help`

- [x] **Step 3.1: Execute all test suites**
  - Run `python -m unittest discover tests` and ensure zero failures.

- [x] **Step 3.2: Verify CLI help and documentation alignment**
  - Test `python scripts/core/fofa_login.py --help` to confirm options and descriptions are clear.
