window.mountDTRope = function (container, api) {
  const markup = `<div id="dt-alf-rope"><article class="arcade"><header class="mast">
    <img class="portrait" src="/static/art/home.webp" alt=""><div class="signature"><b>DT TEAM</b><span></span> ARCADE</div><h2>Трос <em>Альфа</em></h2></header>
    <div class="mission"><span data-ui="place"></span><strong data-ui="prize"></strong></div>
    <canvas width="840" height="484" aria-label="Альф на тросе. Цель — золотая полоса на крыше справа."></canvas>
    <div class="game-body"><div class="coupons" data-ui="marks"></div>
    <div class="message" aria-live="polite"><h3 data-ui="headline"></h3><p data-ui="hint"></p></div>
    <div class="actions"><button class="gold" data-ui="hold" hidden>Зажать трос</button>
    <button class="secondary" data-ui="bank" hidden></button><button class="gold" data-ui="next" hidden></button></div>
    <details><summary>Мои забеги <small data-ui="summary"></small></summary><div class="stats"><table>
    <thead><tr><th>Крыша</th><th>Дошёл</th><th>Срыв</th><th>Забрал</th></tr></thead><tbody></tbody></table></div></details></div></article></div>`;
  container.innerHTML=markup;
  const ui=Object.fromEntries([...container.querySelectorAll('[data-ui]')].map(e=>[e.dataset.ui,e]));
  const canvas=container.querySelector('canvas'), names=['Гранд-отель','Кинотеатр «Луна»','Часовая башня','Балкон клуба DT'];
  const lifetime=new AbortController(), opts={signal:lifetime.signal};
  const pendingKey='dt-rope-start-'+api.userId;
  let data,scene,input=null,arm=null,waiting=false,flying=false;
  const active=()=>container.isConnected&&!lifetime.signal.aborted;
  const sum=a=>a.reduce((n,m)=>n+m,0);
  function apply(value){
    if(!active())return;
    data=value;
    if(!scene)scene=window.createRopeScene(canvas,data.levels);
    scene.show(data.run);
    api.balanceChanged(data);
    display();
  }
  function display(){
    if(!data||!active())return;
    const r=data.run, i=r?.level??0, mode=r?.state??'lobby', bonus=data.levels[i].bonus;
    const ready=['ready','swing'].includes(mode),landed=mode==='landed',ended=!ready&&!landed;
    const count=landed||mode==='banked'?i+1:ready?i:0;
    ui.place.textContent=(i+1)+' / 4 · '+names[i];ui.prize.textContent='До +'+bonus+'%';
    ui.marks.innerHTML=data.levels.map((l,k)=>`<span class="${k<count?'taken':k===i?'target':''}">${k<count?'✓ ':''}+${l.bonus-(k?data.levels[k-1].bonus:0)}%</span>`).join('');
    ui.hold.hidden=!ready;ui.bank.hidden=!landed;ui.next.hidden=ready||(landed&&i===3);
    ui.hold.disabled=flying||waiting;ui.bank.disabled=waiting;ui.next.disabled=waiting||(ended&&(!data.enabled||data.balance<data.price));
    ui.hold.textContent=flying?'Альф в полёте…':input!==null?'Отпусти для прыжка':'Зажать трос';
    ui.bank.textContent='Забрать +'+bonus+'%';
    ui.next.textContent=landed?'Дальше до +'+(data.levels[i+1]?.bonus??12)+'%':!data.enabled?'Акция на паузе':data.balance<data.price?'Не хватает '+(data.price-data.balance)+' баллов':'Начать забег за '+data.price+' баллов';
    let title='Четыре крыши — до +12%',hint='Забери прибавку после любой крыши. Она пойдёт одним бонусом на следующую подтверждённую оплату.';
    if(ready){title='Впереди '+names[i];hint='Зажми кнопку или пробел и отпусти на разгоне. Цель — золотая площадка справа.';}
    if(landed){title='На крыше! Собрано +'+bonus+'%';hint=i===3?'Забери один бонус на следующую оплату.':'Забери бонус или рискни им на следующей крыше.';}
    if(mode==='lost'){title=i?'Срыв. Потерян бонус +'+data.levels[i-1].bonus+'%':'Прыжок не удался';hint=r.landing_x<data.levels[i].left?'Альф не долетел до площадки.':'Альф перелетел площадку.';}
    if(mode==='banked'){title='Бонус +'+bonus+'% сохранён';hint='В очередь добавлена одна прибавка к следующей подтверждённой оплате.';}
    ui.headline.textContent=title;ui.hint.textContent=hint;
    const {banked,lost}=data.stats;
    ui.summary.textContent='Финишей '+banked[3]+' / '+(sum(banked)+sum(lost));
    container.querySelector('tbody').innerHTML=banked.map((b,k)=>`<tr><td>${k+1}</td><td>${sum(banked.slice(k))+sum(lost.slice(k+1))}</td><td>${lost[k]}</td><td>${b}</td></tr>`).join('');
  }
  async function recover(err){
    if(!active())return;
    api.notice(err.message);
    try{apply(await api.request('/api/rope'));}catch(e){if(active())api.notice(e.message);}
  }
  async function choice(action){
    if(!active()||waiting||input!==null||flying||!data)return;
    const r=data.run;
    let body;
    if(action==='start'){
      if(!data.enabled||data.balance<data.price||['ready','swing','landed'].includes(r?.state))return;
      let nonce;try{const saved=JSON.parse(localStorage.getItem(pendingKey));if(saved?.previous_id===(r?.id??0))nonce=saved.request_id;}catch{}
      body={action,previous_id:r?.id??0,request_id:nonce||crypto.randomUUID()};
      try{localStorage.setItem(pendingKey,JSON.stringify(body));}catch{}
    }else{if(r?.state!=='landed')return;body={action,id:r.id,version:r.version};}
    waiting=true;display();
    try{
      const value=await api.request('/api/rope',body);
      if(action==='start'){try{localStorage.removeItem(pendingKey);}catch{}}
      apply(value);
    }catch(e){await recover(e);}finally{waiting=false;display();}
  }
  ui.next.onclick=()=>choice(data?.run?.state==='landed'?'next':'start');
  ui.bank.onclick=()=>choice('bank');
  function hold(source){
    const r=data?.run;
    if(!active()||input!==null||waiting||flying||!['ready','swing'].includes(r?.state))return;
    input=source;scene.hold();display();
    arm=api.request('/api/rope',{action:'arm',id:r.id,version:r.version}).then(value=>{
      if(value.run?.state!=='swing'||value.run.id!==r.id||value.run.version!==r.version+1)throw Error('Состояние забега изменилось.');
      if(active())data=value;
      return value.run;
    }).catch(async e=>{input=null;await recover(e);return null;});
  }
  async function release(source){
    if(input!==source||!active())return;
    input=null;flying=true;scene.fly();display();
    try{
      const r=await arm;
      if(r){
        const [value]=await Promise.all([api.request('/api/rope',{action:'release',id:r.id,version:r.version}),new Promise(done=>setTimeout(done,550))]);
        apply(value);if(active()&&value.run?.state==='landed')api.haptic();
      }
    }catch(e){await recover(e);}finally{flying=false;display();}
  }
  async function cancel(){
    if(input===null)return;
    input=null;waiting=true;await arm;waiting=false;
    if(active()&&data){scene.show(data.run);display();}
  }
  for(const surface of [ui.hold,canvas]){
    surface.addEventListener('contextmenu',e=>e.preventDefault(),opts);
    surface.addEventListener('pointerdown',e=>{
      if(!e.isPrimary||e.button!==0||waiting||flying||input!==null||ui.hold.hidden)return;
      e.preventDefault();surface.setPointerCapture(e.pointerId);hold(e.pointerId);
    },opts);
    surface.addEventListener('pointerup',e=>release(e.pointerId),opts);
    surface.addEventListener('pointercancel',cancel,opts);
    surface.addEventListener('lostpointercapture',e=>{if(input===e.pointerId)cancel();},opts);
  }
  ui.hold.addEventListener('keydown',e=>{if(['Space','Enter'].includes(e.code)){e.preventDefault();if(!e.repeat)hold(e.code);}},opts);
  ui.hold.addEventListener('keyup',e=>{if(input===e.code){e.preventDefault();release(e.code);}},opts);
  ui.hold.addEventListener('click',e=>{if(e.detail===0){if(input==='access')release('access');else hold('access');}},opts);
  window.addEventListener('blur',cancel,opts);
  document.addEventListener('visibilitychange',()=>{if(document.hidden)cancel();},opts);
  ui.headline.textContent='Загружаем забег…';
  api.request('/api/rope').then(apply).catch(recover);
  return {destroy(){lifetime.abort();scene?.destroy();},refresh(value){
    if(data&&input===null&&!flying&&!waiting){data.enabled=value.enabled;data.balance=value.balance??data.balance;display();}
  }};
};
