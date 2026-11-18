(() => {
  'use strict';
  const ordinary=['one','five','two','ten','four','one','five','two','cash','four','one','five','two','ten','four','one','five','two','ten','four'];
  const prizes={one:{points:1},two:{points:2},four:{points:4},five:{points:5},ten:{points:10},cash:{cash:20},jackpot:{cash:500}};
  Object.values(prizes).forEach(p=>p.name=p.cash?`${p.cash} $`:`+${p.points}%`);
  let root=null,ctx=null,data=null,tab='wheel',spinning=false,lastResult=null,rotation=0,sectors=[],rotor=null,pending=null;
  let ropeView=null;
  function unmount(){ropeView?.destroy();ropeView=null;}
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const date=v=>new Date(v).toLocaleString('ru-RU',{timeZone:'Europe/Moscow',day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
  const $=id=>root.querySelector('#dtw-'+id);
  const testing=()=>ctx?.game==='wheel_test';
  const key=()=>`dt-wheel-${testing()?'test-':''}pending-${ctx.userId}`;
  const endpoint=()=>testing()?'/api/wheel/test':'/api/wheel/spin';
  function saveNonce(nonce){pending=nonce;try{if(nonce)localStorage.setItem(key(),nonce);else localStorage.removeItem(key());}catch{}}
  function buildSectors(keep){const s=[...ordinary];if(!data.jackpot_claimed||keep==='jackpot')s.splice(5,0,'jackpot');return s;}
  function mount(container,value,context){
    unmount();root=container;ctx=context;data=value;tab=context.game==='rope'?'rope':'wheel';spinning=false;lastResult=null;rotation=0;
    try{pending=localStorage.getItem(key());}catch{pending=null;}
    if(testing() && data.history.length){
      lastResult=data.history[0];
      const segments=buildSectors(lastResult.prize);
      rotation=(360-(segments.indexOf(lastResult.prize)+.5)*360/segments.length)%360;
    }
    paint();
    root.onclick=async event=>{
      const button=event.target.closest('button');if(!button||button.dataset.nav||spinning)return;
      if(button.dataset.wheelTab){
        const wanted=button.dataset.wheelTab;
        if(wanted===tab)return;
        tab=wanted;paint();
        if(wanted!=='rope'){
          try{const fresh=await ctx.request('/api/wheel');if(root===container&&tab===wanted&&!spinning){data=fresh;paint();}}catch(e){ctx.notice(e.message);}
        }
      }
      else if(button.id==='dtw-spin')spin();
    };
  }
  function wheelHTML(){
    return `<div class="dtw-wheel-space"><div class="dtw-pointer" aria-hidden="true"></div><div class="dtw-wheel-rim"><svg id="dtw-wheel" role="img"></svg><div class="dtw-wheel-center"><div class="dtw-center-portrait"><img src="/static/art/home.webp" alt=""><span>DT TEAM</span></div></div><div class="dtw-wheel-glass" aria-hidden="true"></div></div><div class="dtw-celebration" id="dtw-celebration" aria-hidden="true"></div><div class="dtw-wheel-shadow"></div></div>`;
  }
  function paintTest(){
    const count=data.remaining, total=data.total;
    root.innerHTML=`<div id="dt-wheel"><div class="dtw-app">
      <header class="dtw-hero"><img src="/static/art/home.webp" alt=""><div class="dtw-hero-copy"><span>DT TEAM / АДМИН</span><h1>Тест колеса</h1></div></header>
      <section class="dtw-view"><div class="dtw-ticket-row"><span>Осталось попыток</span><strong>${count} из ${total}</strong></div>
      <p class="dtw-list-note">Вращай бесплатно. Все результаты здесь демонстрационные.</p>
      ${wheelHTML()}<button id="dtw-spin" class="dtw-primary"></button>
      <div id="dtw-outcome" aria-live="polite">${lastResult?resultHTML(lastResult):''}</div>
      <button class="action" data-nav="admin_home">В админку</button></section></div></div>`;
    drawWheel();updateControls();
  }
  function paint(){
    if(!root?.isConnected)return;
    unmount();
    if(testing()){paintTest();return;}
    root.innerHTML=`<div id="dt-wheel"><div class="dtw-app"><div class="dtw-hero"><img src="/static/art/home.webp" alt="Альф в клубе DT TEAM"><div class="dtw-hero-copy"><span>DT TEAM / ИГРЫ</span><h1>Игры DT</h1><p>1 € после вывода = 1 балл DT</p></div></div><div class="games-balance">Общий баланс <strong id="dtw-balance">${data.balance==null?'Сохранён':data.balance+' баллов'}</strong></div><nav class="dtw-tabs" aria-label="Разделы акции">${[['rope','Трос Альфа'],['wheel','Колесо'],['bonuses','Бонусы'],['history','История']].map(([id,label])=>`<button data-wheel-tab="${id}" ${(id==='wheel'||id==='rope')&&id!==ctx.game?'data-nav="'+id+'"':''} aria-selected="${id===tab}">${label}${id==='bonuses'?` <span>${data.coupons?.length||0}</span>`:''}</button>`).join('')}</nav>${ctx.admin&&tab==='wheel'?'<button class="action" data-nav="wheel_test">Тестовые вращения ›</button>':''}<section class="dtw-view" id="dtw-content"></section></div></div>`;
    const view=$('content');
    if(tab==='rope'&&(data.enabled||data.open_run)){
      ropeView=window.mountDTRope(view,{...ctx,balanceChanged(value){
        data.balance=value.balance;data.available=Math.floor(value.balance/150);
        data.open_run=['ready','swing','landed'].includes(value.run?.state);
        const badge=$('balance');if(badge)badge.textContent=value.balance+' баллов';
      }});return;
    }
    if(!data.enabled){view.innerHTML='<h2 class="dtw-tab-heading">Акция на паузе</h2><p class="dtw-list-note">Вращения и заработанные бонусы сохранены. Прибавка применится к следующей подтверждённой оплате.</p>'+(pending?'<button id="dtw-spin" class="dtw-primary">Проверить последнее вращение</button>':'')+(lastResult?resultHTML(lastResult):'');return;}
    if(tab==='bonuses'){
      view.innerHTML=`<h2 class="dtw-tab-heading">Твои бонусы</h2><p class="dtw-list-note">Бонусы применяются автоматически к следующим подтверждённым оплатам: по одному, в порядке получения. Например, 70% + 5% = 75%.</p>${data.coupons.length?data.coupons.map((p,i)=>`<div class="dtw-history-item"><strong>+${p.points}%</strong><div>${i===0?'К следующей оплате':`В очереди · ${i+1}`}<small>${date(p.at)} МСК</small></div></div>`).join(''):'<p class="dtw-list-note">Здесь появятся твои процентные бонусы.</p>'}<button class="dtw-primary" data-nav="wallet">Денежные призы в кошельке ↗</button>`;return;
    }
    if(tab==='history'){
      view.innerHTML=`<h2 class="dtw-tab-heading">История призов</h2><p class="dtw-list-note">Всего вращений: ${data.used}. Последние 50 результатов · время по Москве.</p>${data.history.length?data.history.map(p=>`<div class="dtw-history-item"><strong>${p.cash?`${p.cash} $`:`+${p.points}%`}</strong><div>${p.cash?'Начислено в кошелёк':p.used_request_id?`Применён · заявка #${p.used_request_id}`:'Ожидает следующую оплату'}<small>${date(p.at)} · №${p.id}</small></div></div>`).join(''):'<p class="dtw-list-note">Первый приз уже ждёт твоего вращения.</p>'}`;return;
    }
    view.innerHTML=`<div class="dtw-jackpot"><div><span>ГЛАВНЫЙ ПРИЗ</span><strong>500 <small>$</small></strong></div><div class="dtw-jackpot-note"><b>${data.jackpot_claimed?'ПРИЗ РАЗЫГРАН':'ОДИН НА ВСЮ АКЦИЮ'}</b><span>${data.jackpot_claimed?'Остальные бонусы доступны':'Твой большой сюрприз'}</span></div></div><div class="dtw-ticket-row"><span>Одно вращение</span><strong>150 баллов</strong></div>${data.waiting?`<p class="dtw-list-note">${data.waiting} € ждут вывода.</p>`:''}${data.debt?`<p class="dtw-list-note">После возврата оплаты следующие ${data.debt} баллов покроют ранее потраченный остаток.</p>`:''}${wheelHTML()}<button id="dtw-spin" class="dtw-primary"></button><p class="dtw-spin-hint">Только оплаты, подтверждённые при включённой акции и выведенные с PayPal.</p><div id="dtw-outcome" aria-live="polite">${lastResult?resultHTML(lastResult):''}</div>${data.coupons.length?`<div class="dtw-active-bonus"><strong>+${data.coupons[0].points}%</strong><p>К следующей подтверждённой оплате<small>Бонусов в очереди: ${data.coupons.length}</small></p></div>`:''}<details class="dtw-rules"><summary>Призы и правила <span>＋</span></summary><p>+1%, +2%, +4%, +5%, +10%, 20 $ и один главный приз 500 $. Денежные призы начисляются в USDT: 20 $ = 20 USDT, 500 $ = 500 USDT.</p><p>1 € подтверждённой во время акции и выведенной оплаты даёт 1 балл. При старте забега списывается 100 баллов, при вращении — 150. Старые подтверждения и оплаты, подтверждённые на паузе, не участвуют. Суммы складываются; остаток сохраняется.</p><p>Процентный бонус прибавляется к ставке следующей подтверждённой оплаты. Бонусы применяются по одному, в порядке получения, включая Happy Hours. При возврате оплаты использованный процентный бонус возвращается в очередь.</p><p>Возвращённые оплаты исключаются из прогресса. Уже полученные призы остаются, а недостающий прогресс покрывается следующими оплатами.</p><p>Во время паузы вращения недоступны. Оплаты, подтверждённые до паузы в рамках акции, сохраняют право на прогресс после вывода. Баллы и бонусы сохраняются.</p></details>`;
    drawWheel();updateControls();
  }
  function resultHTML(p){
    if(p.test)return `<section class="dtw-result"><div class="dtw-result-kicker">ТЕСТОВЫЙ РЕЗУЛЬТАТ</div><div class="dtw-result-value">${p.cash?`${p.cash} $`:`+${p.points}%`}</div><p>Пробное вращение · без начисления приза</p></section>`;
    return `<section class="dtw-result"><div class="dtw-result-kicker">${p.prize==='jackpot'?'ГЛАВНЫЙ ПРИЗ ТВОЙ':'ТВОЙ ПРИЗ'}</div><div class="dtw-result-value">${p.cash?`${p.cash} $`:`+${p.points}%`}</div><h2>${p.cash?'Баланс пополнен':'Бонус сохранён'}</h2><p>${p.cash?`${p.cash} USDT уже доступны в кошельке.`:`+${p.points}% применятся к следующей подтверждённой оплате в порядке очереди.`}</p></section>`;}
  function updateControls(){if(!root?.isConnected)return;const b=$('spin');if(!b)return;
    if(testing()){
      b.disabled=spinning||ctx.isBusy()||(!pending && data.remaining<1);
      b.textContent=spinning?'Колесо вращается…':pending?'Проверить попытку':data.remaining?'Крутить тестово':'Попытки закончились';
      return;
    }
    b.disabled=spinning||ctx.isBusy()||(!pending&&(!data.enabled||data.available<1));b.textContent=spinning?'Твой приз уже выбран…':pending?'Проверить последнее вращение':data.available>0?'Крутить за 150 баллов':`Ещё ${data.remaining||150} баллов до вращения`;}
  async function refresh(value){if(!root?.isConnected||spinning||ctx.isBusy())return;
    if(tab==='rope'&&ropeView){
      Object.assign(data,value);const badge=$('balance');if(badge&&value.balance!=null)badge.textContent=value.balance+' баллов';
      ropeView.refresh(value);return;
    }
    if(JSON.stringify([value.enabled,value.balance,value.qualified,value.used,value.waiting,value.revision])!==JSON.stringify([data.enabled,data.balance,data.qualified,data.used,data.waiting,data.revision])){try{data=await ctx.request('/api/wheel');paint();}catch(e){ctx.notice(e.message);}}}
  async function spin(){
    const unavailable=testing()?data.remaining<1:(!data.enabled||data.available<1);
    if(spinning||ctx.isBusy()||(!pending&&unavailable))return;
    spinning=true;ctx.busy(true);updateControls();ctx.notice('');
    const nonce=pending||crypto.randomUUID();saveNonce(nonce);
    try{
      const response=await ctx.request(endpoint(),{request_id:nonce});
      const result=response.result;saveNonce(null);
      // Money/coupon is already committed. Animation cannot decide or grant it.
      lastResult=null;
      if(!testing()&&!data.enabled){data=response.wheel;lastResult=result;spinning=false;paint();return;}
      spinning=false;drawWheel();spinning=true;
      if(result.prize==='jackpot'&&!sectors.includes('jackpot')){lastResult=result;spinning=false;drawWheel();spinning=true;lastResult=null;}
      const index=sectors.indexOf(result.prize),step=360/sectors.length;
      if(index<0)throw new Error('Приз сохранён. Откройте историю для просмотра результата.');
      const desired=(360-(index+.5)*step+360)%360,mod=((rotation%360)+360)%360;
      rotation+=1800+(desired-mod+360)%360;
      const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
      const panel=root.querySelector('#dt-wheel');panel.dataset.spinning='true';root.querySelector('.dtw-pointer').classList.add('is-spinning');
      rotor.style.transition=reduced?'none':'transform 4.7s cubic-bezier(.12,.67,.13,1)';rotor.getBoundingClientRect();rotor.style.transform=`rotate(${rotation}deg)`;
      await new Promise(resolve=>setTimeout(resolve,reduced?30:4800));
      data=response.wheel;lastResult=result;spinning=false;paint();
      ctx.haptic();$('outcome')?.scrollIntoView({block:'nearest',behavior:reduced?'instant':'smooth'});
    }catch(e){if(e.status&&e.status<500)saveNonce(null);ctx.notice(e.message);try{
      data=await ctx.request(testing()?'/api/wheel/test':'/api/wheel');
      if(testing())lastResult=data.history[0]||null;
    }catch{}spinning=false;paint();}
    finally{spinning=false;ctx.busy(false);updateControls();ctx.updated();}
  }
  function node(name,attrs={}){const el=document.createElementNS('http://www.w3.org/2000/svg',name);Object.entries(attrs).forEach(([k,v])=>el.setAttribute(k,String(v)));return el;}
  function drawWheel(){
    if(spinning)return;
    sectors=buildSectors(lastResult?.prize);
    const svg=root.querySelector('#dtw-wheel'),size=330,c=size/2,r=c-5,step=360/sectors.length;
    const finishes={one:['#35323e','#131018','#eee0d2'],two:['#6c5148','#2d2029','#fbe6c3'],four:['#b3884d','#64432f','#fff0cd'],five:['#f0d498','#b58a4e','#28180f'],ten:['#fff5dc','#dfb976','#302014'],cash:['#835561','#402331','#fff0cc'],jackpot:['#b75260','#551525','#fff0c8']};
    svg.setAttribute('viewBox',`0 0 ${size} ${size}`);svg.replaceChildren();
    const desc=node('desc');desc.textContent=[...new Set(sectors)].map(k=>prizes[k].name).join('. ');svg.append(desc);
    const defs=node('defs');
    Object.entries(finishes).forEach(([key,colors])=>{const gradient=node('radialGradient',{id:'dtw-finish-'+key,cx:c,cy:c,r,gradientUnits:'userSpaceOnUse'});gradient.append(node('stop',{offset:'0%','stop-color':colors[1]}),node('stop',{offset:'49%','stop-color':colors[1]}),node('stop',{offset:'100%','stop-color':colors[0]}));defs.append(gradient);});svg.append(defs);
    rotor=node('g');rotor.id='dtw-rotor';rotor.style.transformOrigin=`${c}px ${c}px`;rotor.style.transformBox='view-box';rotor.style.transform=`rotate(${rotation}deg)`;svg.append(rotor);
    const point=(a,rr=r)=>[c+rr*Math.sin(a*Math.PI/180),c-rr*Math.cos(a*Math.PI/180)];
    const landed=lastResult?Math.floor(((360-(rotation%360)+360)%360)/step):-1;
    sectors.forEach((key,i)=>{
      const a=i*step,b=(i+1)*step,p=point(a),q=point(b),prize=prizes[key],ink=finishes[key]?.[2]||prize.ink;
      const path=node('path',{d:`M ${c} ${c} L ${p[0]} ${p[1]} A ${r} ${r} 0 0 1 ${q[0]} ${q[1]} Z`,fill:`url(#dtw-finish-${key})`,stroke:'#171017','stroke-width':1.2,'data-prize':key});
      if(i===landed&&key===lastResult?.prize)path.setAttribute('class','dtw-wheel-winning');rotor.append(path);
      const rimA=point(a+1.3,r*.967),rimB=point(b-1.3,r*.967);
      rotor.append(node('path',{d:`M ${rimA[0]} ${rimA[1]} A ${r*.967} ${r*.967} 0 0 1 ${rimB[0]} ${rimB[1]}`,fill:'none',stroke:key==='jackpot'?'#ffe6a8':'#ffe4b0','stroke-opacity':key==='jackpot'?.85:.32,'stroke-width':key==='jackpot'?2:1}));
      const transform=`rotate(${a+step/2} ${c} ${c})`,fontSize=key==='jackpot'?(size<280?14:17):(size<280?15:18);
      const label=node('text',{x:c,y:c-r*.825,'text-anchor':'middle','dominant-baseline':'middle',fill:ink,transform,'font-family':'Team, sans-serif','font-size':fontSize,'font-weight':500});
      label.textContent=prize.cash?String(prize.cash):'+'+prize.points;rotor.append(label);
      const unit=node('text',{x:c,y:c-r*.65,'text-anchor':'middle','dominant-baseline':'middle',fill:ink,transform,'font-family':'Team, sans-serif','font-size':11,'font-weight':400,'fill-opacity':.88});unit.textContent=prize.cash?'$':'%';rotor.append(unit);
      const pin=point(a,r*.995);rotor.append(node('circle',{cx:pin[0],cy:pin[1],r:1.35,fill:'#e6c993'}));
    });
    rotor.append(node('circle',{cx:c,cy:c,r:r*.46,fill:'none',stroke:'#d4aa65','stroke-opacity':.28,'stroke-width':.7}));
    svg.append(node('circle',{cx:c,cy:c,r:r+1,fill:'none',stroke:'#e7c58a','stroke-opacity':.7,'stroke-width':1}));
    svg.setAttribute('aria-label',desc.textContent);
  }
  window.DTWheel={mount,unmount,updateControls,refresh,isSpinning:()=>spinning};
})();
