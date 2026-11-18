window.mountDTGameStats = function(panel, request){
  panel.className='games-report';
  let page=0, uid=null, memberPage=0, name='', sequence=0;
  const when=at=>new Date(at).toLocaleString('ru-RU',{timeZone:'Europe/Moscow',dateStyle:'short',timeStyle:'short'});
  function element(parent,tag,value){
    const e=document.createElement(tag);e.textContent=value;parent.append(e);return e;
  }
  function button(parent,label,callback){const b=element(parent,'button',label);b.type='button';b.onclick=callback;}
  function totals(s){return 'Колесо: '+s.spins+' · Забегов: '+s.runs+' · Срывов: '+s.failed+' · Забрано с крыш: '+s.banked+' · В процессе: '+s.open;}
  async function show(){
    const serial=++sequence;
    panel.replaceChildren();element(panel,'p','Загружаем статистику…');
    try{
      const result=await request('/api/games/statistics?page='+page+(uid===null?'':'&uid='+uid));
      if(serial!==sequence||!panel.isConnected)return;
      panel.replaceChildren();
      element(panel,'h2',uid===null?'Статистика игр':name);
      element(panel,'p',totals(result.stats));
      element(panel,'p','Всего получено призов: '+result.stats.awards+' · Денежных призов: '+result.stats.cash+' USDT · Списано: '+result.stats.spent+' баллов');
      if(uid!==null)button(panel,'← Все участники',()=>{uid=null;page=memberPage;show();});
      if(!result.rows.length)element(panel,'p','Игровых попыток пока нет.');
      for(const row of result.rows){
        const item=element(panel,'article','');
        if(uid===null){
          const label=row.username?'@'+row.username:row.full_name||'Участник';
          element(item,'strong',label+' · ID '+row.uid);
          element(item,'small',totals(row));
          element(item,'small','Призов: '+row.awards+' · Потрачено: '+row.spent+' баллов');
          button(item,'История участника',()=>{memberPage=page;uid=row.uid;name=label+' · '+uid;page=0;show();});
        }else{
          const wheel=row.game==='wheel';
          const resultText=wheel?(row.cash?row.cash+' USDT':'+'+row.points+'%'):
            row.status==='lost'?'Срыв на крыше '+(row.level+1):
            row.status==='banked'?'Забрал +'+row.points+'%':'В процессе · крыша '+(row.level+1);
          element(item,'strong',(wheel?'Колесо':'Трос Альфа')+' · '+resultText);
          element(item,'small',when(row.at)+' МСК · −'+row.cost+' баллов');
          if(row.points)element(item,'small',row.applied?'Применён к оплате #'+row.applied:'В очереди на оплату');
        }
      }
      if(page>0)button(panel,'← Предыдущая',()=>{page--;show();});
      if(result.more)button(panel,'Следующая →',()=>{page++;show();});
      button(panel,'Обновить статистику',show);
    }catch(e){if(serial!==sequence||!panel.isConnected)return;panel.replaceChildren();element(panel,'p',e.message);button(panel,'Повторить',show);}
  }
  show();
};
