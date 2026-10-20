// Run with PLANIGO_PLAYWRIGHT pointing to an installed Playwright package.
import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
import path from 'node:path';
const require=createRequire(import.meta.url);
const {chromium}=require(process.env.PLANIGO_PLAYWRIGHT || 'playwright');
const root=path.resolve(import.meta.dirname,'..');
const base=process.env.PLANIGO_URL || 'http://127.0.0.1:8765/';
const previews=process.argv.includes('--previews');
const browser=await chromium.launch({headless:true,executablePath:process.env.PLANIGO_CHROMIUM,args:['--no-sandbox','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
const page=await browser.newPage({viewport:{width:1440,height:1050},deviceScaleFactor:1});
const errors=[];page.on('pageerror',e=>errors.push(e.message));
page.on('response',r=>{if(r.status()>=400 && !(previews&&r.url().includes('preview-')))errors.push(`${r.status()} ${r.url()}`);});
try{
  await page.goto(base);await page.locator('#demos').scrollIntoViewIfNeeded();
  await page.waitForFunction(()=>document.querySelector('#viewport').dataset.ready,{timeout:60000});
  const cases=JSON.parse(await fs.readFile(path.join(root,'data/cases.json')));
  if(await page.locator('#show-controls').isChecked() || await page.locator('#control-panel').isVisible())throw Error('Dynamics must be hidden initially');
  if(await page.locator('#results details[open]').count())throw Error('Result details must be collapsed initially');
  let maxFKError=0,maxSphereError=0;
  for(let i=0;i<6;i++){
    await page.locator('.scene-card').nth(i).click();
    await page.waitForFunction(id=>document.querySelector('#viewport').dataset.ready===id,cases[i].id);
    const parity=await page.evaluate(async()=>{
      const {inspect}=await import('./main.js');const {viewer,data}=inspect();let error=0;
      for(const frame of [0,Math.floor(data.times.length/2),data.times.length-1]){
        viewer.setTime(data.times[frame]);
        viewer.currentMatrices.forEach((m,link)=>{const ref=data.poses[frame][link];for(let r=0;r<4;r++)for(let c=0;c<4;c++)error=Math.max(error,Math.abs(m.elements[c*4+r]-ref[r][c]));});
      }return error;
    });maxFKError=Math.max(maxFKError,parity);
    if(parity>2e-5)throw Error(`FK mismatch: ${parity}`);
    const sphereError=await page.evaluate(async()=>{
      const {viewer,data}=(await import('./main.js')).inspect();
      if(viewer.links.length!==11 || viewer.sphereMeshes.length!==61)throw Error('Expected 11 links and 61 spheres');
      let error=0;
      for(const reference of data.sphere_reference){
        viewer.setTime(data.times[reference.frame]);
        viewer.sphereMeshes.forEach((mesh,i)=>{
          mesh.position.toArray().forEach((v,k)=>{error=Math.max(error,Math.abs(v-reference.centers[i][k]));});
          if(Math.abs(mesh.scale.x-viewer.model.radii[i])>1e-7)throw Error('Sphere radius mismatch');
        });
      }
      return error;
    });
    maxSphereError=Math.max(maxSphereError,sphereError);
    if(sphereError>2e-5)throw Error(`Collision sphere mismatch: ${sphereError}`);

    await page.locator('#timeline').evaluate((el,t)=>{el.value=t;el.dispatchEvent(new Event('input',{bubbles:true}));},cases[i].duration*.72);
    if(previews){
      await page.evaluate(async()=>{const {inspect}=await import('./main.js');inspect().viewer.render();});
      // Read the render buffer directly: no UI labels, image distortion or screenshot overlays.
      const encoded=await page.evaluate(async()=>{const {viewer}=(await import('./main.js')).inspect();viewer.render();return viewer.renderer.domElement.toDataURL('image/webp',.9).split(',')[1];});
      await fs.writeFile(path.join(root,`assets/preview-${cases[i].id}.webp`),Buffer.from(encoded,'base64'));
    }
    await page.locator('#show-path').uncheck();await page.locator('#show-spheres').check();await page.locator('#show-controls').check();
    if(await page.locator('#control-chart .joint-curve').count()!==7)throw Error('Expected seven joint curves');
    if(await page.locator('#control-chart .control-polygon').count()!==7)throw Error('Expected seven control polygons');
    for(const id of ['velocity-chart','acceleration-chart']){
      if(await page.locator(`#${id} .joint-curve`).count()!==7 || await page.locator(`#${id} .limit-line`).count()!==2)throw Error('Dynamics curves or limits missing');
    }
    const layers=await page.evaluate(async()=>{const {viewer}= (await import('./main.js')).inspect();return !viewer.path.visible&&viewer.spheres.visible&&!document.querySelector('#control-panel').hidden;});
    if(!layers)throw Error('Layer toggles failed');
    if(previews && i===0)await page.locator('#viewport').screenshot({path:'/tmp/planigo-home-collision-model.png'});
    await page.locator('#show-path').check();await page.locator('#show-spheres').uncheck();await page.locator('#show-controls').uncheck();
    await page.locator('#timeline').evaluate(el=>{el.value=0;el.dispatchEvent(new Event('input'));});
    await page.locator('#play').click();await page.locator('#viewport').scrollIntoViewIfNeeded();
    await page.waitForFunction(()=>Number(document.querySelector('#timeline').value)>0,null,{timeout:5000});
    const progress=await page.locator('#timeline').inputValue();if(Number(progress)<=0)throw Error('Playback did not advance');
    await page.locator('#play').click();
    const before=await page.evaluate(async()=> (await import('./main.js')).inspect().viewer.camera.position.toArray());
    const canvas=page.locator('#viewport canvas');await canvas.focus();await page.keyboard.press('ArrowLeft');
    const after=await page.evaluate(async()=> (await import('./main.js')).inspect().viewer.camera.position.toArray());
    if(JSON.stringify(before)===JSON.stringify(after))throw Error('Keyboard orbit failed');
    await page.locator('#reset-view').click();
  }
  if(process.argv.includes('--teaser')){
    await page.locator('.scene-card').nth(4).click();await page.waitForFunction(()=>document.querySelector('#viewport').dataset.ready==='cage_panda-90');
    const recording=await page.evaluate(async()=>{
      const {viewer,data}=(await import('./main.js')).inspect();
      const canvas=viewer.renderer.domElement,stream=canvas.captureStream(30);
      const recorder=new MediaRecorder(stream,{mimeType:'video/webm;codecs=vp9',videoBitsPerSecond:1400000});
      const parts=[];recorder.ondataavailable=e=>parts.push(e.data);
      const done=new Promise(resolve=>recorder.onstop=async()=>{const buffer=await new Blob(parts).arrayBuffer();resolve(Array.from(new Uint8Array(buffer)));});
      viewer.setTime(0);recorder.start();
      const start=performance.now();
      await new Promise(resolve=>{function render(now){const t=(now-start)/1000;viewer.setTime(Math.min(t,data.duration));if(t<data.duration+.6)requestAnimationFrame(render);else resolve();}requestAnimationFrame(render);});
      recorder.stop();stream.getTracks().forEach(t=>t.stop());return done;
    });
    await fs.writeFile(path.join(root,'assets/teaser.webm'),Buffer.from(recording));
  }
  if(previews)await page.reload();
  await page.locator('#demos').scrollIntoViewIfNeeded();await page.waitForFunction(()=>document.querySelector('#viewport').dataset.ready);
  await page.locator('.scene-card').nth(2).click();await page.waitForFunction(()=>document.querySelector('#viewport').dataset.ready==='bookshelf_small_panda-88');
  await page.locator('#timeline').evaluate(el=>{el.value=Number(el.max)*.72;el.dispatchEvent(new Event('input'));});
  await page.locator('#show-controls').check();
  await page.evaluate(()=>scrollTo(0,0));await page.screenshot({path:'/tmp/planigo-home-desktop.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});await page.evaluate(()=>scrollTo(0,0));
  if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Mobile horizontal overflow');
  await page.screenshot({path:'/tmp/planigo-home-mobile.png',fullPage:true});
  await page.locator('#demos').scrollIntoViewIfNeeded();await page.locator('#play').click();await page.waitForTimeout(150);await page.locator('#play').click();
  await page.locator('.scene-card').nth(5).click();await page.waitForFunction(()=>document.querySelector('#viewport').dataset.ready==='table_under_pick_panda-14');
  // Race case switches; the last choice must win, even if a fetch completes late.
  await page.evaluate(()=>{const b=document.querySelectorAll('.scene-card');b[1].click();b[4].click();b[0].click();});
  await page.waitForFunction(()=>document.querySelector('#viewport').dataset.ready==='box_panda-57');
  for(const width of [320,768]){await page.setViewportSize({width,height:844});if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error(`Overflow at ${width}px`);}
  const reduced=await browser.newPage({reducedMotion:'reduce'});
  await reduced.goto(base);await reduced.waitForTimeout(200);
  if(!await reduced.locator('#teaser-video').evaluate(v=>v.paused))throw Error('Reduced motion ignored');
  await reduced.close();
  const fallback=await browser.newPage();
  await fallback.addInitScript(()=>{const original=HTMLCanvasElement.prototype.getContext;HTMLCanvasElement.prototype.getContext=function(type,...args){return type.startsWith('webgl')?null:original.call(this,type,...args);};});
  await fallback.goto(base);await fallback.locator('#demos').scrollIntoViewIfNeeded();
  await fallback.waitForFunction(()=>document.querySelector('#viewer-status').textContent.includes('unavailable'));
  if(!await fallback.locator('#viewer-poster').isVisible())throw Error('Missing WebGL fallback');
  await fallback.close();
  const nojs=await browser.newPage({javaScriptEnabled:false});await nojs.goto(base);
  const reports=await Promise.all(['comparison.json','mpinets.json'].map(async name=>JSON.parse(await fs.readFile(path.join(root,'data',name)))));
  const expectedGroups=reports.reduce((n,r)=>n+Object.keys(r.summaries.planigo.groups).length,0);
  if(await nojs.locator('.results-table tbody tr').count()!==expectedGroups || await nojs.locator('.comparison-table tbody tr').count()!==4)throw Error('Static results unavailable without JS');
  await nojs.close();
  if(errors.length)throw Error(errors.join('\n'));
  console.log(JSON.stringify({scenes:6,maxFKError,maxSphereError,widths:[320,390,768,1440],errors,previews,checks:['load','physical-time scrubbing','play/pause','layers','7D controls','keyboard orbit','camera reset','mobile layout','rapid selection','reduced motion','WebGL fallback','no-JS results']},null,2));
}finally{await browser.close();}
