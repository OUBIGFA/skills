---
name: chrome
description: Use when the user mentions @chrome, the Chrome plugin, Catsxp, their own browser extension, existing browser tabs, logged-in browser sessions, or browser tasks that need the user's real browser state.
version: 1.0.0
---

# Chrome / Catsxp Browser

Use this skill whenever the user mentions `@chrome` or asks to use their own browser, browser extension, logged-in sessions, existing tabs, or Catsxp.

In this Windows environment, the user's Chromium browser is:

```text
C:\Program Files\CatsxpSoftware\Catsxp-Browser\Application\catsxp.exe
```

The Codex Chrome extension backend may still be named `Chrome` even when the actual browser is Catsxp.

## Required behavior

- Do not conclude that Chrome is unavailable just because there is no separate visible `chrome` tool in the current tool list.
- Do not use the in-app browser (`iab`) for `@chrome` requests unless the extension backend is genuinely unavailable after retry.
- Use the Node REPL `js` tool and the bundled browser-client module to connect to the extension-backed browser.
- Select the extension backend by listing browsers, finding the item whose `type` is `extension`, then calling `await agent.browsers.get(extensionBrowser.id)`.
- Confirm the connection with `await browser.user.openTabs()`. Any successful tab list means the Chrome/Catsxp backend is usable.
- If the extension backend is not found and Catsxp is not running, start Catsxp from the path above, wait briefly, then retry setup once.

## Bootstrap

Use the absolute Chrome plugin path first. This is the path that has been verified on this machine:

```js
const { setupBrowserRuntime } = await import("file:///C:/Users/BIGFA/.codex/plugins/cache/openai-bundled/chrome/26.519.81530/scripts/browser-client.mjs");
await setupBrowserRuntime({ globals: globalThis });
const browsers = await agent.browsers.list();
const extensionBrowser = browsers.find(b => b.type === "extension");
if (!extensionBrowser) throw new Error("Chrome/Catsxp extension backend is unavailable");
globalThis.browser = await agent.browsers.get(extensionBrowser.id);
await browser.nameSession("🔎 Chrome task");
const openTabs = await browser.user.openTabs();
```

If that import path is missing, use the Browser plugin path as fallback:

```js
const { setupBrowserRuntime } = await import("file:///C:/Users/BIGFA/.codex/plugins/cache/openai-bundled/browser/26.519.81530/scripts/browser-client.mjs");
await setupBrowserRuntime({ globals: globalThis });
const browsers = await agent.browsers.list();
const extensionBrowser = browsers.find(b => b.type === "extension");
if (!extensionBrowser) throw new Error("Chrome/Catsxp extension backend is unavailable");
globalThis.browser = await agent.browsers.get(extensionBrowser.id);
await browser.nameSession("🔎 Chrome task");
const openTabs = await browser.user.openTabs();
```

## Starting Catsxp

If setup does not discover the extension backend, first check whether Catsxp is running. If not, start it:

```powershell
Start-Process -FilePath 'C:\Program Files\CatsxpSoftware\Catsxp-Browser\Application\catsxp.exe' -ArgumentList 'about:blank' -WindowStyle Hidden
```

Then wait 2-3 seconds and retry the bootstrap once.

## Common task patterns

Claim an existing user tab by listing tabs first:

```js
const tabs = await browser.user.openTabs();
const target = tabs.find(t => t.url.includes("x.com/"));
globalThis.tab = target ? await browser.user.claimTab(target) : await browser.tabs.new();
```

Open a new page:

```js
if (typeof tab === "undefined") globalThis.tab = await browser.tabs.new();
await tab.goto("https://example.com/");
await tab.playwright.waitForLoadState("domcontentloaded");
```

Read visible page text:

```js
const title = await tab.title();
const url = await tab.url();
const text = await tab.playwright.locator("body").innerText({ timeoutMs: 10000 });
```

## Known local diagnosis

This machine has already verified:

- Catsxp default profile contains the Codex extension.
- The extension is enabled.
- The native host manifest is correct.
- The extension backend can list Catsxp tabs and control pages when Catsxp is running.
