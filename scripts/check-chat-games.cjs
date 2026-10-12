// Isolated UI fixture: no real messages, accounts or games are created.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const path=require('node:path');
const os=require('node:os');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:390,height:844}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  let current={session:null,turn:null};let posts=[];let friend=true;
  const conv={id:'fixture-room',type:'ROOM',status:'ACTIVE',owner_id:2,max_players:2,participants:[{id:1,display_name:'رضا'},{id:2,display_name:'مهسا'}]};
  await page.route('**/api/**',route=>{
   const req=route.request();
   if(req.method()==='POST'){
    const body=req.postDataJSON();posts.push(body);
    current={session:{id:posts.length,conversation_id:conv.id,status:'ACTIVE',turn_order:[1,2],turn_index:0,round_number:1,play_mode:body.play_mode,category:'',max_intensity:body.max_intensity,ended_reason:''},turn:{id:posts.length,player_id:1,status:body.play_mode==='DEEP_TALK'?'ANSWERING':'CHOOSING',choice:'TRUTH',prompt:body.play_mode==='DEEP_TALK'?{id:1,text:'سؤال آزمایشی',type:'TRUTH',category:'BOLD',intensity:3}:null,confirmations:[],confirmations_required:1}};
   }
   return route.fulfill({json:current});
  });
  await page.route('**/__chat-games',route=>route.fulfill({contentType:'text/html',body:`<!doctype html><html dir="rtl" lang="fa"><head><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"></head><body><div id="root"></div><script type="module">
   import RefreshRuntime from '/@react-refresh';RefreshRuntime.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(type)=>type;window.__vite_plugin_react_preamble_installed__=true;
   const {default:React}=await import('/node_modules/.vite/deps/react.js');const {default:ReactDOM}=await import('/node_modules/.vite/deps/react-dom_client.js');
   const source=await(await fetch('/src/features/chat/ChatGameLauncher.tsx')).text();
   const storePath=source.split(';').find(line=>line.includes('import')&&line.includes('/store/social.ts')).match(/"([^"]*store[^"]*)"/)[1];
   const {useSocial}=await import(storePath);useSocial.setState({lists:{friends:${friend?'[{id:2}]':'[]'},incoming:[],outgoing:[]}});
   const {ChatGameLauncher}=await import('/src/features/chat/ChatGameLauncher.tsx');
   const {GamePanel}=await import('/src/features/game/GamePanel.tsx');await import('/src/index.css');
   const el=React.createElement;
   ReactDOM.createRoot(document.getElementById('root')).render(el('div',{className:'chat-screen chat-room'},el('header',{className:'chat-header flex p-3'},el('h1',{className:'flex-1'},'مهسا'),el(ChatGameLauncher,{conversation:${JSON.stringify(conv)},selfId:1})),el(GamePanel,{conversationId:'fixture-room',selfId:1,participants:${JSON.stringify(conv.participants)},isOwner:false,hideStart:true,pairChat:true})));
  </script></body></html>`}));
  await page.goto('http://localhost:5173/__chat-games');
  await page.getByRole('button',{name:'شروع بازی جدید',exact:true}).click();
  await page.getByRole('button',{name:/فقط بین خودمون/}).click();
  const submit=page.getByRole('button',{name:'بریم سر حرف‌های نگفته 😉',exact:true});
  await submit.waitFor();
  for(const width of [320,390,768]){
   await page.setViewportSize({width,height:568});
   await submit.scrollIntoViewIfNeeded();await submit.click({trial:true});
   assert.ok(await page.getByRole('dialog').evaluate(el=>el.scrollWidth<=el.clientWidth),'no horizontal overflow in game picker');
  }
  await page.setViewportSize({width:390,height:844});await page.evaluate(()=>document.fonts.ready);
  await page.screenshot({path:path.join(os.tmpdir(),'ft-deep-game-picker.png')});
  await submit.click();await page.getByRole('dialog').waitFor({state:'hidden'});
  assert.deepEqual(posts[0],{max_intensity:3,play_mode:'DEEP_TALK'});
  await page.getByText('جوابت رو بنویس…',{exact:true}).waitFor();
  assert.equal(await page.getByRole('button',{name:'جرئت',exact:true}).count(),0);
  assert.equal(await page.getByRole('button',{name:'پایان بازی',exact:true}).count(),1,'nonowner friend can end');
  await page.getByRole('button',{name:'شروع بازی جدید',exact:true}).click();
  await page.getByRole('checkbox').waitFor();
  const classic=page.getByRole('dialog').getByRole('button',{name:'شروع بازی جدید',exact:true});
  assert.equal(await classic.isDisabled(),true);
  await page.getByRole('checkbox').check();await classic.click();
  await page.getByRole('dialog').waitFor({state:'hidden'});
  assert.deepEqual(posts[1],{max_intensity:2,play_mode:'CLASSIC',replace_session_id:1});
  await page.getByRole('button',{name:'جرئت',exact:true}).waitFor();
  assert.equal(await page.getByRole('button',{name:'شروع بازی جدید',exact:true}).count(),1,'launcher remains accessible in active game');
  console.log('PASS friend nonowner start, deep mode, mobile picker, same chat, restart confirmation and classic controls');
  friend=false;conv.owner_id=1;current={session:null,turn:null};
  await page.reload();await page.getByRole('button',{name:'شروع بازی جدید',exact:true}).click();
  assert.equal(await page.getByRole('button',{name:/فقط بین خودمون/}).count(),0);
  await page.keyboard.press('Escape');assert.equal(await page.getByRole('dialog').count(),0);
  assert.deepEqual(errors,[]);console.log('PASS deep option hidden for nonfriends and picker closes with Escape');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
