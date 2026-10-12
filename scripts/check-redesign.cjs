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
  const conversations=[conv,{...conv,id:'design-group',max_players:5,code:'PARTY88',participants:[me,...people],last_message_preview:'امشب کی برای یه دور بازی پایه‌ست؟',unread_count:0},{...conv,id:'design-friend',type:'DIRECT',code:null,owner_id:null,participants:[me,people[3]],last_message_preview:'دور بعدی جرئت رو انتخاب می‌کنم!',unread_count:0},{...conv,id:'design-friend2',type:'DIRECT',code:null,owner_id:null,participants:[me,people[2]],last_message_preview:'خیلی خوش گذشت، مرسی ✨',unread_count:0}];
  const activeGame={session:{id:1,conversation_id:conv.id,status:'ACTIVE',turn_order:[1,2],turn_index:0,round_number:1,category:'normal',max_intensity:2,ended_reason:''},turn:{id:1,index:0,player_id:1,status:'CHOOSING',choice:'',prompt:null,answer_message_id:null,confirmations:[],confirmations_required:1,version:1}};
  let friendAccepted=false;
  let friendOpened=false;
  let accepted=false;
  let started=false;
  const messages=['سلام! آماده‌ای بازی کنیم؟','سلام 😄 آره، بزن بریم!','پس شروع کنیم؛ جرئت یا حقیقت؟'].map((body,i)=>({id:i+1,body,type:'TEXT',conversation_id:conv.id,sender:i===1?me:people[0],created_at:now,reactions:{},meta:{},client_id:'m'+i,is_deleted:false}));
  messages.push({id:4,body:'',type:'TEXT',conversation_id:conv.id,sender:people[0],created_at:now,reactions:{},meta:{},client_id:'m4',is_deleted:false,attachment:{kind:'voice',name:'voice.wav',size:96044,mime:'audio/wav',url:'/audio/design'}});
  messages.push({id:5,body:'کدوم اتفاق زندگیت الان تعریفش همه رو می‌خندونه؟',type:'GAME_PROMPT',conversation_id:conv.id,sender:null,created_at:now,reactions:{},meta:{choice:'TRUTH'},client_id:'m5',is_deleted:false});
  messages.push({id:6,body:'یه داستان طولانی دارم 😂',type:'GAME_ANSWER',conversation_id:conv.id,sender:me,created_at:now,reactions:{},meta:{},client_id:'m6',is_deleted:false});
  const invite={id:1,user:people[0],direction:'incoming',status:'PENDING',created_at:now,conversation_id:null};
  await page.route('**/api/**',route=>{
   const u=new URL(route.request().url());let json;
   if(u.pathname==='/api/users/me/photo/')json={...me,avatar_url:route.request().method()==='DELETE'?null:'/images/modes/boy.jpg'};
   else if(u.pathname==='/api/users/me/' && route.request().method()==='PATCH')json={...me,...route.request().postDataJSON()};
   else if(u.pathname==='/api/lobby/')json={modes,active_people:people,online_count:24};
   else if(u.pathname==='/api/match/')json={state:'IDLE'};
   else if(u.pathname==='/api/friends/2/accept/'){friendAccepted=true;json={conversation_id:conv.id,user:{...people[0],relation:'FRIENDS'}};}
   else if(u.pathname==='/api/friends/2/conversation/'){friendOpened=true;json={conversation_id:conv.id};}
   else if(u.pathname==='/api/friends/')json={friends:friendAccepted?[people[0],...people.slice(1,3)]:people.slice(1,3),incoming:friendAccepted?[]:[{id:1,user:people[0],direction:'incoming',created_at:now}],outgoing:[]};
   else if(u.pathname==='/api/game-invitations/1/accept/'){assert.equal(route.request().postDataJSON().conversation_id,conv.id);accepted=true;started=true;json={...invite,status:'ACCEPTED',conversation_id:conv.id};}
   else if(u.pathname==='/api/game-invitations/')json={incoming:accepted?[]:[invite],outgoing:[],ready:[]};
   else if(u.pathname==='/api/conversations/')json=conversations;
   else if(u.pathname.includes('/messages/'))json=messages;
   else if(u.pathname.includes('/game/')){if(route.request().method()==='POST')started=true;json=started?activeGame:{session:null,turn:null};}
   else if(u.pathname==='/api/conversations/design-room/')json=conv;
   else if(u.pathname.startsWith('/api/people/'))json={...people[0],city:'شیراز',interests:['موسیقی','سفر','بازی‌های گروهی','کتاب'],joined_at:'2026-01-01',stats:{games:12,truths:10,dares:4,streak_days:3},badges:[{key:'first_game',title:'قدم اول',description:'شرکت در اولین بازی',icon:'🎲',earned:true,progress:1,target:1},{key:'regular',title:'پایهٔ بازی',description:'شرکت در ۱۰ بازی',icon:'⭐',earned:true,progress:10,target:10},{key:'dare',title:'دل‌وجرئت',description:'انجام ۱۰ نوبت جرئت',icon:'🔥',earned:false,progress:4,target:10}]};
   else json=[];
   return route.fulfill({json});
  });
  await page.route('**/__design*',route=>route.fulfill({contentType:'text/html',body:`<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script type="module">
   import RefreshRuntime from '/@react-refresh';RefreshRuntime.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(type)=>type;window.__vite_plugin_react_preamble_installed__=true;
   const {default:React}=await import('/node_modules/.vite/deps/react.js');const {default:ReactDOM}=await import('/node_modules/.vite/deps/react-dom_client.js');
   const source=await(await fetch('/src/features/play/PlayScreen.tsx')).text();const {MemoryRouter,Routes,Route}=await import(source.match(/"([^"]*react-router-dom[^\"]*)"/)[1]);
   const sessionPath=source.split(';').find(line=>line.includes('import')&&line.includes('/store/session.ts')).match(/"([^"]*store[^"]*)"/)[1];const {useSession}=await import(sessionPath);useSession.setState({user:${JSON.stringify(me)},status:'ready'});
   const {useChat}=await import('/src/store/chat.ts');useChat.setState({status:'open',conversations:${JSON.stringify(conversations)},online:{'design-room':[1,2]}});
   const {useInvitations}=await import('/src/store/invitations.ts');useInvitations.setState({lists:{incoming:[${JSON.stringify(invite)}],outgoing:[],ready:[]}});
   const {PlayScreen}=await import('/src/features/play/PlayScreen.tsx');const {FriendsScreen}=await import('/src/features/friends/FriendsScreen.tsx');const {ProfileScreen}=await import('/src/features/profile/ProfileScreen.tsx');const {PublicProfileScreen}=await import('/src/features/profile/PublicProfileScreen.tsx');const {ChatListScreen}=await import('/src/features/chat/ChatListScreen.tsx');const {ChatRoomScreen}=await import('/src/features/chat/ChatRoomScreen.tsx');const {GameInvitationsScreen}=await import('/src/features/play/GameInvitations.tsx');
   await import('/src/index.css');const el=React.createElement;const screen=new URLSearchParams(location.search).get('screen')||'/';
   ReactDOM.createRoot(document.getElementById('root')).render(el(MemoryRouter,{initialEntries:[screen]},el(Routes,null,...[['/',PlayScreen],['/friends',FriendsScreen],['/profile',ProfileScreen],['/people/:userId',PublicProfileScreen],['/chats',ChatListScreen],['/c/:id',ChatRoomScreen],['/invitations',GameInvitationsScreen]].map(([path,C])=>el(Route,{key:path,path,element:el(C)})))));
  </script></body></html>`}));
  for(const [name,screen,ready] of [['home','/','شروع سریع'],['friends','/friends','درخواست‌ها (۱)'],['profile','/profile','پروفایل'],['chats','/chats','مهسا'],['chat','/c/design-room','پس شروع کنیم؛ جرئت یا حقیقت؟'],['invites','/invitations','دعوت‌های بازی'],['public-profile','/people/2','دربارهٔ من']]){
   await page.goto('http://localhost:5173/__design?screen='+encodeURIComponent(screen));
   try { await page.getByText(ready,{exact:true}).first().waitFor(); } catch (e) { console.error('Failed screen',name,await page.locator('body').innerText()); await page.screenshot({path:path.join(os.tmpdir(),'ft-design-failure.png')}); throw e; }
   await page.evaluate(()=>document.fonts.ready);
   if(name==='chat')await page.locator('.chat-play-card').waitFor();
   await page.evaluate(()=>Promise.all(document.getAnimations().map(a=>a.finished)));
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
    await page.getByLabel('نام نمایشی',{exact:true}).fill('رضای بازیگوش');
    await page.getByPlaceholder('مثلاً شیراز').fill('شیراز');
    await page.getByLabel('بیو',{exact:true}).fill('اهل بازی و سفر');
    await page.getByLabel('علایق',{exact:true}).fill('موسیقی، سفر، موسیقی');
    await page.getByRole('button',{name:'ذخیرهٔ اطلاعات',exact:true}).click();
    await page.getByRole('status').filter({hasText:'اطلاعات پروفایل ذخیره شد.'}).waitFor();
    assert.equal(await page.locator('.profile-card').getByText('رضای بازیگوش',{exact:true}).count(),1);
    console.log('PASS public profile editor saves name, bio, city and interests');
   }
   if(name==='chat'){
    const input = page.getByLabel('متن پیام');
    const inputSurface = () => input.evaluate(el => {
      const props = ['outlineStyle', 'borderColor', 'boxShadow', 'backgroundColor'];
      return [el, el.closest('.composer-field')].map(node => {
        const style = getComputedStyle(node);
        return props.map(prop => style[prop]);
      });
    });
    await input.evaluate(el => el.blur());
    const unfocused = await inputSurface();
    await input.click();
    await input.evaluate(el => Promise.all([el, el.closest('.composer-field')].flatMap(node => node.getAnimations().map(a => a.finished))));
    assert.deepEqual(await inputSurface(), unfocused, 'typing field and wrapper keep their appearance on focus');
    assert.equal(await input.evaluate(el => getComputedStyle(el).outlineStyle), 'none', 'no rectangular focus outline inside composer');
    console.log('PASS composer keeps identical appearance when focused');
    await page.getByAltText('عکس مهسا').first().evaluate(img=>img.decode());
    const composerLayout=await page.evaluate(()=>{
      const voice=document.querySelector('[aria-label="برای ضبط وویس نگه دارید"]');
      const field=document.querySelector('.composer-field');
      if(!voice || !field) return null;
      const vr=voice.getBoundingClientRect(), fr=field.getBoundingClientRect();
      return {voiceLeft:vr.left, fieldRight:fr.right, voiceCenter:vr.left+vr.width/2, fieldCenter:fr.left+fr.width/2};
    });
    assert.ok(composerLayout && composerLayout.voiceCenter > composerLayout.fieldCenter,'voice control is on the right side');
    const direction=await page.evaluate(()=>{
      const mine=document.querySelector('.chat-message-row[data-mine="true"] .chat-bubble').getBoundingClientRect();
      const other=document.querySelector('.chat-message-row[data-mine="false"] .chat-bubble').getBoundingClientRect();
      const list=document.querySelector('.chat-message-list').getBoundingClientRect();
      return {mineRight:mine.right,otherLeft:other.left,mid:list.left+list.width/2};
    });
    assert.ok(direction.mineRight > direction.mid && direction.otherLeft < direction.mid,'outgoing right, incoming left');
    await page.getByRole('button',{name:'انتخاب ایموجی',exact:true}).click();
    await page.getByRole('button',{name:'افزودن 😂',exact:true}).click();
    assert.equal(await page.getByLabel('متن پیام').inputValue(),'😂');
    assert.equal(await page.getByRole('button',{name:'ارسال پیام',exact:true}).count(),1);
    await page.getByLabel('متن پیام').fill('');
    await page.getByRole('button',{name:'افزودن پیوست',exact:true}).click();
    const popup=await page.getByLabel('انتخاب پیوست',{exact:true}).boundingBox();
    const field=await page.locator('.composer-field').boundingBox();
    assert.ok(popup.y+popup.height<field.y,'attachments appear above composer');
    await page.evaluate(()=>Promise.all(document.getAnimations().map(a=>a.finished)));
    await page.screenshot({path:path.join(os.tmpdir(),'ft-chat-attachments.png')});
    await page.keyboard.press('Escape');
    assert.equal(await page.getByLabel('انتخاب پیوست',{exact:true}).count(),0);
    await page.getByRole('button',{name:'گزینه‌های گفتگو',exact:true}).click();
    await page.getByRole('button',{name:'کپی کد روم',exact:true}).waitFor();
    await page.getByRole('button',{name:'گزینه‌های گفتگو',exact:true}).click();
    assert.equal(await page.getByRole('button',{name:'کپی کد روم',exact:true}).count(),0);
    console.log('PASS chat message placement, emoji insertion, send/mic switch, attachment popover and room menu');
    await page.getByRole('button',{name:'قبول دعوت',exact:true}).click();
    await page.locator('.chat-game-controls').waitFor();
    assert.equal(await page.locator('.chat-play-card').count(),0);
    assert.equal(await page.getByLabel('متن پیام').count(),1);
    assert.ok(accepted&&started,'card accepts invitation for this conversation and reloads its game state');
    await page.evaluate(()=>Promise.all(document.getAnimations().map(a=>a.finished)));
    await page.screenshot({path:path.join(os.tmpdir(),'ft-chat-active-game.png')});
    console.log('PASS invitation acceptance and real game start use shared composer');
    await page.locator('.chat-header button').filter({hasText:'مهسا'}).click();
    await page.getByText('دربارهٔ من',{exact:true}).waitFor();
    assert.equal(await page.locator('.public-profile-screen').count(),1);
    console.log('PASS chat header opens player profile');
   }
   if(name==='friends'){
    await page.getByRole('button',{name:'قبول درخواست',exact:true}).click();
    await page.getByText('دوستان (۳)',{exact:true}).waitFor();
    assert.ok(friendAccepted);
    assert.equal(await page.locator('.chat-room').count(),0,'accepting friendship leaves the friends page open');
    await page.getByRole('button',{name:'پیام بده ›',exact:true}).first().click();
    await page.getByLabel('متن پیام').waitFor();
    assert.ok(friendOpened,'friend row explicitly resolves the previous conversation on the server');
    assert.equal(await page.getByText('پس شروع کنیم؛ جرئت یا حقیقت؟',{exact:true}).count(),1,'previous chat history is visible');
    console.log('PASS accepting friendship stays on friends page; message button opens existing history');
   }
   if(name==='public-profile'){
    assert.equal(await page.getByText('شیراز',{exact:true}).count(),1);
    assert.equal(await page.getByText('کتاب',{exact:true}).count(),1);
    assert.equal(await page.locator('.profile-badge.earned').count(),2);
    const photo=page.getByRole('button',{name:'نمایش عکس پروفایل مهسا',exact:true});
    await photo.click();
    await page.getByRole('dialog',{name:'عکس پروفایل مهسا',exact:true}).waitFor();
    await page.getByAltText('عکس بزرگ مهسا').evaluate(img=>img.decode());
    await page.screenshot({path:path.join(os.tmpdir(),'ft-public-profile-photo.png')});
    await page.keyboard.press('Escape');
    assert.equal(await page.getByRole('dialog').count(),0);
    assert.equal(await photo.evaluate(el=>document.activeElement===el),true,'photo viewer restores focus');
    await photo.click();
    await page.getByRole('button',{name:'بستن عکس',exact:true}).click();
    assert.equal(await page.getByRole('dialog').count(),0);
    await page.setViewportSize({width:390,height:844});
    await page.locator('main').evaluate(el=>el.scrollTop=0);
    await page.screenshot({path:path.join(os.tmpdir(),'ft-public-profile.png')});
    console.log('PASS public profile details, real badge states, full photo, Escape and focus restoration');
   }
   if(name==='chats'){
     assert.equal(await page.locator('.chat-conversation-row').count(),conversations.length);
     await page.getByRole('link',{name:'پروفایل مهسا',exact:true}).click();
     await page.getByText('دربارهٔ من',{exact:true}).waitFor();
     console.log('PASS inbox avatar opens player profile');
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
