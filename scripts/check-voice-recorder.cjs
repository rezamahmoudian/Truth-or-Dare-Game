// Run against the Vite dev server with Playwright on NODE_PATH.
// The isolated component uses mocked media and HTTP; no real chat is modified.
const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const path = require("node:path");
const os = require("node:os");

(async () => {
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 390, height: 844 }, hasTouch: true });
    const errors = [];
    page.on("pageerror", (error) => { errors.push(error.message); console.error("Browser:", error.message); });
    page.on("console", (message) => { if (message.type() === "error") console.error("Console:", message.text()); });
    await page.addInitScript(() => {
      window.mediaTest = { deferred: false, denied: false, started: 0, stopped: 0, tracksStopped: 0 };
      Object.defineProperty(navigator.mediaDevices, "getUserMedia", { value: async () => {
        if (window.mediaTest.denied) throw new Error("NotAllowedError");
        if (window.mediaTest.deferred) await new Promise((resolve) => { window.mediaTest.resolve = resolve; });
        return { getTracks: () => [{ stop: () => { window.mediaTest.tracksStopped++; } }] };
      } });
      window.MediaRecorder = class {
        static isTypeSupported() { return true; }
        constructor() { this.state = "inactive"; this.mimeType = "audio/webm"; }
        start() { this.state = "recording"; window.mediaTest.started++; }
        stop() {
          if (this.state !== "recording") throw new Error("Double stop");
          this.state = "inactive";
          window.mediaTest.stopped++;
          queueMicrotask(() => {
            this.ondataavailable?.({ data: new Blob(["test audio"], { type: this.mimeType }) });
            this.onstop?.();
          });
        }
      };
    });
    let failNext = false;
    const uploads = [];
    await page.route("**/api/**", async (route) => {
      if (route.request().url().endsWith("/attachments/")) {
        const body = route.request().postDataBuffer().toString();
        const id = /name="client_id"\r\n\r\n([^\r]+)/.exec(body)?.[1];
        uploads.push(id);
        const status = failNext ? 503 : 200;
        failNext = false;
        await route.fulfill({ status, json: status === 503 ? { detail: "ارسال نشد؛ دوباره تلاش کنید." } : {
          id: uploads.length, conversation_id: "voice-test", client_id: id, type: "ATTACHMENT", body: "", sender: { id: 1 }, created_at: new Date().toISOString(), reactions: {},
        } });
      } else await route.fulfill({ json: [] });
    });
    await page.route("**/__voice-test", (route) => route.fulfill({ contentType: "text/html", body: `<!doctype html>
      <html dir="rtl" lang="fa"><head><meta charset="utf-8" /><meta name="viewport" content="width=device-width,initial-scale=1" /></head><body><div id="root"></div>
      <script type="module">
      import RefreshRuntime from '/@react-refresh';
      RefreshRuntime.injectIntoGlobalHook(window);
      window.$RefreshReg$ = () => {}; window.$RefreshSig$ = () => (type) => type;
      window.__vite_plugin_react_preamble_installed__ = true;
      await import('/@vite/client');
      const { default: React } = await import('/node_modules/.vite/deps/react.js');
      const { default: ReactDOM } = await import('/node_modules/.vite/deps/react-dom_client.js');
      const { AttachmentComposer } = await import('/src/features/chat/AttachmentComposer.tsx');
      await import('/src/index.css');
      window.testRoot = ReactDOM.createRoot(document.getElementById('root'));
      window.testRoot.render(React.createElement(React.StrictMode, null, React.createElement('div', {style:{position:'fixed',bottom:0,width:'100%',padding:'12px',boxSizing:'border-box'}},
        React.createElement(AttachmentComposer, {conversationId:'voice-test',hasText:false,onSendText:()=>{}},
          React.createElement('textarea', {placeholder:'پیام…',className:'min-w-0 flex-1 resize-none bg-transparent p-3 outline-none',rows:1})))));
      </script></body></html>` }));
    await page.goto("http://localhost:5173/__voice-test");
    const mic = () => page.getByRole("button", { name: "برای ضبط وویس نگه دارید", exact: true });
    async function hold() {
      const box = await mic().boundingBox();
      assert.ok(box);
      await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
      await page.mouse.down();
      await page.waitForTimeout(550);
      return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
    }
    async function uploadsCount(count) {
      await page.waitForFunction(() => !document.body.textContent.includes("در حال ارسال…"));
      assert.equal(uploads.length, count);
    }
    await mic().waitFor();
    await page.screenshot({ path: path.join(os.tmpdir(), "ft-voice-idle.png") });
    await hold();
    await page.mouse.up();
    await page.waitForTimeout(150);
    await uploadsCount(1);
    console.log("PASS hold + release sends once");

    const p = await hold();
    await page.mouse.move(p.x + 105, p.y);
    await page.getByText("رها کن تا لغو شود").waitFor();
    await page.mouse.up();
    await uploadsCount(1);
    console.log("PASS slide right cancels");

    const lock = await hold();
    await page.mouse.move(lock.x, lock.y - 100);
    await page.mouse.up();
    await page.getByText("ضبط بدون نگه‌داشتن").waitFor();
    await uploadsCount(1);
    await page.screenshot({ path: path.join(os.tmpdir(), "ft-voice-locked.png") });
    await page.getByRole("button", { name: "توقف و گوش‌دادن قبل از ارسال" }).click();
    await page.getByText("پیام صوتی شما").waitFor();
    await uploadsCount(1);
    await page.getByRole("button", { name: "حذف پیوست" }).click();
    console.log("PASS slide up locks; stop keeps preview without sending");

    await page.evaluate(() => { window.mediaTest.deferred = true; });
    const before = await page.evaluate(() => window.mediaTest.started);
    await hold();
    await page.mouse.up();
    await page.evaluate(() => { window.mediaTest.resolve(); window.mediaTest.deferred = false; });
    await page.waitForTimeout(100);
    assert.equal(await page.evaluate(() => window.mediaTest.started), before);
    await uploadsCount(1);
    console.log("PASS releasing before microphone permission prevents late recording");

    failNext = true;
    await hold();
    await page.mouse.up();
    await page.getByRole("button", { name: "ارسال دوباره" }).waitFor();
    await page.getByRole("button", { name: "ارسال دوباره" }).click();
    await page.waitForTimeout(150);
    await uploadsCount(3);
    assert.ok(uploads[1]);
    assert.equal(uploads[1], uploads[2]);
    console.log("PASS failed upload retains draft and client_id on retry");

    await mic().focus();
    await page.keyboard.down("Space");
    await page.waitForTimeout(550);
    await page.keyboard.up("Space");
    await page.waitForTimeout(150);
    await uploadsCount(4);
    console.log("PASS keyboard hold + release sends once");

    await page.evaluate(() => { window.mediaTest.denied = true; });
    await hold();
    await page.mouse.up();
    await page.getByRole("alert").waitFor();
    await uploadsCount(4);
    await page.evaluate(() => { window.mediaTest.denied = false; });
    console.log("PASS denied microphone permission displays error");

    await hold();
    await page.evaluate(() => window.dispatchEvent(new Event("blur")));
    await page.mouse.up();
    await uploadsCount(4);
    console.log("PASS window interruption cancels without sending");

    await mic().click();
    await page.waitForTimeout(100);
    await uploadsCount(4);
    console.log("PASS brief tap does not send an empty voice message");

    const cdp = await page.context().newCDPSession(page);
    await page.setViewportSize({ width: 320, height: 740 });
    const touchBox = await mic().boundingBox();
    const touch = { x: touchBox.x + touchBox.width / 2, y: touchBox.y + touchBox.height / 2 };
    await cdp.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [touch] });
    await page.waitForTimeout(550);
    await page.screenshot({ path: path.join(os.tmpdir(), "ft-voice-recording.png") });
    await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
    await page.waitForTimeout(150);
    await uploadsCount(5);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
    console.log("PASS touch hold + release at 320px; no horizontal overflow");

    const lockedSend = await hold();
    await page.mouse.move(lockedSend.x, lockedSend.y - 100);
    await page.mouse.up();
    await page.getByRole("button", { name: "ارسال وویس", exact: true }).click();
    await page.waitForTimeout(150);
    await uploadsCount(6);
    console.log("PASS locked recording sends only on explicit send");

    await hold();
    await page.evaluate(() => window.testRoot.unmount());
    await page.mouse.up();
    const stats = await page.evaluate(() => window.mediaTest);
    assert.equal(stats.started, stats.stopped);
    assert.ok(stats.tracksStopped >= stats.started);
    assert.equal(uploads.length, 6);
    assert.deepEqual(errors, []);
    console.log("PASS unmount releases microphone; no browser errors");
  } finally { await browser.close(); }
})().catch((error) => { console.error(error); process.exitCode = 1; });
