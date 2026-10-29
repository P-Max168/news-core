const fs=require('fs'),assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const jsQR=require('jsqr'),{PNG}=require('pngjs');
(async()=>{
 const b=await chromium.launch({executablePath:process.env.CHROMIUM_EXECUTABLE || undefined,args:JSON.parse(process.env.CHROMIUM_ARGS_JSON || '["--no-sandbox"]'),headless:true});
 const ctx=await b.newContext({viewport:{width:390,height:844},deviceScaleFactor:2,serviceWorkers:'block'});
 await ctx.addInitScript(()=>{localStorage.setItem('tnk.profile.v1',JSON.stringify({v:1,onboarded:true,persona:'pattaya',topics:['east','visa','life','weather','society'],taste:{w:{},votes:{}},ui:{},updatedAt:1}));Math.random=()=>.94;});
 const page=await ctx.newPage(),errors=[];page.on('pageerror',e=>errors.push(String(e)));
 const base=process.argv[2]||'http://127.0.0.1:8765/';
 await page.goto(base,{waitUntil:'domcontentloaded'});
 await page.waitForFunction(()=>window.TNAds&&TNAds.active()&&document.querySelectorAll('.card,.top-card').length>0);
 await page.waitForFunction(()=>[...document.querySelectorAll('tn-partner-ad')].every(x=>x.getAttribute('data-ready')==='1'));
 const initial=await page.evaluate(()=>({cards:document.querySelectorAll('.card,.top-card').length,ads:document.querySelectorAll('.tn-campaign').length,bodyWidth:document.documentElement.scrollWidth,viewport:innerWidth}));
 assert(initial.cards>0);assert(initial.ads>0);assert(initial.bodyWidth<=initial.viewport+1);
 const weights=await page.evaluate(()=>{const c=TN_ADS.campaign.items,counts={};for(let i=0;i<100;i++){let x=TNAds.pick((i+.5)/100,c);counts[x.id]=(counts[x.id]||0)+1}return counts});
 assert.deepEqual(weights,{dragon:40,seven:12,suwon:12,lounge:12,dongwon:12,kt:12});
 const stable=await page.evaluate(()=>{let sl=TN_ADS.slots[0];let a=TNAds.renderSlot(sl,'stability'),b=TNAds.renderSlot(sl,'stability');return a.item.id===b.item.id&&a.html===b.html});assert(stable);
 await page.locator('[data-ad-slot="top"] .tn-campaign').scrollIntoViewIfNeeded();
 await page.waitForFunction(()=>(TNAds.snapshot().counts.viewable.kt||0)>0);
 const counted=await page.evaluate(()=>TNAds.snapshot());
 assert((counted.counts.viewable.kt||0)>0,'Actual visible homepage advertisement counted');
 const before=await page.evaluate(()=>TNAds.snapshot().counts.viewable.kt||0);
 await page.evaluate(()=>{let el=document.querySelector('[data-ad-slot="top"]');el.innerHTML=TNAds.renderSlot(TN_ADS.slots.find(s=>s.id==='top'),'top:0').html;});
 await page.waitForTimeout(1500);
 assert.equal(await page.evaluate(()=>TNAds.snapshot().counts.viewable.kt||0),before,'No duplicate top impression on redraw');
 const findings=[];
 for(const width of [320,390,1280]){
  await page.setViewportSize({width,height:900});
  await page.evaluate(()=>{document.querySelector('#campaign-harness')?.remove();let d=document.createElement('div');d.id='campaign-harness';d.style='position:relative;background:white;max-width:1200px;margin:0 auto;';document.body.prepend(d)});
  for(const [id,u] of [['dragon',.2],['seven',.45],['suwon',.57],['lounge',.69],['dongwon',.81],['kt',.94]]){
   for(const variant of ['large','strip','small','bar']){
    await page.evaluate(({id,u,variant,width})=>{Math.random=()=>u;let sl={id:'infeed',enabled:true,items:[{variant,render:'dragon',theme:5}]};let d=document.getElementById('campaign-harness');d.innerHTML=TNAds.renderSlot(sl,`test:${width}:${id}:${variant}`).html;},{id,u,variant,width});
    const host=page.locator('#campaign-harness tn-partner-ad');
    if(id!=='dragon')await host.waitFor({state:'attached'});
    if(id!=='dragon')await page.waitForFunction(()=>document.querySelector('#campaign-harness tn-partner-ad')?.getAttribute('data-ready')==='1');
    const el=id==='dragon'?page.locator('#campaign-harness .dm-ad'):host.locator('article');
    await el.scrollIntoViewIfNeeded();
    await page.waitForTimeout(60);
    const bounds=await el.evaluate(a=>{let r=a.getBoundingClientRect();let heading=a.querySelector('h2');let h=heading?.getBoundingClientRect();return {width:r.width,height:r.height,headingInside:!h||(h.left>=r.left-1&&h.right<=r.right+1&&h.top>=r.top-1&&h.bottom<=r.bottom+1)}});
    assert(bounds.width>0&&bounds.height>0);assert(bounds.headingInside,`Heading clipped: ${width}/${id}/${variant}`);
    if(id==='kt'){
     const qr=host.locator('.line-qr');const shot=PNG.sync.read(await qr.screenshot());
     const decoded=jsQR(new Uint8ClampedArray(shot.data),shot.width,shot.height);
     assert.equal(decoded?.data,'https://line.me/ti/p/x_k8FjS5cQ',`Rendered QR ${width}/${variant}`);
     const overlap=await host.evaluate(h=>{let q=h.shadowRoot.querySelector('.line-qr').getBoundingClientRect(),t=h.shadowRoot.querySelector('h2').getBoundingClientRect();return q.left<t.right&&q.right>t.left&&q.top<t.bottom&&q.bottom>t.top});
     assert(!overlap,`QR overlaps heading ${width}/${variant}`);
     if(width===390&&variant==='large')await el.screenshot({path:process.env.KT_SCREENSHOT || '/tmp/KT_Final_QR_Mobile.png'});
    }
    findings.push({width,id,variant,...bounds});
   }
  }
 }
 // Restore actual portal and exercise additional consuming routes.
 await page.goto(base+'#nearby/food',{waitUntil:'domcontentloaded'});
 await page.waitForFunction(()=>document.querySelector('[data-nb-ad] .tn-campaign'));
 const nearby=await page.locator('[data-nb-ad] .tn-campaign').getAttribute('data-tn-slot');assert.equal(nearby,'nearby-food');
 await page.goto(base+'#jobs',{waitUntil:'domcontentloaded'});
 await page.waitForFunction(()=>document.querySelector('.jb-ad .tn-campaign'));
 assert.equal(await page.locator('.jb-ad .tn-campaign').getAttribute('data-tn-key'),'jobs:0');
 // Campaign switch restores legacy without changing existing items.
 await page.evaluate(()=>{TN_ADS.campaign.enabled=false;location.hash='nearby/massage'});
 await page.waitForTimeout(500);
 assert.equal(await page.evaluate(()=>TNAds.active()),false);
 assert.equal(await page.evaluate(()=>TNAds.renderSlot(TN_ADS.slots[0],'off')),null);
 assert.deepEqual(errors,[]);
 console.log(JSON.stringify({status:'PASS',base,initial,weights,localMeasured:counted,variants:findings.length,qrDecodes:12,nearby,jobs:true,pageErrors:errors,findings},null,2));
 await b.close();
})().catch(e=>{console.error(e);process.exit(1)});
