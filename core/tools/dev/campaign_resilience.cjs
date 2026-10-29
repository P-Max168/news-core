const assert=require('node:assert/strict'),fs=require('fs');const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async()=>{
let b=await chromium.launch({executablePath:process.env.CHROMIUM_EXECUTABLE || undefined,args:JSON.parse(process.env.CHROMIUM_ARGS_JSON || '["--no-sandbox"]'),headless:true});
const c=await b.newContext({viewport:{width:390,height:844},deviceScaleFactor:1});
await c.addInitScript(()=>{Math.random=()=>.94;localStorage.setItem('tnk.profile.v1',JSON.stringify({v:1,onboarded:true,persona:'pattaya',topics:['east','visa','life','weather','society'],taste:{w:{},votes:{}},ui:{},updatedAt:1}));});
let p=await c.newPage();await p.goto('http://127.0.0.1:8765/',{waitUntil:'domcontentloaded'});await p.waitForFunction(()=>document.querySelector('tn-partner-ad[data-ready="1"]'));
await p.evaluate(()=>navigator.serviceWorker.ready);await p.reload({waitUntil:'domcontentloaded'});await p.waitForFunction(()=>document.querySelector('tn-partner-ad[data-ready="1"]'));
const titles=await p.locator('.card__title,.top-card__title').allTextContents();
await c.setOffline(true);await p.reload({waitUntil:'domcontentloaded'});await p.waitForFunction(()=>document.querySelector('tn-partner-ad[data-ready="1"]'));
assert.deepEqual(await p.locator('.card__title,.top-card__title').allTextContents(),titles);assert(titles.length>0);
await c.setOffline(false);await c.close();await b.close();b=await chromium.launch({executablePath:process.env.CHROMIUM_EXECUTABLE || undefined,args:JSON.parse(process.env.CHROMIUM_ARGS_JSON || '["--no-sandbox"]'),headless:true});
// Asset failure must display the legacy dragon rather than a blank placeholder.
const fail=await b.newContext({serviceWorkers:'block'});await fail.addInitScript(()=>Math.random=()=>.94);
await fail.route('**/assets/ads/partners/creatives.json*',r=>r.abort());
p=await fail.newPage();await p.goto('http://127.0.0.1:8765/',{waitUntil:'domcontentloaded'});await p.waitForFunction(()=>document.querySelector('.tn-campaign[data-tn-fallback="creative-load"] .dm-ad'));
assert(await p.locator('.tn-campaign[data-tn-fallback]').count()>0);
const fallback=await p.evaluate(()=>TNAds.snapshot().counts.fallback);assert(fallback>0);
await fail.close();await b.close();b=await chromium.launch({executablePath:process.env.CHROMIUM_EXECUTABLE || undefined,args:JSON.parse(process.env.CHROMIUM_ARGS_JSON || '["--no-sandbox"]'),headless:true});
// Disabled campaign goes through the exact legacy renderers (including feed).
const legacy=await b.newContext({serviceWorkers:'block'});await legacy.route('**/data/ads.js',async route=>{let r=await route.fetch();let raw=await r.text(),a=JSON.parse(raw.slice(raw.indexOf('=')+1).trim().replace(/;$/,''));a.campaign.enabled=false;await route.fulfill({response:r,body:'window.TN_ADS='+JSON.stringify(a)+';'});});
p=await legacy.newPage();await p.goto('http://127.0.0.1:8765/',{waitUntil:'domcontentloaded'});await p.waitForFunction(()=>document.querySelector('.dm-ad'));assert.equal(await p.locator('.tn-campaign').count(),0);
assert.equal(await p.evaluate(()=>TNAds.active()),false);
// Global/slot disable respected by the selection layer.
assert.equal(await p.evaluate(()=>{TN_ADS.campaign.enabled=true;TN_ADS.enabled=false;return TNAds.renderSlot(TN_ADS.slots[0],'disabled')}),null);
await b.close();console.log(JSON.stringify({status:'PASS',offlineNewsTitlesPreserved:titles.length,offlinePartners:true,fallbackToDragon:fallback,legacyCampaignOff:true,globalDisabled:true},null,2));
})().catch(e=>{console.error(e);process.exit(1)});
