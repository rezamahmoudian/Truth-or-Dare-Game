// Visual fixtures only. Does not create accounts, enqueue or message live users.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const path=require('node:path');
const os=require('node:os');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try {
  const colorScheme=process.env.DESIGN_THEME||'light';
  const page=await browser.newPage({viewport:{width:390,height:844},colorScheme});
  const errors=[];page.on('pageerror',e=>{errors.push(e.message);console.error('Browser error:',e.message);});
  await page.addInitScript(()=>localStorage.setItem('ft.access','design-fixture'));
  const me={id:1,username:'reza',display_name:'رضا',avatar:'a3',age:27,gender:'M',is_guest:false,is_onboarded:true,streak_days:0};
  const people=[['مهسا','a2'],['آرمان','a5'],['نیلوفر','a7'],['علی','a9']].map(([display_name,avatar],i)=>({id:i+2,username:'player'+i,display_name,avatar,avatar_url:i===0?'/images/modes/girl.jpg':null,age:25,bio:'اهل موسیقی و بازی‌های گروهی',relation:'NONE',gender:'F'}));
  const modes=[['quick','شروع سریع','هم‌بازی اتفاقی'],['group','بازی گروهی','هرچی بیشتر، خنده‌ها بلندتر!'],['girls','بازی با دختر','یه آشنایی، یه بازی تازه'],['boys','بازی با پسر','یه هم‌بازی، کلی حرف'],['deep','بازی چالشی','جرئتش رو داری؟']].map(([key,title,subtitle])=>({key,title,subtitle,size_min:2,size_max:key==='group'?5:2,remaining_today:null,queue_state:'FAST',is_featured:key==='quick',is_ai:false}));
  const now=new Date().toISOString();
  const conv={id:'design-room',type:'ROOM',status:'ACTIVE',owner_id:1,code:'PLAY42',max_players:2,participants:[me,people[0]],created_at:now,last_message_at:now,last_message_preview:'آماده‌ای بازی کنیم؟',unread_count:2};
  const messages=['سلام! آماده‌ای بازی کنیم؟','سلام 😄 آره، بزن بریم!','پس شروع کنیم؛ جرئت یا حقیقت؟'].map((body,i)=>({id:i+1,body,type:'TEXT',conversation_id:conv.id,sender:i===1?me:people[0],created_at:now,reactions:{},meta:{},client_id:'m'+i,is_deleted:false}));
  const invite={id:1,user:people[0],direction:'incoming',status:'PENDING',created_at:now,conversation_id:null};
  await page.route('**/api/**',route=>{
   const u=new URL(route.request().url());let json;
   if(u.pathname==='/api/users/me/photo/')json={...me,avatar_url:route.request().method()==='DELETE'?null:'/images/modes/boy.jpg'};
   else if(u.pathname==='/api/lobby/')json={modes,active_people:people,online_count:24};
   else if(u.pathname==='/api/match/')json={state:'IDLE'};
   else if(u.pathname==='/api/friends/')json={friends:people.slice(1,3),incoming:[{id:1,user:people[0],direction:'incoming',created_at:now}],outgoing:[]};
   else if(u.pathname==='/api/game-invitations/')json={incoming:[invite],outgoing:[],ready:[]};
   else if(u.pathname==='/api/conversations/')json=[conv];
   else if(u.pathname.includes('/messages/'))json=messages;
   else if(u.pathname.includes('/game/'))json={session:null,turn:null};
   else if(u.pathname==='/api/conversations/design-room/')json=conv;
   else if(u.pathname.startsWith('/api/people/'))json=people[0];
   else json=[];
   return route.fulfill({json});
  });
  await page.route('**/__design*',route=>route.fulfill({contentType:'text/html',body:`<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script type="module">
   import RefreshRuntime from '/@react-refresh';RefreshRuntime.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(type)=>type;window.__vite_plugin_react_preamble_installed__=true;
   const {default:React}=await import('/node_modules/.vite/deps/react.js');const {default:ReactDOM}=await import('/node_modules/.vite/deps/react-dom_client.js');
   const source=await(await fetch('/src/features/play/PlayScreen.tsx')).text();const {MemoryRouter,Routes,Route}=await import(source.match(/"([^"]*react-router-dom[^\"]*)"/)[1]);
   const {useSession}=await import('/src/store/session.ts');useSession.setState({user:${JSON.stringify(me)},status:'ready'});
   const {useChat}=await import('/src/store/chat.ts');useChat.setState({status:'open',conversations:[${JSON.stringify(conv)}],online:{'design-room':[1,2]}});
   const {useInvitations}=await import('/src/store/invitations.ts');useInvitations.setState({lists:{incoming:[${JSON.stringify(invite)}],outgoing:[],ready:[]}});
   const {PlayScreen}=await import('/src/features/play/PlayScreen.tsx');const {FriendsScreen}=await import('/src/features/friends/FriendsScreen.tsx');const {ProfileScreen}=await import('/src/features/profile/ProfileScreen.tsx');const {ChatListScreen}=await import('/src/features/chat/ChatListScreen.tsx');const {ChatRoomScreen}=await import('/src/features/chat/ChatRoomScreen.tsx');const {GameInvitationsScreen}=await import('/src/features/play/GameInvitations.tsx');
   await import('/src/index.css');const el=React.createElement;const screen=new URLSearchParams(location.search).get('screen')||'/';
   ReactDOM.createRoot(document.getElementById('root')).render(el(MemoryRouter,{initialEntries:[screen]},el(Routes,null,...[['/',PlayScreen],['/friends',FriendsScreen],['/profile',ProfileScreen],['/chats',ChatListScreen],['/c/:id',ChatRoomScreen],['/invitations',GameInvitationsScreen]].map(([path,C])=>el(Route,{key:path,path,element:el(C)})))));
  </script></body></html>`}));
  for(const [name,screen,ready] of [['home','/','شروع سریع'],['friends','/friends','درخواست‌ها (۱)'],['profile','/profile','پروفایل'],['chats','/chats','روم PLAY42'],['chat','/c/design-room','پس شروع کنیم؛ جرئت یا حقیقت؟'],['invites','/invitations','دعوت‌های بازی']]){
   await page.goto('http://localhost:5173/__design?screen='+encodeURIComponent(screen));
   await page.getByText(ready,{exact:true}).first().waitFor();
   await page.evaluate(()=>document.fonts.ready);
   if(name==='home'){await page.locator('.mode-photo').first().evaluate(img=>img.decode());}
   await page.screenshot({path:path.join(os.tmpdir(),'ft-redesign-'+name+'-'+colorScheme+'.png')});
   if(name==='home'){
    assert.equal(await page.locator('.app-shell').evaluate(el=>getComputedStyle(el).backgroundColor),'rgb(21, 19, 31)');
    const cards=page.locator('.mini-playing-card');
    const transforms=()=>cards.evaluateAll(els=>els.map(el=>getComputedStyle(el).transform));
    const before=await transforms();
    await page.locator('.quick-card').hover();
    await cards.evaluateAll(els=>Promise.all(els.flatMap(el=>el.getAnimations().map(a=>a.finished))));
    const after=await transforms();
    assert.ok(after.every((value,i)=>value!==before[i]),'both playing cards move on hover');
    await page.screenshot({path:path.join(os.tmpdir(),'ft-redesign-hover-'+colorScheme+'.png')});
    await page.mouse.move(0,0);
    await cards.evaluateAll(els=>Promise.all(els.flatMap(el=>el.getAnimations().map(a=>a.finished))));
    assert.deepEqual(await transforms(),before,'cards return when pointer leaves');
    await page.locator('.mode-photo-card').first().hover();
    const photo=page.locator('.mode-photo').first();
    await photo.evaluate(el=>Promise.all(el.getAnimations().map(a=>a.finished)));
    assert.equal(await photo.evaluate(el=>getComputedStyle(el).transform),'matrix(1.04, 0, 0, 1.04, 0, 0)');
    await page.locator('.mode-photo-card').first().screenshot({path:path.join(os.tmpdir(),'ft-redesign-photo-hover-'+colorScheme+'.png')});
    await page.mouse.move(0,0);
    console.log('PASS '+colorScheme+' reference colors and hover animations');
   }
   for(const width of [320,390,768]){
    await page.setViewportSize({width,height:844});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,name+' horizontal overflow');
    if(name==='home' && width===320)await page.screenshot({path:path.join(os.tmpdir(),'ft-redesign-home-320.png')});
   }
   await page.setViewportSize({width:390,height:844});
   if(name==='profile'){
    await page.getByLabel('فایل عکس پروفایل').setInputFiles(path.join(__dirname,'../frontend/public/images/modes/boy.jpg'));
    await page.getByRole('button',{name:'ذخیره عکس',exact:true}).click();
    await page.getByRole('status').filter({hasText:'عکس پروفایل به‌روز شد.'}).waitFor();
    assert.equal(await page.locator('.profile-card img').getAttribute('src'),'/images/modes/boy.jpg');
    await page.locator('.profile-card img').evaluate(img=>img.decode());
    await page.screenshot({path:path.join(os.tmpdir(),'ft-profile-photo.png')});
    await page.getByRole('button',{name:'حذف عکس',exact:true}).click();
    await page.waitForFunction(()=>!document.querySelector('.profile-card img'));
    console.log('PASS profile photo preview, save, shared avatar and removal');
   }
   if(name==='chat'){
    await page.getByAltText('عکس مهسا').first().evaluate(img=>img.decode());
    const composerLayout=await page.evaluate(()=>{
      const voice=document.querySelector('[aria-label="برای ضبط وویس نگه دارید"]');
      const field=document.querySelector('.composer-field');
      if(!voice || !field) return null;
      const vr=voice.getBoundingClientRect(), fr=field.getBoundingClientRect();
      return {voiceLeft:vr.left, fieldRight:fr.right, voiceCenter:vr.left+vr.width/2, fieldCenter:fr.left+fr.width/2};
    });
    assert.ok(composerLayout && composerLayout.voiceCenter > composerLayout.fieldCenter,'voice control is on the right side');
   }
   if(name==='home'){
    await page.getByText('بازی با دوستات',{exact:true}).scrollIntoViewIfNeeded();
    await page.screenshot({path:path.join(os.tmpdir(),'ft-redesign-home-lower.png')});
   }
   console.log('PASS '+name+' responsive layout');
  }
  assert.deepEqual(errors,[]);
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
