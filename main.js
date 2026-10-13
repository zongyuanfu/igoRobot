import {drawCharts,updateChartTime} from './charts.js';
const $=id=>document.getElementById(id);
const descriptions=[
  'A reach into a box-shaped enclosure. Orbit the view to inspect the arm relative to the surrounding panels.',
  'An inverted box scene with motion below the robot base. The expanded ESDF includes this lower workspace.',
  'A compact bookshelf scene. Inspect the final approach and the positions of the elbow and wrist.',
  'A thin bookshelf scene. The side view makes the shelf spacing and final arm posture easier to inspect.',
  'A cage scene with several surrounding obstacles. Turn on collision spheres to inspect the robot representation.',
  'A selected successful reach below a table. Inspect how the arm passes beneath the work surface.'
];
let cases=[], viewer, data, index=0, time=0, playing=false, last=0, frame=0, visible=true, ticket=0, initPromise;
const cache=new Map();
async function json(url){const res=await fetch(url);if(!res.ok)throw Error(`Unable to load ${url}`);return res.json();}
function setPlaying(value){playing=value;$('play').innerHTML=value?'Ⅱ <span>Pause</span>':'▶ <span>Play</span>';$('play').setAttribute('aria-label',value?'Pause trajectory':'Play trajectory');last=0;schedule();}
function schedule(){if(playing && visible && !document.hidden && !frame)frame=requestAnimationFrame(tick);}
function tick(now){frame=0;if(!playing || !visible || document.hidden)return;if(last)time=Math.min(data.duration,time+(now-last)/1000*Number($('speed').value));last=now;setTime(time);if(time>=data.duration)setPlaying(false);else schedule();}
function setTime(value){time=Math.max(0,Math.min(data.duration,value));viewer?.setTime(time);$('timeline').value=time;$('clock').textContent=`${time.toFixed(2)} / ${data.duration.toFixed(2)} s`;updateChartTime(time,data.duration);}
function error(message){$('viewer-status').textContent=message;$('viewer-poster').hidden=false;const canvas=$('viewport').querySelector('canvas');if(canvas)canvas.style.visibility='hidden';$('play').disabled=true;$('timeline').disabled=true;setPlaying(false);}
async function initViewer(){
  if(!initPromise)initPromise=(async()=>{const {TrajectoryViewer}=await import('./viewer.js');const v=new TrajectoryViewer($('viewport'));await v.init();return v;})();
  return initPromise;
}
async function selectScene(i){
  index=i;const request=++ticket;const item=cases[i];setPlaying(false);
  $('play').disabled=true;$('timeline').disabled=true;
  $('scene-title').textContent=item.title;$('case-label').textContent=`MB / ${String(item.index).padStart(4,'0')}`;
  $('scene-description').textContent=descriptions[i];
  $('case-optimize').innerHTML=`${item.optimize_ms.toFixed(1)} <small>ms</small>`;
  $('case-duration').innerHTML=`${item.duration.toFixed(3)} <small>s</small>`;
  $('manifest-link').href=`data/${item.id}-manifest.json`;
  $('viewer-poster').src=`assets/preview-${item.id}.webp`;$('viewer-poster').hidden=false;
  $('viewer-status').textContent='Loading the robot and trajectory…';
  document.querySelectorAll('.scene-card').forEach((b,n)=>b.setAttribute('aria-pressed',String(n===i)));
  try{
    const [v,d]=await Promise.all([initViewer(),cache.has(item.id)?cache.get(item.id):json(`demos/${item.id}.json`)]);
    cache.set(item.id,d);if(request!==ticket)return;
    viewer=v;data=d;viewer.load(data);viewer.setLayers($('show-path').checked,$('show-spheres').checked);
    $('timeline').max=data.duration;$('timeline').disabled=false;$('play').disabled=false;
    $('viewer-status').textContent='';$('viewer-poster').hidden=true;viewer.renderer.domElement.style.visibility='visible';setTime(0);drawCharts(data);updateChartTime(0,data.duration);
    $('viewport').dataset.ready=item.id;
  }catch(err){if(request===ticket){console.error(err);error('The interactive view is unavailable. You can still inspect the preview and download the case data.');}}
}
$('play').addEventListener('click',()=>{if(time>=data.duration)setTime(0);setPlaying(!playing);});
$('timeline').addEventListener('input',e=>{setPlaying(false);setTime(Number(e.target.value));});
$('reset-view').addEventListener('click',()=>viewer?.reset());
for(const id of ['show-path','show-spheres'])$(id).addEventListener('change',()=>{viewer?.setLayers($('show-path').checked,$('show-spheres').checked);document.querySelector('.view-legend>span').hidden=!$('show-path').checked;});
$('show-controls').addEventListener('change',()=>{$('control-panel').hidden=!$('show-controls').checked;if(data)updateChartTime(time,data.duration);});
$('viewport').addEventListener('viewer-failed',()=>error('The 3D context was lost. Reload this page to restore interaction; the preview remains available.'));
document.addEventListener('visibilitychange',()=>{last=0;schedule();});
new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;last=0;schedule();},{threshold:0}).observe($('viewport'));
async function start(){
  cases=await json('data/cases.json');
  cases.forEach((item,i)=>{
    const button=document.createElement('button');button.className='scene-card';button.type='button';button.setAttribute('aria-pressed','false');button.setAttribute('aria-label',`${item.title}, successful case ${item.index}`);
    button.innerHTML=`<img src="assets/preview-${item.id}.webp" alt="" width="240" height="160"><span class="card-label"><b>${String(i+1).padStart(2,'0')}</b>${item.title}</span>`;
    button.addEventListener('click',()=>selectScene(i));$('scene-picker').append(button);
  });
  document.querySelectorAll('[data-case]').forEach(a=>a.addEventListener('click',()=>selectScene(Number(a.dataset.case))));
  // Delay the heavy robot meshes until the demo approaches the viewport.
  const observer=new IntersectionObserver(entries=>{if(entries[0].isIntersecting){observer.disconnect();selectScene(index);}},{rootMargin:'300px'});observer.observe($('demos'));
}
start().catch(err=>{console.error(err);error('Demonstration data could not be loaded. Please reload the page or use the download links.');});

const teaser=$('teaser-video'),motionPreference=matchMedia('(prefers-reduced-motion: reduce)');
let teaserPaused=motionPreference.matches;
function updateTeaserButton(){const paused=teaser.paused;$('teaser-toggle').textContent=paused?'▶':'Ⅱ';$('teaser-toggle').setAttribute('aria-label',paused?'Play teaser animation':'Pause teaser animation');}
teaser.addEventListener('play',updateTeaserButton);teaser.addEventListener('pause',updateTeaserButton);
$('teaser-toggle').addEventListener('click',()=>{teaserPaused=!teaser.paused?true:false;if(teaser.paused)teaser.play().catch(()=>{});else teaser.pause();});
new IntersectionObserver(entries=>{if(entries[0].isIntersecting&&!teaserPaused)teaser.play().catch(()=>{});else teaser.pause();}).observe(teaser);
motionPreference.addEventListener('change',e=>{if(e.matches){teaserPaused=true;teaser.pause();}});

// Read-only state for the local browser audit; no planner or network service runs here.
export function inspect(){return {viewer,data,index,time,playing};}
