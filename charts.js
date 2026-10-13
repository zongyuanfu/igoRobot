const colors=['#39749a','#c77b45','#68885b','#8b70a5','#aa954b','#488e8d','#b36782'];
const $=id=>document.getElementById(id);
const left=65,right=875,top=30,bottom=212;

function plot(id,series,{min,max,duration,unit,controls,band=false}){
  const x=t=>left+t/duration*(right-left),y=v=>bottom-(v-min)/(max-min)*(bottom-top);
  let svg=band?`<rect x="${left}" y="${y(1)}" width="${right-left}" height="${y(-1)-y(1)}" fill="#f3f6f3"/>`:'';
  for(let i=0;i<=4;i++){
    const value=min+(max-min)*i/4,py=y(value);
    svg+=`<path d="M${left} ${py}H${right}" stroke="#edf0f2"/><text x="${left-9}" y="${py+4}" text-anchor="end" fill="#68717a" font-size="13">${value.toFixed(1)}</text>`;
    const t=duration*i/4,px=x(t);
    svg+=`<text x="${px}" y="${bottom+22}" text-anchor="middle" fill="#68717a" font-size="13">${t.toFixed(2)}</text>`;
  }
  if(band)for(const limit of [-1,1])svg+=`<path class="limit-line" d="M${left} ${y(limit)}H${right}" stroke="#9caaa0" stroke-dasharray="6 4"/><text x="${right-4}" y="${y(limit)-5}" text-anchor="end" fill="#7b887f" font-size="11">${limit>0?'+':''}${limit} limit</text>`;
  svg+=`<text x="${left}" y="17" fill="#68717a" font-size="13">${band?'':'rad'}</text><text x="${right}" y="254" text-anchor="end" fill="#68717a" font-size="13">Time (s)</text>`;
  colors.forEach((color,j)=>{
    if(controls){
      const vertices=controls.map(p=>`${x(p[0])},${y(p[1][j])}`).join(' ');
      svg+=`<polyline class="control-polygon" data-joint="${j+1}" points="${vertices}" stroke="${color}" stroke-width="1" stroke-dasharray="4 4" fill="none" opacity=".38"/>`;
      controls.forEach(([t,c],i)=>{svg+=`<circle cx="${x(t)}" cy="${y(c[j])}" r="2.3" fill="${i>=3&&i<=8?color:'white'}" stroke="${color}"><title>J${j+1}, C${i}: ${c[j].toFixed(3)} rad</title></circle>`;});
    }
    svg+=`<polyline class="joint-curve" data-joint="${j+1}" points="${series.map(([t,v])=>`${x(t)},${y(v[j])}`).join(' ')}" stroke="${color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" fill="none"><title>Joint ${j+1}</title></polyline>`;
  });
  svg+=`<path class="time-cursor" d="M${left} ${top}V${bottom}" stroke="#272d34" stroke-width="1" opacity=".28"/>`;
  $(id).innerHTML=svg;
}

export function drawCharts(data){
  $('joint-legend').innerHTML=colors.map((color,j)=>`<span><i style="background:${color}"></i>J${j+1}</span>`).join('');
  const values=[...data.controls.flat(),...data.joints.flat()];
  const min=Math.min(...values),max=Math.max(...values),pad=Math.max(.15,(max-min)*.07);
  const knots=[0,0,0,0,...Array.from({length:8},(_,i)=>(i+1)/9),1,1,1,1];
  const controls=data.controls.map((c,i)=>[(knots[i+1]+knots[i+2]+knots[i+3])/3*data.duration,c]);
  plot('control-chart',data.times.map((t,i)=>[t,data.joints[i]]),{min:min-pad,max:max+pad,duration:data.duration,unit:'Joint angle (rad)',controls});
  for(const kind of ['velocity','acceleration']){
    const series=data.times.map((t,i)=>[t,data[kind][i].map((v,j)=>v/data.limits[kind][j])]);
    const peak=Math.max(...series.flatMap(([,v])=>v.map(Math.abs)));
    const extent=Math.max(1.2,peak*1.15);
    plot(`${kind}-chart`,series,{min:-extent,max:extent,duration:data.duration,unit:`${kind==='velocity'?'Velocity':'Acceleration'} / limit`,band:true});
    const limits=kind==='velocity'?'J1–J4: 2.175; J5–J7: 2.610 rad/s':`All joints: ${data.limits.acceleration[0]} rad/s²`;
    $(`${kind}-note`).textContent=`Limits: ${limits}.`;
  }
}

export function updateChartTime(time,duration){
  const x=left+Math.max(0,Math.min(1,time/duration))*(right-left);
  document.querySelectorAll('.time-cursor').forEach(cursor=>cursor.setAttribute('d',`M${x} ${top}V${bottom}`));
}
