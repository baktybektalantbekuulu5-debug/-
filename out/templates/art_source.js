// 2D cartoon templates drawn as SVG. Style: thick black outlines, flat colors, soft cel shading.
const INK='#15141c',SW=5;
const defs=`
<defs>
<linearGradient id="gW" x1="0" x2="1"><stop offset="0" stop-color="#ffffff"/><stop offset=".6" stop-color="#f1f4f9"/><stop offset="1" stop-color="#c9d1e0"/></linearGradient>
<linearGradient id="gO" x1="0" x2="1"><stop offset="0" stop-color="#ff9a3c"/><stop offset=".6" stop-color="#f27a1c"/><stop offset="1" stop-color="#c85c10"/></linearGradient>
<linearGradient id="gB" x1="0" x2="1"><stop offset="0" stop-color="#5aa0e6"/><stop offset="1" stop-color="#2e5fb0"/></linearGradient>
<linearGradient id="gT" x1="0" x2="1"><stop offset="0" stop-color="#7fd6cf"/><stop offset="1" stop-color="#2f8f8f"/></linearGradient>
<linearGradient id="gG" x1="0" x2="1"><stop offset="0" stop-color="#9aa3b0"/><stop offset="1" stop-color="#5c6573"/></linearGradient>
<radialGradient id="gHelm" cx=".35" cy=".3" r=".8"><stop offset="0" stop-color="#ffffff" stop-opacity=".18"/><stop offset=".6" stop-color="#cfe9ff" stop-opacity=".08"/><stop offset="1" stop-color="#8fbfe8" stop-opacity=".28"/></radialGradient>
<linearGradient id="gSky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#1f1646"/><stop offset=".55" stop-color="#4a2f7a"/><stop offset="1" stop-color="#b86b8a"/></linearGradient>
<linearGradient id="gSand" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#e8a98a"/><stop offset="1" stop-color="#c47a7a"/></linearGradient>
<linearGradient id="gDune" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#f4bf9a"/><stop offset="1" stop-color="#b8688a"/></linearGradient>
<radialGradient id="gMoon" cx=".4" cy=".35" r=".8"><stop offset="0" stop-color="#ffe9a0"/><stop offset="1" stop-color="#d9a940"/></radialGradient>
<linearGradient id="gUV" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#d8a0ff" stop-opacity=".95"/><stop offset="1" stop-color="#8a3dff" stop-opacity=".25"/></linearGradient>
<linearGradient id="gWall" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#4a6a8a"/><stop offset="1" stop-color="#7a95ad"/></linearGradient>
<linearGradient id="gFloor" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#8fa4b8"/><stop offset="1" stop-color="#6c8399"/></linearGradient>
<filter id="glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="8"/></filter>
<filter id="soft" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="3"/></filter>
</defs>`;
const st=(f,w=SW)=>`fill="${f}" stroke="${INK}" stroke-width="${w}" stroke-linejoin="round" stroke-linecap="round"`;
const rect=(x,y,w,h,r,f,w2=SW)=>`<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${r}" ${st(f,w2)}/>`;
const circ=(x,y,r,f,w=SW)=>`<circle cx="${x}" cy="${y}" r="${r}" ${st(f,w)}/>`;
const ell=(x,y,rx,ry,f,w=SW)=>`<ellipse cx="${x}" cy="${y}" rx="${rx}" ry="${ry}" ${st(f,w)}/>`;
const path=(d,f,w=SW)=>`<path d="${d}" ${st(f,w)}/>`;

// ---------- Timur ----------
function boot(){return `${path('M-24 -6 Q-26 28 -22 40 L26 40 Q32 30 24 -6 Z','url(#gW)')}${rect(-25,14,50,9,3,'#d93a3a',4)}${rect(-27,36,56,12,5,'url(#gG)',4)}`}
function leg(sx,a1,a2){return `<g transform="translate(${sx*28},-146)${sx>0?' scale(-1,1)':''}"><g transform="rotate(${a1})">
 ${rect(-22,-6,44,68,16,'url(#gW)')}${rect(-4,6,8,48,3,'url(#gO)',3)}
 <g transform="translate(0,62) rotate(${a2})">${rect(-21,-8,42,50,15,'url(#gW)')}${rect(-20,-14,40,24,9,'url(#gG)',4)}<g transform="translate(0,40)">${boot()}</g></g></g></g>`}
