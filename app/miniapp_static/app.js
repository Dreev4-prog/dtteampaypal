(() => {
  'use strict';
  const tg = window.Telegram?.WebApp;
  const screen = document.getElementById('screen');
  const nav = document.getElementById('navigation');
  const notice = document.getElementById('notice');
  let token = '', current = null, inFlight = false, objectURLs = [], pollTimer = null, selectedPhoto = null, previewURL = '';
  let events=[], knownEvents=null, updateTimer=null, updating=false, readEvents=new Set(), alertTimer=null, noticeTimer=null;
  const eventPanel=document.getElementById('notification-panel'), liveAlert=document.getElementById('live-alert');
  const escape = value => String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const amount = value => Number(value || 0).toLocaleString('ru-RU',{minimumFractionDigits:2,maximumFractionDigits:2});
  const plain = html => new DOMParser().parseFromString(html || '', 'text/html').body.textContent || '';
  const clean = label => label.replace(/[\p{Extended_Pictographic}\uFE0F\u200D]/gu,'').trim() || (/⬅|◀/.test(label)?'Предыдущая':/➡|▶/.test(label)?'Следующая':/🗑/.test(label)?'Удалить':label);
  const art = banner => ({paypal:'paypal',issued:'paypal',database:'paypal',requests:'check',payments:'check',support:'support',profile:'support',broadcast:'support',links:'support'}[banner] || 'home');
  const symbol = label => /выплат|кошел|баланс/i.test(label)?'◈':/поиск|найти/i.test(label)?'⌕':/назад|главно|меню/i.test(label)?'‹':/удал|отмен|отказ/i.test(label)?'×':/время|ждём|24|дат|истор/i.test(label)?'◷':/пользов|кабинет|участ/i.test(label)?'♙':/поддерж|сообщ|контент/i.test(label)?'✉':/добав|созда/i.test(label)?'+':'↗';

  async function request(path, body) {
    const controller=new AbortController(), timeout=setTimeout(()=>controller.abort(),20000);
    let response;
    try{response = await fetch(path, {method:body?'POST':'GET',cache:'no-store',credentials:'omit',signal:controller.signal,
      headers:{...(token?{Authorization:'MiniApp '+token}:{}),...(body?{'Content-Type':'application/json'}:{})},
      body:body?JSON.stringify(body):undefined});}
    catch{throw new Error('Связь прервалась. Нажмите «Обновить данные», чтобы проверить результат.');}
    finally{clearTimeout(timeout);}
    const data = await response.json();
    if(!response.ok){const error=new Error(data.error || 'Сервис временно недоступен');error.status=response.status;throw error;}
    return data;
  }
  function showNotice(text){clearTimeout(noticeTimer);notice.hidden=!text;notice.textContent=text||'';if(text){tg?.HapticFeedback?.notificationOccurred?.(/ошиб|не удалось|недоступ|отказ|прервал/i.test(text)?'warning':'success');if(/^✅|данные обновлены/i.test(text))noticeTimer=setTimeout(()=>showNotice(''),5000);}}
  function busy(value){inFlight=value;document.getElementById('progress').hidden=!value;document.querySelectorAll('button,input,textarea').forEach(e=>e.disabled=value);window.DTWheel?.updateControls();}
  function releaseMedia(){objectURLs.forEach(url=>URL.revokeObjectURL(url));objectURLs=[];}
  async function loadMedia(data){
    const version=data.version;
    for(const element of screen.querySelectorAll('[data-media]')){
      try{
        const response=await fetch('/api/media/'+encodeURIComponent(element.dataset.media),{headers:{Authorization:'MiniApp '+token},cache:'no-store',credentials:'omit'});
        if(!response.ok)throw new Error();
        const blob=await response.blob();
        if(current?.version!==version)return;
        const url=URL.createObjectURL(blob);objectURLs.push(url);
        if(element.tagName==='IMG')element.src=url;else element.href=url;
      }catch{element.hidden=true;showNotice('Изображение или документ не удалось загрузить. Они доступны в чате с ботом.');}
    }
  }
  function button(b, primary=false){
    const text=clean(b.label),danger=/удалить|заблокировать|отказать|отклонить/i.test(text),quiet=/^(назад|главное меню|отмен|к списку)/i.test(text),selected=/^✅/.test(b.label)&&/CryptoBot|xRocket/.test(text);
    const cls='action'+(primary?' primary':'')+(danger?' danger':'')+(quiet?' quiet':'');
    const inner=`<span class="symbol" aria-hidden="true">${selected?'✓':symbol(text)}</span><span class="label">${escape(text)}${selected?'<small class="selection-label">Выбран</small>':''}</span><span class="arrow" aria-hidden="true">${b.url?'↗':'›'}</span>`;
    return b.url?`<a class="${cls}" href="${escape(b.url)}" target="_blank" rel="noopener noreferrer">${inner}</a>`:`<button class="${cls}" data-action="${escape(b.action)}">${inner}</button>`;
  }
  function rows(message){return `<div class="rows">${message.rows.map((row,i)=>`<div class="row" style="--columns:${row.length}">${row.map(b=>button(b,i===0&&row.length===1&&/подтвердить|сохранить|выдать|очередь|отправить|продолжить|начать|готово/i.test(b.label))).join('')}</div>`).join('')}</div>`;}
  function formHTML(form){
    if(!form)return '';
    const photo=form.kind==='photo',receipt=form.kind==='receipt';
    const input=photo?'':form.kind==='time'?`<input id="text-input" type="time" aria-label="${escape(form.label)}">`:`<textarea id="text-input" rows="${form.kind==='number'?1:3}" ${form.kind==='number'?'inputmode="numeric"':''} maxlength="10000" placeholder="${escape(form.placeholder)}"></textarea>`;
    return `<form class="form" id="input-form"><label for="${photo?'photo-input':'text-input'}">${escape(form.label)}</label>${input}${form.quick?`<div class="quick-amounts" aria-label="Быстрый ввод суммы">${form.quick.map(n=>`<button type="button" data-amount="${n}">${n} €</button>`).join('')}</div>`:''}${photo||receipt?'<label class="file-picker" for="photo-input">＋ Выбрать фото<input id="photo-input" type="file" accept="image/jpeg,image/png,image/webp"></label><div id="photo-preview" hidden></div><small>JPEG, PNG или WebP · до 8 МБ. Фото сохранится в чате с ботом.</small>':''}${receipt?'<small>После отправки чек получит участник, а выбранные начисления будут отмечены выплаченными.</small>':''}<button type="submit" class="action primary">${escape(form.submit)} <span class="arrow">↗</span></button></form>`;
  }
  function journeyHTML(journey){
    if(!journey)return '';
    const recap=[journey.amount?`${journey.amount} €`:null,journey.gender?({male:'Мужской PayPal',female:'Женский PayPal'}[journey.gender]):null].filter(Boolean).join(' · ');
    return `<div class="journey"><div class="journey-steps">${journey.labels.map((label,i)=>`<span ${i+1===journey.step?'aria-current="step"':''} class="${i+1<journey.step?'done':''}"><b>${i+1<journey.step?'✓':i+1}</b>${escape(label)}</span>`).join('')}</div>${recap?`<p>${escape(recap)}</p>`:''}</div>`;
  }
  function backTarget(){
    const buttons=(current?.messages||[]).flatMap(m=>m.rows.flat()).filter(b=>b.action);
    return buttons.find(b=>/^⬅/.test(b.label)&&clean(b.label)!=='Предыдущая'&&!/главное меню/i.test(b.label))
      ||buttons.find(b=>/^(отмена|отменить заявку|назад)$/i.test(clean(b.label)))
      ||buttons.find(b=>/главное меню/i.test(b.label));
  }
  function goBack(){if(eventPanel.open){eventPanel.close();return;}if(current?.journey?.step>1){act({nav:'request_back'});return;}const target=backTarget();act(target?{action:target.action}:{nav:current?.section==='admin_home'?'admin_home':'home'});}
  function paintPhoto(){
    const box=document.getElementById('photo-preview');if(!box)return;
    if(previewURL)URL.revokeObjectURL(previewURL);previewURL='';box.hidden=!selectedPhoto;
    if(selectedPhoto){previewURL=URL.createObjectURL(selectedPhoto);box.innerHTML=`<img src="${previewURL}" alt="Выбранное фото"><span>${escape(selectedPhoto.name)}</span><button type="button" data-remove-photo>Убрать фото</button>`;}else box.innerHTML='';
  }
  function homeHTML(data){
    const summary=data.summary;
    return `<section class="entry"><img src="/static/art/home.webp" alt="Альф в чёрном костюме на троне"><div class="entry-copy"><span>${data.work?'РАБОТА ОТКРЫТА':'STOP WORK'}</span><h1>Для<br>своих.</h1></div><button class="home-cta" data-nav="paypal_request">Получить PayPal <span>↗</span></button></section><section class="membership"><div class="member-line"><span>Личный кабинет</span><b>${escape(data.user.name)} / DT TEAM</b></div><div class="balance-label">Доступно к выплате</div><div class="balance">${amount(summary.available)}<span>USDT</span><button aria-label="Открыть кошелёк" data-nav="wallet">↗</button></div><button class="held" data-nav="wallet"><span>◷ Ждём вывод с PayPal</span><strong>${amount(summary.held)} USDT ↗</strong></button></section>${data.wheel?.enabled?`<button class="wheel-entry" data-nav="wheel"><div><strong>DT Колесо</strong><small>${data.wheel.available?`Доступно вращений: ${data.wheel.available}`:`Каждые 150 € — новое вращение`}</small></div><span>↗</span></button>`:''}<section class="home-list"><h2>Мои PayPal / ${String(summary.working).padStart(2,'0')}</h2><button data-nav="my_paypals">PayPal в работе и вся история <span>Смотреть →</span></button><button data-nav="dt_payments">DT Payments <span>↗</span></button><button data-nav="support">Поддержка <span>↗</span></button>${data.user.admin?'<button data-nav="admin_home">Администрирование <span>↗</span></button>':''}</section>`;
  }
  function copyHTML(message,data){
    const html=message.html||'';
    if(data.payouts)return `<p class="admin-summary">Выберите участника для выплаты. Его доступные начисления объединятся в один чек.</p><details class="details"><summary>Общая статистика выплат</summary><div class="copy">${html}</div></details>`;
    if(data.dashboard){const d=data.dashboard;return `<div class="admin-state">${data.work?'Работа открыта':'STOP WORK'} <span>· AUTO ${d.auto_issue?'вкл.':'выкл.'}</span></div><p class="admin-summary">Очередь: ${d.queue} · На проверке: ${d.waiting_check}</p><details class="details"><summary>Сводка по клубу</summary><div class="copy">${html}</div></details>`;}
    if(data.wallet){const w=data.wallet;return `<div class="wallet-card"><div class="balance-label">Доступно к выплате</div><div class="balance">${amount(w.available)}<span>USDT</span></div></div><div class="wallet-held">Ждём вывод с PayPal<strong>${amount(w.held)} USDT</strong></div><div class="wallet-line">Способ выплаты<strong>${w.method==='xrocket'?'xRocket':'CryptoBot'}</strong></div><div class="wallet-line">Выплачено всего<strong>${amount(w.paid)} USDT</strong></div><div class="wallet-line">Выплат за всё время<strong>${w.count_paid}</strong></div>${w.wheel_next_bonus?`<div class="wallet-held">DT Колесо · к следующей оплате<strong>+${w.wheel_next_bonus}%</strong><small>Бонусов в очереди: ${w.wheel_bonus_count}</small></div>`:''}<details class="details"><summary>Подробности баланса</summary><div class="copy">${html}</div></details>`;}
    return `<div class="copy">${html.replace(/^━+\n/gm,'').replace(/\n━+$/gm,'')}</div>`;
  }
  function render(data){
    const changed=!current||data.version!==current.version||data.user?.status!==current.user?.status;
    const draft=current?.form?.key===data.form?.key?document.getElementById('text-input')?.value:null;
    if(current?.form?.key!==data.form?.key){selectedPhoto=null;if(previewURL)URL.revokeObjectURL(previewURL);previewURL='';}
    current=data;busy(Boolean(data.busy));
    document.getElementById('notifications').hidden=!(data.user.admin||data.user.status==='approved');
    if(!changed)return;
    releaseMedia();
    showNotice((data.notices||[]).join('\n'));
    if(['blocked','rejected'].includes(data.user.status)&&!data.user.admin){
      screen.innerHTML='<section class="entry"><img src="/static/art/support.webp" alt="Альф на связи"><div class="entry-copy"><span>DT TEAM</span><h1>Доступ<br>закрыт.</h1><p>Обратитесь в поддержку.</p><a class="entry-action" href="https://t.me/profitgeld">Написать поддержке ↗</a></div></section>';nav.hidden=true;return;
    }
    if(data.route==='home'&&data.summary){screen.innerHTML=homeHTML(data);}
    else if(data.route==='wheel'){screen.innerHTML='<div id="wheel-root"></div>';window.DTWheel.mount(document.getElementById('wheel-root'),data.wheel,{request,busy,isBusy:()=>inFlight,notice:showNotice,userId:data.user.id,haptic:()=>tg?.HapticFeedback?.notificationOccurred?.('success'),updated:refreshUpdates});}
    else{
      const messages=data.messages||[], first=messages.find(m=>m.html)||messages[0];
      const lines=plain(first?.html).split('\n').filter(x=>x.trim());
      const banner=first?.banner||'home';
      const titles={home:'Для своих.',paypal_request:'Получить PayPal',wallet:'Кошелёк',my_paypals:'Мои PayPal',profile:'Кабинет',support:'Поддержка',admin_home:'Управление',paypal_payments_hub:'Работа с PayPal',payouts_v22:'Центр выплат'};
      const detailTitle=/^(payment_card|paypal_withdraw|wd_wait|payment_refund)/.test(data.route)?'Оплата PayPal':/^member_card/.test(data.route)?'Участник':/^payout_user/.test(data.route)?'Выплаты участника':/^my_paypals_list/.test(data.route)?'Мои PayPal':null;
      let title=data.journey?'Получить PayPal':titles[data.route]||detailTitle||clean(lines[0]||'DT TEAM');
      if(title.length>35)title=({paypal:'Получить PayPal',requests:'Мои PayPal',profile:'Кабинет',payments:'Оплаты',admin:'Управление',database:'База PayPal',support:'Поддержка',broadcast:'Контент'}[banner]||'DT TEAM');
      const provider=data.payouts?`<div class="provider-totals"><div>CryptoBot<strong>${amount(data.payouts.cryptobot_total)}</strong><small>USDT к выплате</small></div><div>xRocket<strong>${amount(data.payouts.xrocket_total)}</strong><small>USDT к выплате</small></div></div>`:'';
      screen.innerHTML=`<section class="cover ${data.form||data.journey?'compact':''}"><img src="/static/art/${art(data.wallet?'home':banner)}.webp" alt="Альф · DT TEAM"><div class="cover-copy"><span>DT TEAM / PRIVATE CLUB</span><h1>${escape(title)}</h1><small>${data.user.admin?'Управление клубом':'Личный кабинет'}</small></div></section><section class="content">${journeyHTML(data.journey)}${provider}${messages.map((m,i)=>`<article class="message">${m.photo&&!m.photo.is_banner?`<img class="proof" data-media="${escape(m.photo.id)}" alt="Изображение из бота">`:''}${copyHTML(m,data)}${m.document?`<a class="download" data-media="${escape(m.document.id)}" download="${escape(m.document.filename)}">↓ ${escape(m.document.filename)}</a>`:''}${i===messages.length-1?formHTML(data.form):''}${rows(m)}</article>`).join('')}${messages.length?'':formHTML(data.form)}</section>`;
    }
    const input=document.getElementById('text-input');if(input&&draft!=null)input.value=draft;
    paintPhoto();
    document.getElementById('back').hidden=data.route==='home';
    nav.hidden=false;
    const tabs=[['home','⌂','Главная'],['my_paypals','▱','PayPal'],['wallet','◈','Кошелёк'],['profile','♙','Кабинет']];
    if(data.user.admin)tabs.push(['admin_home','⚙','Управление']);
    nav.style.setProperty('--tabs',tabs.length);
    nav.innerHTML=tabs.map(([id,icon,label])=>`<button data-nav="${id}" ${data.section===id?'aria-current="page"':''}><span aria-hidden="true">${icon}</span>${label}</button>`).join('');
    tg?.BackButton?.[data.route==='home'?'hide':'show']();
    busy(Boolean(data.busy));
    screen.classList.remove('screen-enter');requestAnimationFrame(()=>screen.classList.add('screen-enter'));
    loadMedia(data);
    if(!data.busy)refreshUpdates();
  }
  function updateBadge(){
    const count=events.filter(event=>!readEvents.has(event.id)).length,badge=document.getElementById('notification-count');
    badge.hidden=!count;badge.textContent=count>9?'9+':String(count);
    document.getElementById('notifications').setAttribute('aria-label',count?`Уведомления: ${count} новых`:'Уведомления');
  }
  function drawEvents(){
    document.getElementById('notification-list').innerHTML=events.length?events.map(event=>`<article class="event ${readEvents.has(event.id)?'':'unread'}"><div class="event-top"><span>${event.tone==='success'?'✓':event.tone==='waiting'?'◷':event.tone==='warning'?'!':'•'}</span><time>${new Date(event.at).toLocaleString('ru-RU',{timeZone:'Europe/Moscow',day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'})}</time></div><h3>${escape(event.title)}</h3><p>${escape(event.body)}</p><button data-event-nav="${escape(event.nav)}">${escape(event.label)} →</button></article>`).join(''):'<div class="empty-events"><span>◷</span><h3>Пока нет событий</h3><p>Здесь появятся изменения по вашим PayPal и выплатам.</p></div>';
  }
  function markRead(){events.forEach(event=>readEvents.add(event.id));readEvents=new Set([...readEvents].slice(-300));try{localStorage.setItem('dt-read-events-'+current.user.id,JSON.stringify([...readEvents]));}catch{}updateBadge();}
  function openEvents(){drawEvents();if(!eventPanel.open)eventPanel.showModal();liveAlert.hidden=true;markRead();}
  async function refreshUpdates(){
    clearTimeout(updateTimer);
    if(!token||updating||document.hidden||!(current?.user.admin||current?.user.status==='approved'))return;
    updating=true;
    try{
      const updates=await request('/api/updates');
      const fresh=knownEvents?updates.events.filter(event=>!knownEvents.has(event.id)&&!readEvents.has(event.id)):[];
      events=updates.events;knownEvents=new Set(events.map(event=>event.id));updateBadge();
      if(fresh.length){liveAlert.textContent=fresh.length===1?`${fresh[0].title} · Открыть`:`Новых событий: ${fresh.length} · Открыть`;liveAlert.hidden=false;tg?.HapticFeedback?.notificationOccurred?.('success');clearTimeout(alertTimer);alertTimer=setTimeout(()=>liveAlert.hidden=true,9000);}
      if(eventPanel.open){drawEvents();markRead();}
      if(current.route==='home'&&!inFlight&&JSON.stringify([current.summary,current.work,current.wheel])!==JSON.stringify([updates.summary,updates.work,updates.wheel])){current.summary=updates.summary;current.work=updates.work;current.wheel=updates.wheel;screen.innerHTML=homeHTML(current);}
      if(current.route==='wheel'&&!inFlight)window.DTWheel?.refresh(updates.wheel);
      if(current.wallet&&!inFlight){current.wallet.available=updates.summary.available;current.wallet.held=updates.summary.held;const card=screen.querySelector('.wallet-card .balance'),held=screen.querySelector('.wallet-held strong');if(card)card.innerHTML=`${amount(updates.summary.available)}<span>USDT</span>`;if(held)held.textContent=amount(updates.summary.held)+' USDT';}
    }catch(error){if(error.status===401){showNotice(error.message);token='';}}
    finally{updating=false;if(token)updateTimer=setTimeout(refreshUpdates,12000);}
  }
  async function poll(){
    clearTimeout(pollTimer);
    try{const data=await request('/api/state');render(data);if(data.busy)pollTimer=setTimeout(poll,1200);}
    catch(error){busy(false);showNotice(error.message+' Нажмите ↻, чтобы проверить состояние.');}
  }
  async function act(body){
    if(inFlight||!current)return;
    busy(true);showNotice('');
    try{const data=await request('/api/action',{...body,version:current.version,request_id:crypto.randomUUID()});render(data);if(data.busy)pollTimer=setTimeout(poll,500);window.scrollTo({top:0,behavior:'instant'});}
    catch(error){busy(false);showNotice(error.message);if(error.status===409)await poll();}
  }
  document.addEventListener('click',event=>{
    const button=event.target.closest('button');if(!button)return;
    if(button.dataset.eventNav){eventPanel.close();act({nav:button.dataset.eventNav});return;}
    if(button.dataset.amount){const input=document.getElementById('text-input');input.value=button.dataset.amount;input.focus();return;}
    if(button.hasAttribute('data-remove-photo')){selectedPhoto=null;const input=document.getElementById('photo-input');if(input)input.value='';paintPhoto();return;}
    if(button.dataset.nav)act({nav:button.dataset.nav});
    else if(button.dataset.action)act({action:button.dataset.action});
  });
  document.addEventListener('submit',async event=>{
    if(event.target.id!=='input-form')return;event.preventDefault();if(inFlight)return;
    const input={text:document.getElementById('text-input')?.value||''};
    const file=selectedPhoto;
    if(file){
      if(file.size>8*1024*1024){showNotice('Фото должно быть не больше 8 МБ.');return;}
      try{input.photo=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=reject;reader.readAsDataURL(file);});}catch{showNotice('Не удалось прочитать фото. Выберите файл ещё раз.');return;}
    }
    if(current.form.kind==='photo'&&!file){showNotice('Прикрепите фото.');return;}
    if(!file&&!input.text.trim()){showNotice('Введите значение.');return;}
    await act({input});
  });
  document.addEventListener('change',event=>{if(event.target.id!=='photo-input')return;const file=event.target.files?.[0];if(!file)return;if(file.size>8*1024*1024){showNotice('Фото должно быть не больше 8 МБ.');event.target.value='';return;}selectedPhoto=file;paintPhoto();});
  document.getElementById('refresh').addEventListener('click',()=>{
    if(!current){start();return;}
    if(current.busy){poll();return;}
    if(current.form||current.journey){poll();return;}
    const refreshButton=current.messages.flatMap(m=>m.rows.flat()).find(b=>b.action&&/обновить/i.test(b.label));
    if(refreshButton){act({action:refreshButton.action});return;}
    if(['home','paypal_request','my_paypals','wallet','profile','support','dt_payments','admin_home','wheel'].includes(current.route))act({nav:current.route});
    else poll();
  });
  document.getElementById('back').addEventListener('click',goBack);
  document.getElementById('notifications').addEventListener('click',openEvents);
  document.getElementById('close-notifications').addEventListener('click',()=>eventPanel.close());liveAlert.addEventListener('click',openEvents);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)refreshUpdates();else clearTimeout(updateTimer);});
  notice.tabIndex=0;notice.setAttribute('aria-label','Уведомление. Нажмите, чтобы закрыть');notice.addEventListener('click',()=>showNotice(''));notice.addEventListener('keydown',event=>{if(event.key==='Escape'||event.key==='Enter')showNotice('');});
  tg?.BackButton?.onClick(goBack);
  const viewport=()=>{document.documentElement.style.setProperty('--safe-bottom',Math.max(tg?.safeAreaInset?.bottom||0,tg?.contentSafeAreaInset?.bottom||0)+'px');document.documentElement.style.setProperty('--safe-top',(tg?.contentSafeAreaInset?.top||0)+'px');document.body.classList.toggle('keyboard-open',Boolean(window.visualViewport&&window.innerHeight-window.visualViewport.height>130));};
  window.visualViewport?.addEventListener('resize',viewport);tg?.onEvent?.('safeAreaChanged',viewport);tg?.onEvent?.('contentSafeAreaChanged',viewport);viewport();
  async function start(){
    if(!tg?.initData){
      document.getElementById('loading-label').textContent='Войдите через кнопку «Открыть Mini App» в боте.';
      if(!screen.querySelector('.entry-action'))screen.querySelector('.entry-copy').insertAdjacentHTML('beforeend','<a class="entry-action" href="https://t.me/DT_TEAM_PAYPAL_BOT">Открыть Telegram ↗</a>');return;
    }
    try{tg.ready();tg.expand();tg.setHeaderColor?.('#09090b');tg.setBackgroundColor?.('#09090b');tg.setBottomBarColor?.('#111014');
      const data=await request('/api/session',{init_data:tg.initData});token=data.token;try{const saved=JSON.parse(localStorage.getItem('dt-read-events-'+data.user.id)||'[]');readEvents=new Set(Array.isArray(saved)?saved:[]);}catch{}render(data);
    }catch(error){showNotice(error.message);document.getElementById('loading-label').textContent='Не удалось открыть кабинет.';}
  }
  start();
})();
