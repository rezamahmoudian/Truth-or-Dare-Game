// Isolated UI check with fixture profiles; no accounts or real messages created.
const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const path = require("node:path");
const os = require("node:os");

(async () => {
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
    const errors = [];
    page.on("pageerror", error => { errors.push(error.message); console.error(error.message); });
    await page.addInitScript(() => localStorage.setItem("ft.access", "ui-fixture-token"));
    let enabled = false;
    const settings = {fallback_enabled:true,session_min_minutes:10,session_max_minutes:20};
    const personas = [
      ["رها نیک‌منش",24,"شیراز","a2","شوخ و اجتماعی؛ عاشق موسیقی و سؤال‌های بامزه."],
      ["نیلا مهرآیین",27,"رشت","a5","آرام و کتاب‌دوست؛ طرفدار گفتگوهای عمیق."],
      ["تارا رادفر",25,"اصفهان","a8","پرانرژی و رقابت‌دوست؛ اهل معما و بازی."],
    ].map(([name,age,city,avatar,bio], i) => ({id:i+1,username:`ai-${i}`,display_name:name,age,avatar,bio,is_ai:true,ai_profile:{city,interests:"موسیقی و بازی"}}));
    await page.route("**/api/ai/personas/", route => route.fulfill({ json: { available: enabled, personas, settings } }));
    await page.route("**/__ai-ui", route => route.fulfill({ contentType:"text/html", body:`<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script type="module">
      import RefreshRuntime from '/@react-refresh';
      RefreshRuntime.injectIntoGlobalHook(window); window.$RefreshReg$=()=>{}; window.$RefreshSig$=()=>(type)=>type; window.__vite_plugin_react_preamble_installed__=true;
      const {default:React}=await import('/node_modules/.vite/deps/react.js');
      const {default:ReactDOM}=await import('/node_modules/.vite/deps/react-dom_client.js');
      const {AIIntroSheet}=await import('/src/features/play/AIIntroSheet.tsx');
      await import('/src/index.css');
      window.started=0; window.dismissedCount=0;
      window.testRoot=ReactDOM.createRoot(document.getElementById('root'));
      window.testRoot.render(React.createElement(React.StrictMode,null,React.createElement(AIIntroSheet,{onClose:()=>{window.dismissedCount++},onStart:async()=>{window.started++}})));
    </script></body></html>` }));
    await page.goto("http://localhost:5173/__ai-ui");
    await page.getByText("رها نیک‌منش",{exact:true}).waitFor();
    const start = page.getByRole("button",{name:"شروع بازی با AI",exact:true});
    assert.equal(await start.isDisabled(),true);
    assert.equal(await page.locator("article").count(),3);
    await page.getByText("اتصال هنوز توسط مدیر فعال نشده است.").waitFor();
    console.log("PASS profiles and unavailable configuration render clearly");
    enabled=true;
    await page.reload();
    await page.getByText("رها نیک‌منش",{exact:true}).waitFor();
    assert.equal(await start.isEnabled(),true);
    assert.equal(await page.evaluate(()=>window.started),0);
    assert.equal(await page.getByText(/این شخصیت‌ها انسان واقعی نیستند/).count(), 0);
    await start.scrollIntoViewIfNeeded();
    await page.screenshot({path:path.join(os.tmpdir(),"ft-ai-personas.png")});
    await start.click();
    assert.equal(await page.evaluate(()=>window.started),1);
    await page.setViewportSize({width:320,height:740});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth),true);
    assert.deepEqual(errors,[]);
    console.log("PASS explicit start, mobile layout, disclosure and no browser errors");
    const modes = [{ key:"quick", title:"بازی سریع", subtitle:"دونفره", size_min:2, size_max:2, is_featured:true, remaining_today:null, queue_state:"EMPTY" },
      {key:"group", title:"بازی گروهی", subtitle:"گروهی", size_min:3, size_max:5, remaining_today:null, queue_state:"EMPTY"}];
    const submitted = [];
    await page.route("**/api/lobby/", route => route.fulfill({json:{modes,online_count:0,active_people:[],ai_settings:settings}}));
    await page.route("**/api/game-invitations/", route => route.fulfill({json:{incoming:[],outgoing:[],ready:[]}}));
    await page.route("**/api/match/", route => {
      if (route.request().method() === "POST") {
        const data = route.request().postDataJSON(); submitted.push(data);
        return route.fulfill({json:{id:submitted.length,mode:data.mode,state:"QUEUED",widened:false,waited_seconds:0,queue_size:1,
          ai_fallback_at:settings.fallback_enabled && data.mode === "quick" ? new Date(Date.now()+240000).toISOString() : null}});
      }
      return route.fulfill({json:{state:"IDLE"}});
    });
    await page.route("**/__ai-lobby", route => route.fulfill({contentType:"text/html",body:`<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script type="module">
      import RefreshRuntime from '/@react-refresh';
      RefreshRuntime.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(type)=>type;window.__vite_plugin_react_preamble_installed__=true;
      const {default:React}=await import('/node_modules/.vite/deps/react.js');
      const {default:ReactDOM}=await import('/node_modules/.vite/deps/react-dom_client.js');
      const screenSource=await (await fetch('/src/features/play/PlayScreen.tsx')).text();
      const routerPath=screenSource.match(/"([^"]*react-router-dom[^\"]*)"/)[1];
      const {MemoryRouter}=await import(routerPath);
      const {PlayScreen}=await import('/src/features/play/PlayScreen.tsx');
      await import('/src/index.css');
      ReactDOM.createRoot(document.getElementById('root')).render(React.createElement(MemoryRouter,null,React.createElement(PlayScreen)));
    </script></body></html>`}));
    await page.goto("http://localhost:5173/__ai-lobby");
    await page.getByRole("button",{name:/بازی سریع/}).waitFor();
    assert.equal(await page.getByRole("checkbox").count(),0);
    await page.getByRole("button",{name:/بازی سریع/}).click();
    await page.getByRole("button",{name:"انصراف",exact:true}).waitFor();
    assert.equal(submitted.at(-1).ai_consent,false);
    await page.getByRole("button",{name:"انصراف",exact:true}).click();
    await page.getByRole("button",{name:/بازی سریع/}).click();
    await page.getByRole("button",{name:"انصراف",exact:true}).waitFor();
    assert.equal(submitted.at(-1).ai_consent,false);
    await page.getByRole("button",{name:"انصراف",exact:true}).click();
    await page.getByRole("button",{name:/بازی گروهی/}).click();
    await page.getByRole("button",{name:"انصراف",exact:true}).waitFor();
    assert.equal(submitted.at(-1).ai_consent,false);
    settings.fallback_enabled=false;
    await page.reload();
    await page.getByRole("button",{name:/بازی سریع/}).waitFor();
    assert.equal(await page.getByText(/مدت جلسه تصادفی بین/).count(),0);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth),true);
    assert.deepEqual(errors,[]);
    console.log("PASS automatic fallback, no checkbox, group exclusion and mobile layout");
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1});