function arm(sx,a1,a2,hold){return `<g transform="translate(${sx*66},-322)${sx>0?' scale(-1,1)':''}"><g transform="rotate(${a1})">
 ${rect(-17,-8,34,66,13,'url(#gW)')}${rect(-17,6,34,12,4,'url(#gO)',3)}
 <g transform="translate(0,58) rotate(${a2})">${rect(-16,-6,32,56,12,'url(#gW)')}${rect(-17,36,34,14,5,'url(#gB)',4)}${sx<0?`<g filter="url(#glow)"><rect x="-15" y="32" width="30" height="8" fill="#37f0ff"/></g>${rect(-16,33,32,8,3,'#4ff4ff',3)}`:''}${circ(0,62,17,'url(#gG)')}${hold||''}</g></g></g>`}
function tank(){return `<g transform="translate(88,-300)">${rect(-26,-56,52,150,22,'url(#gT)')}${rect(-14,-48,12,120,5,'rgba(255,255,255,.5)',0)}${rect(-8,-70,16,20,5,'#c9ced6',4)}</g>
<g transform="translate(-4,0)">${path('M60 -260 Q108 -250 100 -218','none',7)}${path('M60 -260 Q108 -250 100 -218','none',3).replace(INK,'#4aa0e6')}</g>`}
function torso(){return `${path('M-62 -330 Q0 -352 62 -330 L56 -196 Q0 -178 -56 -196 Z','url(#gW)')}
${path('M-62 -330 L-56 -196 L-34 -192 L-40 -326 Z','url(#gO)',4)}${path('M62 -330 L56 -196 L34 -192 L40 -326 Z','url(#gO)',4)}
${path('M-30 -318 Q0 -300 30 -318','none',6).replace(INK,'#2e5fb0')}${path('M-34 -222 Q0 -206 34 -222','none',6).replace(INK,'#2e5fb0')}
${circ(0,-282,22,'#eef3fa')}${circ(0,-282,15,'#2f9aa5',4)}${circ(0,-282,6,'#fff',3)}
${path('M-22 -252 Q-30 -230 -18 -214','none',6).replace(INK,'#4aa0e6')}${path('M22 -252 Q30 -230 18 -214','none',6).replace(INK,'#4aa0e6')}`}
function head(face,spiky=1){
 const eyes={
  smile:`${ell(-20,-398,13,15,'#fff',4)}${ell(20,-398,13,15,'#fff',4)}${circ(-18,-396,6,INK,0)}${circ(22,-396,6,INK,0)}${circ(-16,-399,2,'#fff',0)}${circ(24,-399,2,'#fff',0)}`,
  scared:`${ell(-20,-398,16,19,'#fff',4)}${ell(20,-398,16,19,'#fff',4)}${circ(-20,-397,3.5,INK,0)}${circ(20,-397,3.5,INK,0)}`,
  grumpy:`${ell(-20,-396,13,10,'#fff',4)}${ell(20,-396,13,10,'#fff',4)}${circ(-20,-394,5,INK,0)}${circ(20,-394,5,INK,0)}`,
  joy:`${path('M-34 -394 Q-20 -410 -6 -394','none',5)}${path('M6 -394 Q20 -410 34 -394','none',5)}`,
  wink:`${ell(-20,-398,13,15,'#fff',4)}${circ(-18,-396,6,INK,0)}${path('M8 -396 Q20 -406 32 -396','none',5)}`}[face];
 const brows={smile:`${path('M-34 -420 Q-20 -428 -6 -420','none',5)}${path('M6 -420 Q20 -428 34 -420','none',5)}`,
  scared:`${path('M-34 -426 Q-20 -442 -6 -424','none',5)}${path('M6 -424 Q20 -442 34 -426','none',5)}`,
  grumpy:`${path('M-34 -414 L-6 -408','none',6)}${path('M6 -408 L34 -414','none',6)}`,joy:'',wink:`${path('M-34 -420 Q-20 -428 -6 -420','none',5)}${path('M8 -418 Q20 -426 32 -420','none',5)}`}[face];
 const mouth={smile:`${path('M-16 -366 Q0 -352 16 -366','#fff',4)}`,scared:`${ell(0,-362,11,14,'#7a1f2b',4)}`,grumpy:`${path('M-14 -362 Q0 -370 14 -362','none',5)}`,joy:`${path('M-20 -368 Q0 -346 20 -368 Z','#fff',4)}`,wink:`${path('M-18 -368 Q2 -348 20 -366 Z','#fff',4)}`}[face];
 return `${circ(0,-396,58,'#f2c29c')}${ell(-34,-376,9,6,'rgba(255,120,120,.45)',0)}${ell(34,-376,9,6,'rgba(255,120,120,.45)',0)}${eyes}${brows}${mouth}
 ${path('M-62 -396 Q-70 -452 -34 -458 L-30 -478 L-14 -460 L2 -486 L14 -462 L36 -480 L40 -456 Q70 -440 62 -392 Q56 -426 30 -434 Q0 -420 -34 -430 Q-56 -420 -62 -396 Z','#17151d',4)}`}
