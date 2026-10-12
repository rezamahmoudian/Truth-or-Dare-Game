// Browser auth regression checks. All API requests are mocked; no live accounts are created.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const path = require('node:path');
const os = require('node:os');
(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const me = { id: 8001, username: 'returning', display_name: 'رضا', avatar: 'a3', age: 27, gender: 'M', birth_date: '1998-01-01', bio: '', is_guest: false, is_onboarded: true, can_change_gender: true, streak_days: 0 };
  const errors = [];
  async function setup(tokens = {}, scenario = '') {
    const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
    await context.addInitScript(values => { for (const [key, value] of Object.entries(values)) localStorage.setItem(key, value); }, tokens);
    const page = await context.newPage();
    page.on('pageerror', e => errors.push(e.message));
    const calls = [];
    let user = { ...me };
    await page.route('**/api/**', async route => {
      const request = route.request();
      const url = new URL(request.url());
      const body = request.postDataJSON();
      calls.push({ path: url.pathname, method: request.method(), body });
      let json = {}, status = 200;
      if (url.pathname === '/api/auth/login/') {
        if (body.password === 'wrong') { status = 401; json = { detail: 'نام کاربری یا رمز عبور درست نیست.' }; }
        else json = { access: 'login-access', refresh: 'login-refresh', user };
      } else if (url.pathname === '/api/auth/register/') {
        user = { ...me, username: body.username, display_name: '', avatar: '', gender: '', birth_date: null, is_onboarded: false };
        status = 201; json = { access: 'register-access', refresh: 'register-refresh', user };
      } else if (url.pathname === '/api/auth/refresh/') {
        if (scenario === 'expired') { status = 401; json = {detail:'expired'}; }
        else if (scenario === 'refresh-offline') { status = 503; json = {detail:'temporary outage'}; }
        else json = {access:'renewed',refresh:'rotated'};
      } else if (url.pathname === '/api/users/me/') {
        if (request.method() === 'PATCH') {
          user = {...user,...body}; user.is_onboarded = !!(user.display_name && user.gender && user.birth_date); json = user;
        } else if (scenario === 'offline') { status = 503; json = {detail:'temporary outage'}; }
        else if (scenario === 'expired' || scenario === 'refresh-offline' || (!request.headers().authorization?.includes('renewed') && scenario === 'refresh')) { status = 401; json = {detail:'expired'}; }
        else json = user;
      } else if (url.pathname === '/api/lobby/') json = {modes:[],active_people:[],online_count:0};
      else if (url.pathname === '/api/match/') json = {state:'IDLE'};
      else if (url.pathname === '/api/friends/') json = {friends:[],incoming:[],outgoing:[]};
      else if (url.pathname === '/api/game-invitations/') json = {incoming:[],outgoing:[],ready:[]};
      else if (url.pathname === '/api/conversations/') json = [];
      else if (url.pathname === '/api/auth/guest/') throw new Error('Must not silently create a guest');
      await route.fulfill({status,json});
    });
    await page.goto('http://localhost:5173/');
    return {context,page,calls};
  }
  try {
    {
      const {page,context,calls} = await setup();
      await page.getByRole('button',{name:'ورود به حساب',exact:true}).waitFor();
      assert.equal(calls.length,0,'first visit must not create an account or fetch private data');
      for(const width of [320,390,768]) {
        await page.setViewportSize({width,height:844});
        assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth),true);
      }
      for (const mode of ['ورود', 'ثبت‌نام']) {
        await page.getByRole('button', { name: mode, exact: true }).click();
        for (const height of [568, 420, 320]) {
          await page.setViewportSize({ width: 320, height });
          const submit = page.getByRole('button', { name: mode === 'ورود' ? 'ورود به حساب' : 'ثبت‌نام و ادامه', exact: true });
          await submit.scrollIntoViewIfNeeded();
          const bounds = await submit.boundingBox();
          assert.ok(bounds.y >= 0 && bounds.y + bounds.height <= height, 'submit remains reachable in a short viewport');
          const layout = await page.locator('.auth-screen').evaluate(el => {
            el.scrollTop = el.scrollHeight;
            return { height: el.getBoundingClientRect().height, scroll: el.scrollTop, padding: parseFloat(getComputedStyle(el).paddingBottom), footerBottom: el.querySelector('.auth-age-note').getBoundingClientRect().bottom };
          });
          assert.ok(layout.height <= height && layout.scroll > 0, 'form scrolls inside the viewport instead of being clipped by root');
          assert.ok(layout.padding >= 24 && layout.footerBottom <= height - 23, 'bottom content has a reachable safety margin');
          await submit.click({ trial: true });
        }
      }
      await page.getByRole('button', { name: 'ورود', exact: true }).click();
      console.log('PASS login/register buttons reachable in short mobile viewports with bottom padding');
      await page.setViewportSize({width:390,height:844});
      await page.screenshot({path:path.join(os.tmpdir(),'ft-auth-login.png')});
      await page.getByLabel('نام کاربری',{exact:true}).fill('returning');
      await page.getByLabel('رمز عبور',{exact:true}).fill('wrong');
      await page.getByRole('button',{name:'ورود به حساب',exact:true}).click();
      await page.getByRole('alert').waitFor();
      assert.equal(await page.locator('.auth-screen').count(),1);
      await page.getByLabel('رمز عبور',{exact:true}).fill('correct-password');
      await page.getByRole('button',{name:'ورود به حساب',exact:true}).click();
      await page.getByText('امروز چقدر',{exact:false}).waitFor();
      assert.equal(await page.getByText('اسمت چیه؟',{exact:true}).count(),0);
      assert.equal(await page.evaluate(()=>localStorage.getItem('ft.access')),'login-access');
      assert.equal(calls.filter(c=>c.path.includes('/register/')||c.path.includes('/guest/')).length,0);
      await context.close(); console.log('PASS fresh visit, responsive login, invalid password, original account login without onboarding');
    }
    {
      const {page,context,calls} = await setup();
      await page.getByRole('button',{name:'ثبت‌نام',exact:true}).click();
      await page.getByLabel('نام کاربری',{exact:true}).fill('new_player');
      await page.getByLabel('رمز عبور',{exact:true}).fill('Rainy!Password47');
      await page.getByLabel('تکرار رمز عبور',{exact:true}).fill('different-password');
      await page.getByRole('button',{name:'ثبت‌نام و ادامه',exact:true}).click();
      await page.getByRole('alert').waitFor();
      assert.equal(calls.length,0,'mismatched confirmation is caught before creating account');
      await page.getByLabel('تکرار رمز عبور',{exact:true}).fill('Rainy!Password47');
      await page.screenshot({path:path.join(os.tmpdir(),'ft-auth-register.png')});
      await page.getByRole('button',{name:'ثبت‌نام و ادامه',exact:true}).click();
      await page.getByText('اسمت چیه؟',{exact:true}).waitFor();
      await page.getByPlaceholder('نام نمایشی',{exact:true}).fill('بازیکن جدید');
      await page.getByRole('button',{name:'ادامه',exact:true}).click();
      await page.getByRole('button',{name:'زن',exact:true}).click();
      await page.getByRole('button',{name:'ادامه',exact:true}).click();
      await page.getByText('تاریخ تولدت؟',{exact:true}).waitFor();
      await page.getByRole('button',{name:'شروع',exact:true}).click();
      await page.getByText('امروز چقدر',{exact:false}).waitFor();
      assert.equal(calls.filter(c=>c.path==='/api/auth/register/').length,1);
      assert.equal(calls.filter(c=>c.path==='/api/users/me/'&&c.method==='PATCH').length,3);
      await context.close(); console.log('PASS registration follows existing name/avatar, gender and birth-date flow');
    }
    for(const scenario of ['expired','offline','refresh-offline','refresh']) {
      const tokens = scenario==='refresh' ? {'ft.refresh':'saved-refresh'} : {'ft.access':'saved-access','ft.refresh':'saved-refresh'};
      const {page,context,calls} = await setup(tokens,scenario);
      if(scenario==='expired') await page.getByRole('button',{name:'ورود به حساب',exact:true}).waitFor();
      else if(scenario.includes('offline')) {
        await page.getByRole('button',{name:'تلاش دوباره',exact:true}).waitFor();
        assert.equal(await page.evaluate(()=>localStorage.getItem('ft.refresh')),'saved-refresh','temporary failure preserves session');
      } else await page.getByText('امروز چقدر',{exact:false}).waitFor();
      assert.equal(calls.filter(c=>c.path==='/api/auth/guest/').length,0);
      await context.close(); console.log('PASS session recovery '+scenario);
    }
    assert.deepEqual(errors,[]);
  } finally { await browser.close(); }
})().catch(e=>{console.error(e);process.exitCode=1;});
