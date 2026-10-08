// Isolated browser fixtures: no requests or messages are sent to real accounts.
const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const path = require("node:path");
const os = require("node:os");

(async () => {
  const browser = await chromium.launch({channel:"msedge",headless:true});
  try {
    const page = await browser.newPage({viewport:{width:390,height:844}});
    const errors=[]; page.on("pageerror", e=>errors.push(e.message));
    await page.addInitScript(()=>localStorage.setItem("ft.access","fixture-token"));
    const person={id:22,username:"mahsa",display_name:"مهسا",avatar:"a2",age:25,bio:"اهل موسیقی و بازی‌های گروهی",gender:"F",relation:"NONE"};
    let friends={friends:[],incoming:[],outgoing:[]};
    let invitations={incoming:[],outgoing:[],ready:[]};
    let friendSent=0, gameSent=0, accepted=0;
    const invite={id:17,user:person,direction:"outgoing",status:"PENDING",conversation_id:null,created_at:new Date().toISOString()};
    await page.route("**/api/**", async route=>{
      const url=new URL(route.request().url()); const method=route.request().method();
      if(url.pathname==="/api/lobby/") return route.fulfill({json:{modes:[],online_count:2,active_people:[person]}});
      if(url.pathname==="/api/match/") return route.fulfill({json:{state:"IDLE"}});
      if(url.pathname==="/api/people/22/") return route.fulfill({json:person});
      if(url.pathname==="/api/friends/") return route.fulfill({json:friends});
      if(url.pathname==="/api/game-invitations/") return route.fulfill({json:invitations});
      if(url.pathname==="/api/friends/22/" && method==="POST") {
        friendSent++; person.relation="OUTGOING";
        friends.outgoing=[{id:9,user:person,direction:"outgoing",created_at:new Date().toISOString()}];
        return route.fulfill({json:person});
      }
      if(url.pathname==="/api/people/22/invite/" && method==="POST") {
        gameSent++; invitations.outgoing=[invite]; return route.fulfill({json:invite});
      }
      if(url.pathname==="/api/game-invitations/17/accept/") {
        accepted++; invitations={incoming:[],outgoing:[],ready:[{...invite,status:"ACCEPTED",conversation_id:"game-room"}]};
        return route.fulfill({json:{...invite,status:"ACCEPTED",conversation_id:"game-room"}});
      }
      if(url.pathname==="/api/friends/22/accept/") {
        friends={friends:[person],incoming:[],outgoing:[]};
        return route.fulfill({json:{conversation_id:"friend-room",user:{...person,relation:"FRIENDS"}}});
      }
      return route.fulfill({status:404,json:{detail:"unmocked endpoint"}});
    });
    await page.route("**/__online-ui*",route=>route.fulfill({contentType:"text/html",body:`<!doctype html><html dir="rtl" lang="fa"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script type="module">
      import RefreshRuntime from '/@react-refresh';
      RefreshRuntime.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(type)=>type;window.__vite_plugin_react_preamble_installed__=true;
      const {default:React}=await import('/node_modules/.vite/deps/react.js');
      const {default:ReactDOM}=await import('/node_modules/.vite/deps/react-dom_client.js');
      const source=await (await fetch('/src/features/play/PlayScreen.tsx')).text();
      const {MemoryRouter,Routes,Route,useParams}=await import(source.match(/"([^"]*react-router-dom[^\"]*)"/)[1]);
      const {PlayScreen}=await import('/src/features/play/PlayScreen.tsx');
      const {GameInvitationsScreen}=await import('/src/features/play/GameInvitations.tsx');
      const {FriendsScreen}=await import('/src/features/friends/FriendsScreen.tsx');
      await import('/src/index.css');
      const el=React.createElement;
      function Room(){return el('p',{'data-testid':'room'},useParams().id)}
      ReactDOM.createRoot(document.getElementById('root')).render(el(MemoryRouter,{initialEntries:[location.search.includes('friends')?'/friends':'/']},el(Routes,null,
        el(Route,{path:'/',element:el(PlayScreen)}),el(Route,{path:'/invitations',element:el(GameInvitationsScreen)}),el(Route,{path:'/friends',element:el(FriendsScreen)}),el(Route,{path:'/c/:id',element:el(Room)}))));
    </script></body></html>`}));
    await page.goto("http://localhost:5173/__online-ui");
    await page.getByRole("button",{name:"پروفایل مهسا",exact:true}).click();
    await page.getByText(person.bio,{exact:true}).waitFor();
    await page.getByRole("button",{name:"+ افزودن دوست",exact:true}).click();
    await page.getByRole("button",{name:"در انتظار…",exact:true}).waitFor();
    assert.equal(friendSent,1);
    await page.getByRole("button",{name:"🎲 درخواست بازی دونفره",exact:true}).click();
    await page.getByText(/دعوت فرستاده شد/).waitFor(); assert.equal(gameSent,1);
    await page.setViewportSize({width:320,height:740});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    await page.screenshot({path:path.join(os.tmpdir(),"ft-online-profile.png")});
    await page.getByRole("button",{name:"بستن",exact:true}).click();
    assert.equal(await page.getByRole("button",{name:"لغو دعوت",exact:true}).count(),0);
    await page.getByRole("button",{name:/^دعوت‌ها/}).click();
    await page.getByRole("button",{name:/ارسالی/}).click();
    await page.getByRole("button",{name:"لغو دعوت",exact:true}).waitFor();
    console.log("PASS online profile, friend request, game invitation and 320px layout");
    invitations={incoming:Array.from({length:40},(_,i)=>({...invite,id:17+i,direction:"incoming"})),outgoing:[],ready:[]};
    await page.reload();
    assert.equal(await page.getByRole("button",{name:"قبول و شروع بازی",exact:true}).count(),0);
    await page.getByRole("button",{name:/^دعوت‌ها/}).click();
    await page.getByRole("button",{name:"نمایش بیشتر",exact:true}).waitFor();
    assert.equal(await page.getByRole("button",{name:"قبول و شروع بازی",exact:true}).count(),15);
    await page.getByRole("button",{name:"نمایش بیشتر",exact:true}).click();
    assert.equal(await page.getByRole("button",{name:"قبول و شروع بازی",exact:true}).count(),30);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    await page.screenshot({path:path.join(os.tmpdir(),"ft-invitations-screen.png")});
    await page.getByRole("button",{name:"قبول و شروع بازی",exact:true}).first().click();
    await page.getByTestId("room").waitFor(); assert.equal(await page.getByTestId("room").textContent(),"game-room"); assert.equal(accepted,1);
    friends={friends:[],outgoing:[],incoming:[{id:9,user:{...person,relation:"INCOMING"},direction:"incoming",created_at:new Date().toISOString()}]};
    await page.goto("http://localhost:5173/__online-ui?friends");
    await page.getByRole("button",{name:"قبول درخواست",exact:true}).click();
    await page.getByTestId("room").waitFor(); assert.equal(await page.getByTestId("room").textContent(),"friend-room");
    assert.deepEqual(errors,[]);
    console.log("PASS separate invitation inbox, 40-invite batching, mobile layout, game acceptance and friend acceptance");
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