function helmet(){return `<circle cx="0" cy="-400" r="84" fill="url(#gHelm)" stroke="${INK}" stroke-width="5"/>
<path d="M-60 -444 Q-44 -468 -14 -472" fill="none" stroke="#fff" stroke-width="7" stroke-linecap="round" opacity=".9"/>
<ellipse cx="0" cy="-330" rx="60" ry="14" ${st('url(#gB)',5)}/>`}
function timur(o={}){const {x=0,y=0,s=1,face='smile',aL=[8,6],aR=[8,6],lL=[6,0],lR=[6,0],rot=0,holdR='',holdL='',flip=false,shadow=true,bodyDy=0}=o;
 return `<g transform="translate(${x},${y}) scale(${flip?-s:s},${s}) rotate(${rot})">
 ${shadow?`<ellipse cx="0" cy="8" rx="95" ry="14" fill="rgba(20,10,40,.28)"/>`:''}
 ${leg(-1,...lL)}${leg(1,...lR)}<g transform="translate(0,46)">${tank()}${torso()}${arm(1,...aR,holdR)}${arm(-1,...aL,holdL)}
 <g transform="translate(0,${bodyDy-330}) scale(1.14) translate(0,330)">${head(face)}${helmet()}</g></g></g>`}

// ---------- Zara ----------
function zara(o={}){const {x=0,y=0,s=1}=o;
 return `<g transform="translate(${x},${y}) scale(${s})"><ellipse cx="0" cy="48" rx="80" ry="12" fill="rgba(20,10,40,.25)"/>
 ${rect(-36,-190,30,200,10,'#1f2a4a')}${rect(6,-190,30,200,10,'#1f2a4a')}${rect(-44,28,44,22,10,'#59606b',4)}${rect(2,28,44,22,10,'#59606b',4)}
 ${path('M-64 -330 Q0 -352 64 -330 L74 -120 Q0 -100 -74 -120 Z','#f6f8fc')}${path('M-26 -330 L0 -200 L26 -330 Q0 -312 -26 -330','#2d6b45',4)}
 ${path('M-64 -330 L-74 -120 L-50 -116 L-34 -330Z','#dfe5ee',4)}${path('M64 -330 L74 -120 L50 -116 L34 -330Z','#dfe5ee',4)}
 <g transform="translate(-76,-318) rotate(10)">${rect(-17,-6,34,100,13,'#f6f8fc')}${circ(0,100,15,'#f0c4a0')}</g>
 <g transform="translate(76,-318) rotate(-45)">${rect(-17,-6,34,96,13,'#f6f8fc')}<g transform="translate(0,92) rotate(-40)">${circ(0,10,15,'#f0c4a0')}${rect(8,-18,36,42,8,'#efe3c9',4)}${path('M44 -6 Q60 0 44 14','none',4)}${path('M20 -28 Q16 -44 24 -56','none',4).replace(INK,'#bdbdbd')}</g></g>
 ${circ(0,-392,58,'#f2c9a4')}
 ${path('M-66 -392 Q-80 -470 -20 -476 Q40 -490 66 -440 Q82 -400 60 -352 Q70 -400 40 -430 Q0 -418 -30 -430 Q-56 -410 -58 -352 Q-76 -370 -66 -392 Z','#a9aeb8',4)}
 ${circ(-22,-392,19,'rgba(255,255,255,.5)',5)}${circ(22,-392,19,'rgba(255,255,255,.5)',5)}${path('M-3 -392 L3 -392','none',4)}${circ(-22,-392,5,INK,0)}${circ(22,-392,5,INK,0)}
 ${path('M-34 -418 Q-22 -424 -10 -418','none',4)}${path('M10 -420 Q22 -430 34 -420','none',4)}${path('M-14 -362 Q4 -352 18 -364','none',4)}</g>`}

