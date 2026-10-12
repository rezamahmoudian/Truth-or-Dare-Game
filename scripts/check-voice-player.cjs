// Isolated UI check: real generated audio, mocked private-file HTTP responses.
// Requires the Vite dev server and Playwright available on NODE_PATH.
const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const path = require("node:path");
const os = require("node:os");

function wave() {
  const count = 8000 * 6;
  const data = Buffer.alloc(44 + count * 2);
  data.write("RIFF", 0); data.writeUInt32LE(data.length - 8, 4); data.write("WAVEfmt ", 8);
  data.writeUInt32LE(16, 16); data.writeUInt16LE(1, 20); data.writeUInt16LE(1, 22);
  data.writeUInt32LE(8000, 24); data.writeUInt32LE(16000, 28); data.writeUInt16LE(2, 32); data.writeUInt16LE(16, 34);
  data.write("data", 36); data.writeUInt32LE(count * 2, 40);
  for (let i = 0; i < count; i++) data.writeInt16LE(Math.round(Math.sin(i * Math.PI * 2 * 220 / 8000) * (0.3 + 0.6 * Math.abs(Math.sin(i / 3700))) * 14000), 44 + i * 2);
  return data;
}

(async () => {
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
    const errors = [];
    page.on("pageerror", (error) => { errors.push(error.message); console.error(error.message); });
    let requests = 0;
    let failNext = false;
    await page.route("**/api/audio/**", async (route) => {
      requests++;
      if (failNext) { failNext = false; await route.fulfill({ status: 503, json: { detail: "دریافت نشد" } }); }
      else await route.fulfill({ contentType: "audio/wav", body: wave() });
    });
    await page.route("**/__player-test", (route) => route.fulfill({ contentType: "text/html", body: `<!doctype html>
      <html dir="rtl" lang="fa"><head><meta charset="utf-8" /><meta name="viewport" content="width=device-width,initial-scale=1" /></head><body><div id="root"></div>
      <script type="module">
      import RefreshRuntime from '/@react-refresh';
      RefreshRuntime.injectIntoGlobalHook(window);
      window.$RefreshReg$ = () => {}; window.$RefreshSig$ = () => (type) => type;
      window.__vite_plugin_react_preamble_installed__ = true;
      const {default: React} = await import('/node_modules/.vite/deps/react.js');
      const {default: ReactDOM} = await import('/node_modules/.vite/deps/react-dom_client.js');
      const {AttachmentView} = await import('/src/features/chat/Attachments.tsx');
      await import('/src/index.css');
      window.testRoot = ReactDOM.createRoot(document.getElementById('root'));
      window.testRoot.render(React.createElement(React.StrictMode, null,
        React.createElement('div', {className:'flex flex-col gap-5 p-4'},
          ...['one','two','three'].map((id) => React.createElement('div', {key:id,id,className:'surface-raised max-w-[78%] rounded-card p-3'},
            React.createElement(AttachmentView, {attachment:{kind:'voice',name:'voice-test.wav',size:96044,mime:'audio/wav',url:'/audio/'+id}}))))));
      </script></body></html>` }));
    await page.goto("http://localhost:5173/__player-test");
    const first = page.locator("#one");
    const second = page.locator("#two");
    const third = page.locator("#three");
    await first.getByRole("button", { name: "پخش وویس", exact: true }).waitFor();
    assert.equal(requests, 0);
    assert.equal(await page.locator("audio[controls]").count(), 0);
    await first.getByRole("button", { name: "پخش وویس", exact: true }).click();
    await page.waitForFunction(() => document.querySelector("#one audio").currentTime > 0.2);
    assert.equal(requests, 1);
    await first.getByRole("button", { name: "توقف پخش وویس" }).click();
    const paused = await first.locator("audio").evaluate((a) => a.currentTime);
    await page.waitForTimeout(180);
    assert.equal(await first.locator("audio").evaluate((a) => a.currentTime), paused);
    console.log("PASS lazy authenticated load; real audio play and pause; no native controls");

    await page.waitForFunction(() => new Set([...document.querySelectorAll('#one svg g:first-of-type rect')].map(r => r.getAttribute('height'))).size > 3);
    const slider = first.getByRole("slider", { name: "موقعیت پخش وویس" });
    await slider.fill("3");
    assert.ok(Math.abs(await first.locator("audio").evaluate(a => a.currentTime) - 3) < 0.2);
    await slider.focus();
    await page.keyboard.press("ArrowRight");
    assert.ok(await first.locator("audio").evaluate(a => a.currentTime) > 3);
    const progress = await first.locator("clipPath rect").getAttribute("width");
    assert.ok(Number(progress) > 90 && Number(progress) < 120);
    await first.getByRole("button", { name: "گزینه‌های وویس", exact: true }).click();
    await first.getByRole("button", { name: "سرعت پخش 1 برابر؛ تغییر سرعت", exact: true }).click();
    assert.equal(await first.locator("audio").evaluate(a => a.playbackRate), 1.5);
    console.log("PASS decoded waveform, progress fill, seek, keyboard seek, playback speed");

    await first.getByRole("button", { name: "پخش وویس", exact: true }).click();
    await second.getByRole("button", { name: "پخش وویس", exact: true }).click();
    await page.waitForFunction(() => !document.querySelector('#two audio').paused);
    assert.equal(await first.locator("audio").evaluate(a => a.paused), true);
    await second.getByRole("slider").fill("5.8");
    await second.getByRole("button", { name: "پخش وویس", exact: true }).waitFor();
    await second.getByRole("button", { name: "پخش وویس", exact: true }).click();
    await page.waitForFunction(() => { const a = document.querySelector('#two audio'); return !a.paused && a.currentTime < 2; });
    await second.getByRole("button", { name: "توقف پخش وویس" }).click();
    console.log("PASS starting another voice pauses the first; ended audio replays");

    failNext = true;
    await third.getByRole("button", { name: "پخش وویس", exact: true }).click();
    await third.getByRole("alert").waitFor();
    await third.getByRole("button", { name: "پخش وویس", exact: true }).click();
    await page.waitForFunction(() => !document.querySelector('#three audio').paused);
    await third.getByRole("button", { name: "توقف پخش وویس" }).click();
    assert.equal(await third.getByRole("alert").count(), 0);
    console.log("PASS download failure can retry and play");

    await page.setViewportSize({ width: 320, height: 740 });
    await page.screenshot({ path: path.join(os.tmpdir(), 'ft-voice-player.png') });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    assert.equal(await first.getByRole("link", { name: "ذخیرهٔ فایل صوتی" }).count(), 1);
    await first.getByRole("button", { name: "پخش وویس", exact: true }).click();
    await page.evaluate(() => { window.lastAudio = document.querySelector('#one audio'); window.testRoot.unmount(); });
    assert.equal(await page.evaluate(() => window.lastAudio.paused), true);
    assert.deepEqual(errors, []);
    console.log("PASS mobile width, download control, cleanup; no browser errors");

    // MediaRecorder WebM often has no finite native duration. Exercise the
    // actual browser encoder and decoder, without requesting a microphone.
    await page.evaluate(async () => {
      const context = new AudioContext();
      await context.resume();
      const output = context.createMediaStreamDestination();
      const tone = context.createOscillator();
      tone.connect(output); tone.start();
      const recorder = new MediaRecorder(output.stream, { mimeType: "audio/webm;codecs=opus" });
      const chunks = [];
      recorder.ondataavailable = e => chunks.push(e.data);
      const done = new Promise(resolve => { recorder.onstop = resolve; });
      recorder.start();
      await new Promise(resolve => setTimeout(resolve, 900));
      recorder.stop(); await done;
      tone.stop(); output.stream.getTracks().forEach(track => track.stop()); await context.close();
      const src = URL.createObjectURL(new Blob(chunks, { type: recorder.mimeType }));
      const {default: React} = await import('/node_modules/.vite/deps/react.js');
      const {default: ReactDOM} = await import('/node_modules/.vite/deps/react-dom_client.js');
      const {VoicePlayer} = await import('/src/features/chat/VoicePlayer.tsx');
      window.testRoot = ReactDOM.createRoot(document.getElementById('root'));
      window.testRoot.render(React.createElement(VoicePlayer, { src, caption: 'پیش‌نمایش وویس' }));
    });
    await page.waitForFunction(() => Number(document.querySelector('input[type=range]')?.max) > 0.5 && !document.querySelector('input[type=range]').disabled);
    await page.getByRole('button', {name:'پخش وویس',exact:true}).click();
    await page.waitForFunction(() => document.querySelector('audio').currentTime > 0.1);
    await page.getByRole('button', {name:'توقف پخش وویس'}).click();
    await page.getByRole('slider').fill('0.5');
    assert.ok(Math.abs(await page.locator('audio').evaluate(a => a.currentTime) - 0.5) < 0.1);
    assert.deepEqual(errors, []);
    console.log('PASS actual MediaRecorder WebM preview, decoded duration and seek');
  } finally { await browser.close(); }
})().catch((error) => { console.error(error); process.exitCode = 1; });
