import { chromium } from 'playwright-core';
import assert from 'node:assert/strict';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { mkdtemp, copyFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
const temp = await mkdtemp(resolve(tmpdir(),'校园漫游界面-'));
const single = resolve(temp,'校园.html');
await copyFile('dist/校园漫游.html',single);
const browser = await chromium.launch({channel:'chrome', headless:true,args:['--enable-unsafe-swiftshader']});
const problems = [];
async function openGame(options) {
  const context = await browser.newContext({offline:true,acceptDownloads:true,...options});
  const page = await context.newPage();
  page.setDefaultTimeout(90000);
  page.on('pageerror',e=>problems.push(e.message));
  page.on('request',r=>{if(!['file:','data:','blob:'].includes(new URL(r.url()).protocol))problems.push(r.url());});
  await page.goto(pathToFileURL(single).href,{timeout:90000});
  await page.waitForFunction(()=>!!window.game,null,{timeout:60000});
  await page.getByRole('button',{name:'上衣：珊瑚粉',exact:true}).click();
  await page.click('#start');
  await page.waitForFunction(()=> game.started && game.near?.id==='library');
  return {context,page};
}
try {
  const {page,context} = await openGame({viewport:{width:1280,height:800},deviceScaleFactor:0.8});
  
  await page.keyboard.press('e');
  assert.equal(await page.locator('#storyName').innerText(),'图书馆');
  await page.keyboard.press('Escape');
  assert.match(await page.locator('#task').innerText(),/风云剧场/);
  const before=await page.locator('#miniMap small').innerText();
  await page.keyboard.down('s');
  await page.waitForFunction(pos=>document.querySelector('#miniMap small').textContent!==pos,before);
  await page.keyboard.up('s');
  await page.click('#trackTask');
  await page.waitForSelector('#walkingGuide:visible');
  assert.equal(await page.locator('#walkingGuide strong').innerText(),'风云剧场');
  await page.click('#miniMap');
  const placeCount=await page.evaluate(()=>game.playable.length);
  assert.equal(await page.locator('#placeList button').count(),placeCount);
  await page.click('#placeSearch');await page.keyboard.type('wcm');
  assert.equal(await page.locator('#placeSearch').inputValue(),'wcm');
  assert.equal(await page.locator('#emptyPlaces').isVisible(),true);
  assert.equal(await page.evaluate(()=>game.viewState.overview),true);
  await page.fill('#placeSearch','');
  await page.click('[data-filter=unread]');
  assert.equal(await page.locator('#placeList button').count(),placeCount-1);
  await page.getByRole('button',{name:/气象楼.*米|气象楼.*公里/}).click();
  await page.waitForFunction(()=>game.viewState.mapZoom===.21);
  await page.waitForSelector('#selectedPin:visible');
  assert.equal(await page.locator('#selectedPin').innerText(),'气象楼');
  
  await page.click('#walkTo');
  await page.waitForSelector('#walkingGuide:visible');
  assert.equal(await page.locator('#walkingGuide strong').innerText(),'气象楼');
  await page.getByRole('button',{name:'结束步行指引'}).click();
  await page.waitForSelector('#walkingGuide',{state:'hidden'});
  await page.keyboard.press('m');await page.fill('#placeSearch','风云');
  await page.click('#jumpTo');await page.waitForFunction(()=>game.near?.id==='yard');
  const downloaded=page.waitForEvent('download');await page.click('#trackTask');
  assert.match((await downloaded).suggestedFilename(),/png$/);
  await page.click('#trackTask');
  assert.equal(await page.locator('[data-filter=unread]').getAttribute('aria-pressed'),'true');
  await page.click('#closeMap');
  await page.keyboard.press('c');assert.equal(await page.evaluate(()=>game.viewState.firstPerson),true);
  await page.click('#shuttleMenu');assert.equal(await page.locator('.stationList button').count(),10);
  await page.locator('.stationList button').first().click();
  await page.waitForSelector('#shuttleAction:visible');
  console.log('Desktop: outfit, proximity reading, task, movement, route and cancellation, landmark list, unread filtering, safe text entry, teleport, photograph and ten bus stops OK.');
  await context.close();
  const mobile=await openGame({viewport:{width:390,height:844},hasTouch:true,isMobile:true,deviceScaleFactor:1});
  const m=mobile.page;
  await m.click('#miniMap');await m.fill('#placeSearch','信息科技大楼');
  assert.equal(await m.locator('#placeList button').count(),1);
  await m.locator('#placeList button').first().click();
  assert.match(await m.locator('#placeName').innerText(),/临江楼/);
  await m.click('#walkTo');await m.waitForSelector('#walkingGuide:visible');
  const regions=await m.evaluate(()=>['#walkingGuide','#miniMap','#joystick','#taskCard','#contextActions','header'].map(s=>{const r=document.querySelector(s).getBoundingClientRect();return [s,r.x,r.y,r.right,r.bottom]}));
  for(const [,x,y,r,b] of regions){assert(x>=0&&y>=0&&r<=391&&b<=845,JSON.stringify(regions));}
  const g=regions[0], h=regions.at(-1);assert(g[1]>=h[3] || g[2]>=h[4],JSON.stringify(regions));
  await m.click('#interact');await m.click('#closeStory');
  await m.click('#miniMap');await m.click('#zoomIn');assert((await m.evaluate(()=>game.viewState.mapZoom))<.21);
  
  await mobile.context.close();
  assert.deepEqual(problems,[]);
  console.log('Portrait: local game, touch controls, alias search, landmark selection, route, proximity action, map zoom and panel bounds OK. No JS errors or external requests.');
} finally {await browser.close();await rm(temp,{recursive:true,force:true});}