// ---------- NOVA ----------
function nova(o={}){const {x=0,y=0,s=1,red=false}=o;const eye=red?'#ff3b3b':'#47d3ff',glow=red?'rgba(255,60,60,.55)':'rgba(70,220,255,.55)';
 return `<g transform="translate(${x},${y}) scale(${s})"><ellipse cx="0" cy="130" rx="90" ry="16" fill="${glow}" filter="url(#soft)"/>
 ${circ(0,0,100,'url(#gW)')}${path('M-90 -40 Q-60 -90 -20 -98','none',3).replace(INK,'#9aa5b5')}${path('M90 -30 Q74 30 40 80','none',3).replace(INK,'#9aa5b5')}${path('M-84 20 Q-60 70 -10 98','none',3).replace(INK,'#9aa5b5')}
 ${circ(0,4,62,'#9aa3b0')}${circ(0,4,54,'#15181f')}<circle cx="0" cy="4" r="24" fill="${eye}" filter="url(#soft)"/>${circ(0,4,20,eye,3)}${circ(-6,-2,6,'#fff',0)}
 ${path('M0 -100 L0 -130','none',6)}${circ(0,-138,9,red?'#ff4a4a':'#ff77d8',4)}</g>`}

// ---------- Scorpion ----------
function scorpion(o={}){const {x=0,y=0,s=1,glow=false,flip=false,baby=false}=o;
 const body=glow?'#3aa6c8':'#3a2e66',spots=glow?'#c9fffb':'#42e8d8',claw=glow?'#6ff0e4':'#4a3a80';
 const tailPts=[[170,-70],[200,-130],[205,-200],[170,-250],[120,-262],[88,-236]];
 return `<g transform="translate(${x},${y}) scale(${flip?-s:s},${s})"><ellipse cx="20" cy="42" rx="170" ry="16" fill="rgba(20,10,40,.25)"/>
 ${[-110,-60,-10,40].map((lx,i)=>path(`M${lx} 0 L${lx-20+i*6} 36 L${lx-14+i*6} 46`,'none',16).replace(INK,body)+path(`M${lx} 0 L${lx-20+i*6} 36 L${lx-14+i*6} 46`,'none',6).replace(INK,INK)).join('')}
 <path d="M150 -40 C270 -50 290 -200 190 -250 C140 -274 96 -252 84 -222" fill="none" stroke="${INK}" stroke-width="58" stroke-linecap="round"/>
 <path d="M150 -40 C270 -50 290 -200 190 -250 C140 -274 96 -252 84 -222" fill="none" stroke="${body}" stroke-width="46" stroke-linecap="round"/>
 ${[[236,-96],[262,-150],[236,-216],[176,-252],[120,-258]].map(p=>`<ellipse cx="${p[0]}" cy="${p[1]}" rx="22" ry="12" fill="none" stroke="rgba(0,0,0,.35)" stroke-width="3" transform="rotate(${p[0]>200?70:20} ${p[0]} ${p[1]})"/>`).join('')}
 ${path('M70 -240 Q60 -204 84 -186 Q98 -214 100 -236 Z','#ffd36b',4)}
 ${ell(20,-20,150,70,body)}${ell(20,-40,120,36,'rgba(255,255,255,.12)',0)}
 ${[[-70,-30],[-20,-50],[30,-40],[80,-24],[0,-10],[-50,-4]].map(p=>circ(p[0],p[1],7,spots,3)).join('')}
 ${[170,140].map((p,i)=>'').join('')}
 ${[[-120,-22,-190,-84,-150],[-116,18,-196,22,-170]].map(([x,y,cx,cy,_],i)=>`<path d="M${x} ${y} Q${x-50} ${y-6} ${cx} ${cy}" fill="none" stroke="${INK}" stroke-width="34" stroke-linecap="round"/><path d="M${x} ${y} Q${x-50} ${y-6} ${cx} ${cy}" fill="none" stroke="${body}" stroke-width="24" stroke-linecap="round"/>
 <g transform="translate(${cx},${cy}) rotate(${i?20:-30})">${path('M0 0 Q-42 -6 -50 -44 Q-26 -40 -6 -16 Z',claw,5)}${path('M0 0 Q-40 24 -56 6 Q-32 -4 -6 -16 Z',claw,5)}${path('M0 0 Q10 -10 8 -22 L-8 -22 Z',body,3)}</g>`).join('')}
 ${ell(-120,-10,40,32,body)}${circ(-132,-18,13,'#fff',4)}${circ(-130,-16,8,INK,0)}${circ(-127,-19,3,'#fff',0)}${path('M-146 8 Q-130 20 -112 6','none',4)}</g>`}

