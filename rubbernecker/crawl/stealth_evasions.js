// SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>
//
// SPDX-License-Identifier: MIT
//
// Best-effort evasion pack for Chrome driven by chromedriver.
//
// Adapted from MIT-licensed sources, chiefly puppeteer-extra-plugin-stealth
// (https://github.com/berstend/puppeteer-extra) and selenium-stealth
// (https://github.com/diprajpatra/selenium-stealth). See ATTRIBUTION.md.
//
// Injected once per session through the Chrome DevTools Protocol
// (Page.addScriptToEvaluateOnNewDocument), so it runs in the main world
// before any page script on every new document.
//
// This is best-effort, not a guarantee: it cannot change TLS, HTTP/2, IP
// reputation, or behavioral fingerprints.

(() => {
  "use strict";

  // navigator.webdriver -------------------------------------------------------
  // --disable-blink-features=AutomationControlled already keeps this false;
  // redefine defensively in case the launch flag is ever dropped.
  try {
    Object.defineProperty(Navigator.prototype, "webdriver", {
      get: () => false,
      configurable: true,
    });
  } catch {}

  // window.chrome ---------------------------------------------------------------
  // Stripped automation contexts (old headless, Chrome for Testing) may lack
  // the chrome object or parts of it. Regular Chrome pages expose app, csi,
  // and loadTimes but NOT runtime (extension-only), so fill in only what is
  // missing and never add runtime.
  const chrome = window.chrome || (window.chrome = {});
  if (!chrome.app) {
    chrome.app = {
      isInstalled: false,
      InstallState: {
        DISABLED: "disabled",
        INSTALLED: "installed",
        NOT_INSTALLED: "not_installed",
      },
      RunningState: {
        CANNOT_RUN: "cannot_run",
        READY_TO_RUN: "ready_to_run",
        RUNNING: "running",
      },
      getDetails: () => null,
      installState: () => "disabled",
    };
  }
  if (!chrome.csi) {
    chrome.csi = () => ({
      startE: Date.now(),
      onloadT: Date.now(),
      pageT: 0,
      tran: 15,
    });
  }
  if (!chrome.loadTimes) {
    chrome.loadTimes = () => ({
      requestTime: Date.now() / 1000,
      startLoadTime: Date.now() / 1000,
      commitLoadTime: Date.now() / 1000,
      finishDocumentLoadTime: Date.now() / 1000,
      finishLoadTime: Date.now() / 1000,
      firstPaintTime: Date.now() / 1000,
      firstPaintAfterLoadTime: 0,
      navigationType: "Other",
      wasFetchedViaSpdy: false,
      wasNpnNegotiated: true,
      npnNegotiatedProtocol: "h2",
      wasAlternateProtocolAvailable: false,
      connectionInfo: "h2",
    });
  }

  // navigator.plugins / navigator.mimeTypes --------------------------------------
  // Stripped contexts report none; regular Chrome always exposes the built-in
  // PDF viewer plugins.
  if (navigator.plugins.length === 0) {
    const MIME_TYPE = "application/pdf";
    const PLUGIN_DATA = [
      ["PDF Viewer", "internal-pdf-viewer"],
      ["Chrome PDF Viewer", "internal-pdf-viewer"],
      ["Chromium PDF Viewer", "internal-pdf-viewer"],
      ["Microsoft Edge PDF Viewer", "internal-pdf-viewer"],
      ["Web built-in PDF Viewer", "internal-pdf-viewer"],
    ];
    const mimeTypes = [];
    const plugins = PLUGIN_DATA.map(([name, filename]) => {
      const mimeType = Object.create(MimeType.prototype, {
        type: { value: MIME_TYPE },
        suffixes: { value: "pdf" },
        description: { value: "Portable Document Format" },
      });
      const plugin = Object.create(Plugin.prototype, {
        name: { value: name },
        description: { value: "Portable Document Format" },
        filename: { value: filename },
        length: { value: 1 },
        item: { value: (index) => (index === 0 ? mimeType : null) },
        namedItem: { value: (type) => (type === MIME_TYPE ? mimeType : null) },
      });
      Object.defineProperty(mimeType, "enabledPlugin", { value: plugin });
      Object.defineProperty(plugin, "0", { value: mimeType });
      mimeTypes.push(mimeType);
      return plugin;
    });
    const pluginArray = Object.create(PluginArray.prototype, {
      length: { value: plugins.length },
      item: { value: (index) => plugins[index] ?? null },
      namedItem: { value: (name) => plugins.find((p) => p.name === name) ?? null },
      refresh: { value: () => undefined },
    });
    plugins.forEach((plugin, index) => {
      Object.defineProperty(pluginArray, String(index), {
        value: plugin,
        enumerable: true,
        configurable: true,
      });
    });
    const mimeTypeArray = Object.create(MimeTypeArray.prototype, {
      length: { value: mimeTypes.length },
      item: { value: (index) => mimeTypes[index] ?? null },
      namedItem: { value: (type) => mimeTypes.find((m) => m.type === type) ?? null },
    });
    mimeTypes.forEach((mimeType, index) => {
      Object.defineProperty(mimeTypeArray, String(index), {
        value: mimeType,
        enumerable: true,
        configurable: true,
      });
    });
    Object.defineProperty(navigator, "plugins", {
      get: () => pluginArray,
      configurable: true,
    });
    Object.defineProperty(navigator, "mimeTypes", {
      get: () => mimeTypeArray,
      configurable: true,
    });
  }

  // navigator.languages -----------------------------------------------------------
  // Match the --lang=en-US launch flag; stripped contexts report []. Regular
  // Chrome with our flag reports ["en-US"], which is already consistent, so
  // only fill in when empty.
  if (!navigator.languages || navigator.languages.length === 0) {
    try {
      Object.defineProperty(navigator, "languages", {
        get: () => ["en-US", "en"],
        configurable: true,
      });
    } catch {}
  }

  // navigator.permissions.query -----------------------------------------------------
  // The classic tell: a 'notifications' query returning a state inconsistent
  // with Notification.permission. Proxy the native method so function identity
  // and toString() keep looking native.
  if (navigator.permissions && window.Notification) {
    const originalQuery = navigator.permissions.query;
    navigator.permissions.query = new Proxy(originalQuery, {
      apply(target, thisArg, args) {
        const descriptor = args[0];
        if (descriptor && descriptor.name === "notifications") {
          return Promise.resolve({
            name: "notifications",
            onchange: null,
            state: Notification.permission,
          });
        }
        return Reflect.apply(target, thisArg, args);
      },
    });
  }

  // WebGL vendor/renderer --------------------------------------------------------------
  // Automation contexts often report SwiftShader or an empty GPU string; both
  // are strong bot signals. Report a common desktop GPU instead. The values
  // are substituted by StealthDriver at session start.
  const webglVendor = "__WEBGL_VENDOR__";
  const webglRenderer = "__WEBGL_RENDERER__";
  for (const api of [
    window.WebGLRenderingContext,
    window.WebGL2RenderingContext,
  ]) {
    if (!api) continue;
    const originalGetParameter = api.prototype.getParameter;
    api.prototype.getParameter = new Proxy(originalGetParameter, {
      apply(target, thisArg, args) {
        if (args[0] === 0x9245) return webglVendor; // UNMASKED_VENDOR_WEBGL
        if (args[0] === 0x9246) return webglRenderer; // UNMASKED_RENDERER_WEBGL
        return Reflect.apply(target, thisArg, args);
      },
    });
  }
})();
