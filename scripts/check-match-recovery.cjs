// Isolated browser fixture: no live users, queue entries or chat messages.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');

(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
    const errors = [];
    page.on('pageerror', e => { errors.push(e.message); console.error('Browser:', e.message); });
    page.on('console', m => { if (m.type() === 'error') console.error('Console:', m.text()); });
    page.on('requestfailed', r => console.error('Failed request:', new URL(r.url()).pathname, r.failure()?.errorText));
    const me = { id: 1, username: 'fixture', display_name: 'تست', avatar: 'a1', age: 25, gender: 'M', is_guest: true, is_onboarded: true, streak_days: 0 };
    const mode = { key: 'quick', title: 'شروع سریع', subtitle: 'هم‌بازی اتفاقی', size_min: 2, size_max: 2, remaining_today: null, queue_state: 'FAST', is_featured: true, is_ai: false };
    const ticket = { id: 41, mode: 'quick', state: 'QUEUED', widened: false, waited_seconds: 0, queue_size: 1, conversation_id: null, ai_fallback_at: null };
    let phase = 'IDLE';
    let holdStatus = false;
    let heldRoute;
    const statusQueries = [];
    await page.addInitScript(() => localStorage.setItem('ft.access', 'fixture-token'));
    await page.route('**/api/**', async route => {
      const url = new URL(route.request().url());
      let data = [];
      if (url.pathname === '/api/lobby/') data = { modes: [mode], active_people: [], online_count: 0 };
      if (url.pathname === '/api/match/') {
        if (route.request().method() === 'POST') { phase = 'QUEUED'; data = ticket; }
        else {
          statusQueries.push(url.searchParams.get('ticket_id'));
          if (holdStatus && !url.searchParams.has('ticket_id')) { heldRoute = route; return; }
          data = phase === 'QUEUED' ? ticket : phase === 'MATCHED' && url.searchParams.get('ticket_id') === '41' ? { ...ticket, state: 'MATCHED', conversation_id: 'recovered-room' } : { state: 'IDLE' };
        }
      }
      await route.fulfill({ json: data });
    });
    await page.route('**/__match-recovery', route => route.fulfill({ contentType: 'text/html', body: `<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script type="module">
      import RefreshRuntime from '/@react-refresh';RefreshRuntime.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(type)=>type;window.__vite_plugin_react_preamble_installed__=true;
      const {default:React}=await import('/node_modules/.vite/deps/react.js');const {default:ReactDOM}=await import('/node_modules/.vite/deps/react-dom_client.js');
      const source=await(await fetch('/src/features/play/PlayScreen.tsx')).text();const {MemoryRouter,Routes,Route}=await import(source.match(/"([^"]*react-router-dom[^\"]*)"/)[1]);
      const {useSession}=await import('/src/store/session.ts');useSession.setState({user:${JSON.stringify(me)},status:'ready'});
      const {useMatch}=await import(source.match(new RegExp('from "([^"]*store/match[^"]*)"'))[1]);window.fixtureMatch=useMatch;
      const {PlayScreen}=await import('/src/features/play/PlayScreen.tsx');await import('/src/index.css');
      const el=React.createElement;ReactDOM.createRoot(document.getElementById('root')).render(el(MemoryRouter,{initialEntries:['/']},el(Routes,null,el(Route,{path:'/',element:el(PlayScreen)}),el(Route,{path:'/c/:id',element:el('h1',null,'Recovered room')}))));
    </script></body></html>` }));
    const visit = () => page.goto('http://localhost:5173/__match-recovery');
    await visit();
    await page.waitForFunction(() => window.fixtureMatch?.getState().loaded);
    await page.evaluate(() => window.fixtureMatch.getState().enqueue('quick'));
    assert.equal(await page.evaluate(() => sessionStorage.getItem('ft.pending-search')), '41');
    phase = 'MATCHED'; // Deliberately do not deliver any WebSocket event.
    await page.getByText('Recovered room', { exact: true }).waitFor({ timeout: 12000 });
    assert.equal(await page.evaluate(() => sessionStorage.getItem('ft.pending-search')), null);
    assert.ok(statusQueries.includes('41'));
    console.log('PASS missed WebSocket match recovers via polling the exact search');

    await visit();
    await page.waitForFunction(() => window.fixtureMatch?.getState().loaded);
    assert.equal(await page.getByText('Recovered room', { exact: true }).count(), 0);
    assert.equal(await page.evaluate(() => window.fixtureMatch.getState().ticket), null);
    console.log('PASS returning home does not reopen an old match');

    phase = 'QUEUED';
    await page.evaluate(() => window.fixtureMatch.getState().enqueue('quick'));
    phase = 'MATCHED';
    await page.reload();
    await page.getByText('Recovered room', { exact: true }).waitFor();
    assert.equal(await page.evaluate(() => sessionStorage.getItem('ft.pending-search')), null);
    console.log('PASS pending search survives refresh and recovers a completed match');

    phase = 'IDLE';
    holdStatus = true;
    await visit();
    await page.waitForFunction(() => window.fixtureMatch?.getState().loaded);
    await page.evaluate(() => window.fixtureMatch.getState().enqueue('quick'));
    assert.ok(heldRoute);
    holdStatus = false;
    await heldRoute.fulfill({ json: { state: 'IDLE' } });
    // An explicit resume also ensures the old response has finished processing.
    await page.evaluate(() => window.fixtureMatch.getState().resume());
    assert.equal(await page.evaluate(() => window.fixtureMatch.getState().ticket?.id), 41);
    console.log('PASS late initial status response cannot clear a newly queued search');
    assert.deepEqual(errors, []);
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