// ---------- Backgrounds ----------
function stars(n,seed,w,h){let r=seed,o='';const rnd=()=>{r=(r*16807)%2147483647;return r/2147483647};for(let i=0;i<n;i++){const x=rnd()*w,y=rnd()*h*.6;o+=`<circle cx="${x.toFixed(0)}" cy="${y.toFixed(0)}" r="${(1+rnd()*2.2).toFixed(1)}" fill="${rnd()>.8?'#ffd98a':'#fff'}" opacity="${(.5+rnd()*.5).toFixed(2)}"/>`}return o}
function cactus(x,y,s){return `<g transform="translate(${x},${y}) scale(${s})">${rect(-16,-150,32,150,16,'#2f9c93')}${rect(-52,-110,24,64,12,'#2f9c93')}${rect(-52,-60,56,22,10,'#2f9c93')}${rect(28,-130,24,70,12,'#2f9c93')}${rect(-4,-72,56,22,10,'#2f9c93')}
 ${[[0,-156],[-40,-116],[40,-136]].map(p=>`<circle cx="${p[0]}" cy="${p[1]}" r="12" fill="#ffe27a" filter="url(#glow)" opacity=".9"/>${circ(p[0],p[1],6,'#fff0a8',2)}`).join('')}</g>`}
function desert(W,H,opts={}){const g=H*.58;
 return `<rect width="${W}" height="${H}" fill="url(#gSky)"/>${stars(110,7,W,H)}
 <circle cx="${W*.66}" cy="${H*.22}" r="${H*.12}" fill="url(#gMoon)" stroke="#b8862e" stroke-width="3"/>${[[-.03,-.02,.02],[.02,.03,.015],[-.01,.04,.012]].map(c=>`<circle cx="${W*.66+c[0]*W}" cy="${H*.22+c[1]*H}" r="${c[2]*H*1.6}" fill="#c99a3a" opacity=".5"/>`).join('')}
 <circle cx="${W*.8}" cy="${H*.32}" r="${H*.055}" fill="#4f79c8" stroke="#2a4a8a" stroke-width="3"/>
 <path d="M0 ${g} Q${W*.18} ${g-120} ${W*.4} ${g-30} Q${W*.6} ${g-110} ${W*.82} ${g-20} Q${W*.92} ${g-60} ${W} ${g-30} L${W} ${H} L0 ${H} Z" fill="url(#gDune)" stroke="#7a3f6a" stroke-width="3"/>
 <path d="M0 ${g+90} Q${W*.3} ${g+30} ${W*.6} ${g+80} Q${W*.85} ${g+40} ${W} ${g+90} L${W} ${H} L0 ${H} Z" fill="url(#gSand)" stroke="#8a4a6a" stroke-width="3"/>
 <path d="M${W*.18} ${g+10} Q${W*.3} ${g-10} ${W*.46} ${g+12}" fill="none" stroke="rgba(255,255,255,.25)" stroke-width="5" stroke-linecap="round"/>
 ${cactus(W*.08,g+120,1)}${cactus(W*.14,g+135,.7)}${cactus(W*.9,g+125,1.1)}${cactus(W*.96,g+140,.6)}
 <path d="M${W*.45} ${g+12} l14 -50 l12 -10 l14 24 l16 -4 l12 40 z" fill="#8a5a6a" stroke="${INK}" stroke-width="4"/>`}
function lab(W,H){const f=H*.62;
 return `<rect width="${W}" height="${H}" fill="url(#gWall)"/><rect y="${f}" width="${W}" height="${H-f}" fill="url(#gFloor)"/><path d="M0 ${f} L${W} ${f}" stroke="${INK}" stroke-width="4"/>
 <circle cx="${W/2}" cy="${H*.38}" r="${H*.3}" fill="#3a5a7a" stroke="${INK}" stroke-width="6"/><circle cx="${W/2}" cy="${H*.38}" r="${H*.24}" fill="#1a2a44" stroke="#47d3ff" stroke-width="8"/><circle cx="${W/2}" cy="${H*.38}" r="${H*.17}" fill="#0d1830"/>
 ${[[.08,.14],[.24,.1],[.72,.1],[.86,.16]].map(m=>`${rect(W*m[0],H*m[1],W*.12,H*.16,10,'#16314e')}${path(`M${W*m[0]+16} ${H*m[1]+H*.12} l16 -20 l16 10 l18 -26 l16 12`,'none',4).replace(INK,'#47e0a8')}`).join('')}
 ${[[.2,'#4ee08a'],[.3,'#ff6ac8'],[.7,'#ffd24a']].map(t=>`${rect(W*t[0],H*.42,W*.05,H*.2,14,'rgba(200,240,255,.5)')}${rect(W*t[0]+6,H*.5,W*.05-12,H*.1,8,t[1],3)}`).join('')}
 ${rect(W*.34,H*.58,W*.32,H*.07,10,'#6a7f94')}${[0,1,2,3,4].map(i=>circ(W*.37+i*W*.055,H*.6,9,['#ff5a5a','#ffd24a','#4ee08a','#47d3ff','#c77aff'][i],3)).join('')}`}
const wrap=(W,H,body)=>`<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">${defs}${body}</svg>`;
const T={};
// 1: Timur sheet (white bg): main standing + expression heads
T[1]=wrap(1920,1080,`<rect width="1920" height="1080" fill="#fbfbfd"/>
 ${timur({x:620,y:965,s:1.75,face:'smile',aL:[10,8],aR:[6,6],lL:[4,0],lR:[4,0]})}
 ${[['scared',1230,980],['grumpy',1590,980],['joy',1230,1340],['wink',1590,1340]].map(([f,x,y])=>`<g transform="translate(${x},${y}) scale(1.7)">${head(f)}${helmet()}</g>`).join('')}
 <g font-family="DejaVu Sans, Arial" font-weight="900" font-size="56" fill="#15141c"><text x="60" y="100">ТИМУР</text></g>`);
// 2: Run scene
T[2]=wrap(1920,1080,`${desert(1920,1080)}
 ${scorpion({x:520,y:900,s:1.5,flip:false})}
 ${timur({x:1180,y:990,s:1.55,face:'scared',aL:[130,-10],aR:[60,-30],lL:[-40,-30],lR:[48,40],rot:-8,bodyDy:0})}`);
// 3: UV flashlight
T[3]=wrap(1920,1080,`${desert(1920,1080)}
 <path d="M1000 600 L1640 1000 L1020 1060 Z" fill="url(#gUV)" filter="url(#soft)"/><ellipse cx="1330" cy="1020" rx="330" ry="52" fill="rgba(160,90,255,.35)"/>
 ${scorpion({x:1300,y:1030,s:.55,glow:true,flip:true})}${scorpion({x:1560,y:1050,s:.4,glow:true,flip:true})}${scorpion({x:1130,y:1050,s:.32,glow:true})}
 ${timur({x:560,y:1000,s:1.6,face:'scared',aL:[8,4],aR:[96,0],lL:[8,0],lR:[8,0]})}
 <g transform="translate(930,596) rotate(32)">${rect(0,-12,84,26,8,'#3a3f4c',4)}${rect(76,-18,22,38,6,'#d8dde6',4)}<ellipse cx="98" cy="1" rx="5" ry="14" fill="#e3b8ff"/></g>`);
// 4: lab Zara + Nova
T[4]=wrap(1920,1080,`${lab(1920,1080)}${zara({x:640,y:975,s:1.55})}${nova({x:1340,y:540,s:1.15})}
 <g transform="translate(1590,520)"></g>`);
// 5: giant scorpion + tiny Timur
T[5]=wrap(1920,1080,`${desert(1920,1080)}${scorpion({x:900,y:960,s:3.1,flip:false})}
 ${timur({x:1620,y:1010,s:1.2,face:'scared',aL:[150,-40],aR:[150,-40],lL:[14,20],lR:[14,20]})}`);
window.T=T;
