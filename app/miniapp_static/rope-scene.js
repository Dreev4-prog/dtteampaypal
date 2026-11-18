window.createRopeScene = function(canvas, geometry){
  const ctx=canvas.getContext('2d');
  const levels = [
    {sign:'HOTEL',sky:['#26283f','#685365','#c18b76'],moon:319},
    {sign:'LUNA',sky:['#262843','#574b6b','#ac7980'],moon:280},
    {sign:'XII',sky:['#192437','#414661','#987579'],moon:224},
    {sign:'DT',sky:['#171c30','#40374f','#88646b'],moon:305}
  ].map((art,i)=>({...art,...geometry[i]}));
  const roofY=192, gravity=525, anchor={x:154,y:22}, length=137, body=25;
  let level=0, mode='ready', swingStart=0, releaseAt=0, launch=null, lastX=null;
  let scaleX=1, scaleY=1, raf=0;
  const L=()=>levels[level];
  function swing(time) {
    const phase=time*L().speed, a=-.96*Math.cos(phase), v=.96*L().speed*Math.sin(phase);
    return {x:anchor.x+length*Math.sin(a),y:anchor.y+length*Math.cos(a)+body,
      vx:length*Math.cos(a)*v,vy:-length*Math.sin(a)*v,a};
  }
  function where(p,t){return {x:p.x+p.vx*t,y:p.y+p.vy*t+gravity*t*t/2};}
  const W=420,H=242;
  function poly(c,coords,color){
    c.beginPath();c.moveTo(coords[0],coords[1]);
    for(let i=2;i<coords.length;i+=2)c.lineTo(coords[i],coords[i+1]);
    c.closePath();c.fillStyle=color;c.fill();
  }
  function line(c,x,y,x2,y2,color,w=1){
    c.beginPath();c.moveTo(x,y);c.lineTo(x2,y2);c.strokeStyle=color;c.lineWidth=w;c.stroke();
  }
  function box(c,x,y,w,h,color){c.fillStyle=color;c.fillRect(x,y,w,h);}
  function oval(c,x,y,rx,ry,color,rotation=0){
    c.beginPath();c.ellipse(x,y,rx,ry,rotation,0,Math.PI*2);c.fillStyle=color;c.fill();
  }
  function ink(c,txt,x,y,font,colour,align='left'){
    c.save();c.font=font;c.fillStyle=colour;c.textAlign=align;c.fillText(txt,x,y);c.restore();
  }
  function noise(n){const k=Math.sin(n*73.17+1.5)*31227.14;return k-Math.floor(k);}
  function skyline(c){
    const l=L(), idx=level, grad=c.createLinearGradient(0,0,0,H);
    grad.addColorStop(0,l.sky[0]);grad.addColorStop(.56,l.sky[1]);grad.addColorStop(1,l.sky[2]);
    box(c,0,0,W,H,grad);
    for(let i=0;i<76;i++){
      const x=noise(i+41)*W, y=noise(i+105)*118;
      oval(c,x,y,i%9===0?.82:.45,i%9===0?.82:.45,i%9===0?'#e8cfae':'#b8a8aa');
    }
    const mx=l.moon,my=46+idx*1.8;
    const halo=c.createRadialGradient(mx,my,8,mx,my,65);
    halo.addColorStop(0,'#efc89928');halo.addColorStop(1,'#efc89900');
    box(c,mx-65,my-65,130,130,halo);
    oval(c,mx,my,19,19,'#ecd1ac');c.save();c.beginPath();c.arc(mx,my,19,0,7);c.clip();
    for(let i=0;i<21;i++)oval(c,mx-16+noise(i+804)*35,my-14+noise(i+994)*34,1+noise(i+601)*2.8,1.1,'#b797891c');
    for(let i=0;i<4;i++)line(c,mx-27,my+7+i*3,mx+24,my+7+i*3,'#8e78816b',.6);
    c.restore();
    for(let i=0;i<14;i++){
      const x=noise(i+213)*W,y=38+noise(i+244)*82;
      line(c,x,y,x+10+noise(i+270)*58,y-.8,'#cfafb11d',.8);
    }
    // Three distinct planes keep the playable ledges well in front of the city.
    for(let plane=0;plane<3;plane++){
      let x=-24;
      for(let i=0;x<W+4;i++){
        const seed=idx*51+i*6+plane*117, w=12+noise(seed+17)*(plane===2?27:18);
        const y=94+plane*29+noise(seed+23)*40;
        const fill=['#65566b','#484157','#302e43'][plane];
        box(c,x,y,w,H-y,fill);
        if(i%3===0){
          box(c,x+w*.18,y-4,w*.64,5,fill);box(c,x+w*.32,y-8,w*.36,6,fill);
          if(plane<2)line(c,x+w*.53,y-7,x+w*.53,y-19,fill,.9);
        }
        line(c,x+1,y+.5,x+w-1,y+.5,['#907489','#766374','#615467'][plane],.65);
        if(plane>0){
          for(let col=0;col<Math.floor(w/5)-1;col++)
            for(let row=0;y+7+row*8<H;row++){
              if(noise(seed+col*53+row*16)>.61)box(c,x+3+col*5,y+5+row*8,1.5,2.2,['','#c59d863e','#e2b48a75'][plane]);
            }
        }
        x+=w+noise(seed+36)*6;
      }
    }
    // An Art Deco tower anchors the neighbourhood as the route moves on.
    const tx=[219,104,269,111][idx],ty=[91,99,97,90][idx];
    box(c,tx-9,ty+16,18,H-ty,'#393447');box(c,tx-6,ty+8,12,13,'#393447');
    poly(c,[tx-5,ty+8,tx,ty-2,tx+5,ty+8],'#504456');
    line(c,tx,ty,tx,ty-13,'#665567',.9);oval(c,tx,ty-13,.85,.85,'#d69b91');
    for(let i=-1;i<=1;i++)line(c,tx+i*4,ty+23,tx+i*4,ty+54,'#b89a827a',1);
  }
  function crane(c){
    poly(c,[0,20,19,20,19,125,9,125,9,33,0,33],'#22222c');
    poly(c,[0,21,33,8,99,6,156,15,156,20,88,14,35,17,0,30],'#35313a');
    line(c,0,21,34,8,'#a38b7c',1.1);line(c,34,8,99,6,'#a38b7c',1.1);line(c,99,6,156,15,'#a38b7c',1);
    for(let i=0;i<8;i++){
      const x=28+i*15,top=x<99?8-(x-34)*.031:6+(x-99)*.158;
      line(c,x,top+1,x+8,top+8,'#8c796d',.9);line(c,x+8,top+8,x+15,top+1.5,'#8c796d',.9);
    }
    for(let i=0;i<7;i++)line(c,9,32+i*12,19,42+i*12,'#695e61',1.1);
    box(c,151,15,6,8,'#57494a');oval(c,anchor.x,anchor.y,3.6,3.6,'#d7b987');oval(c,anchor.x,anchor.y,1.7,1.7,'#342d32');
  }
  const startY=anchor.y+length*Math.cos(-.96)+body;
  function startBuilding(c){
    const y=startY;
    box(c,0,y+3,39,H-y,'#25252e');box(c,0,y+8,39,3,'#5d4f50');
    box(c,0,y,42,4,'#413942');line(c,0,y,42,y,'#c3aa8e',1.1);
    for(let j=0;j<5;j++)for(let k=0;k<2;k++){
      const x=3+k*17,yy=y+17+j*21;
      box(c,x,yy,15,14,'#433940');box(c,x+2,yy+2,11,10,(j+k)%3===0?'#be9476':'#61515a');
      box(c,x+6,yy+2,1.5,10,'#433940');box(c,x+2,yy+6,11,1.2,'#433940');
    }
    line(c,38,y+10,38,H,'#7c6863',1);
  }
  function destination(c){
    const l=L(),x=l.left,w=l.right-x,y=roofY,mid=x+w/2;
    // Everything below the luminous lip is architecture, never a second landing surface.
    box(c,x+2,y+5,w-4,H-y,'#25232c');
    box(c,x+1,y+6,w-2,4,'#664b4b');
    if(level===3){
      poly(c,[x+2,y+8,x+6,y+21,x+w-6,y+21,x+w-2,y+8],'#50353a');
      line(c,x+4,y+11,x+w-4,y+11,'#a97c66',1);
      box(c,mid-4,y+21,8,35,'#4b393e');
    }else {
      for(let f=0;f<Math.max(2,Math.floor(w/9));f++){
        const fx=x+3+f*((w-5)/Math.max(2,Math.floor(w/9)));
        box(c,fx,y+13,2.5,H-y-13,'#59464a');
      }
    }
    box(c,x,y+.8,w,3.4,'#a7774d');box(c,x,y-.6,w,2.1,'#ffe1a0');
    for(const px of [x+.5,x+w-.5]){
      line(c,px,y-1,px,y-5,'#eabe79',1.2);
      oval(c,px,y-5.5,1.4,1.4,'#fff0c4');
    }
    if(level===2){
      oval(c,mid,y+23,8,8,'#ac8a6c');oval(c,mid,y+23,6.7,6.7,'#342c36');
      line(c,mid,y+23,mid-2,y+19,'#efd5a4',.85);line(c,mid,y+23,mid+4,y+22,'#efd5a4',.85);
    }else{
      const panelW=Math.min(w-3,48);
      box(c,mid-panelW/2,y+16,panelW,14,'#342830');
      line(c,mid-panelW/2,y+15,mid+panelW/2,y+15,'#986e60',.7);
      ink(c,l.sign,mid,y+26,level===3?'italic bold 9px Georgia':'bold 8px Georgia','#d9b68e','center');
    }
  }
  let backdrop=null,backKey='';
  function background(){
    const key=[level,canvas.width,canvas.height].join('-');
    if(key!==backKey){
      backdrop=document.createElement('canvas');backdrop.width=canvas.width;backdrop.height=canvas.height;
      const c=backdrop.getContext('2d');c.scale(scaleX,scaleY);
      skyline(c);crane(c);startBuilding(c);destination(c);backKey=key;
    }
    ctx.drawImage(backdrop,0,0,W,H);
  }
  function drawAlf(p,pose){
    const c=ctx;
    c.save();c.translate(p.x,p.y);c.scale(1.14,1.14);
    const raised=pose==='swing',flying=pose==='fly',celebrate=pose==='win';
    if(flying)c.rotate(p.vx<0?-.18:.16);
    // Swept fur, ridged muzzle, tuxedo lapels and two distinct shoes at the landing point.
    const heel=flying||raised?3:0;
    poly(c,[-5,-10,1,-10,-1,-3-heel,-5,-heel,-8,-heel],'#0f111b');
    poly(c,[0,-10,5,-10,4,-4+heel*.3,7,-1,3,0,-1,-4],'#232027');
    oval(c,-5,-1-heel,3.5,1.35,'#110e15');oval(c,5,-.8,3.6,1.25,'#17131b');
    line(c,3,0,8,0,'#a58673',.6);
    poly(c,[-5,-18,1,-19,5,-16,6,-8,0,-7,-5,-8,-7,-6],'#211f2a');
    poly(c,[-2,-18,2,-18,1.5,-12],'#f0d8ac');
    poly(c,[-4,-18,-1,-17,1,-11,-3,-14,-2,-15],'#75646a');
    poly(c,[2,-17,4,-16,2,-12,1,-11],'#60535b');
    line(c,-5,-10,-1,-9,'#9e826c',.65);
    poly(c,[-1,-17,2,-16,.6,-14,-.8,-15.5],'#844146');
    const arm=(points)=>{
      c.beginPath();c.moveTo(points[0],points[1]);c.lineTo(points[2],points[3]);c.lineTo(points[4],points[5]);
      c.lineWidth=3.7;c.strokeStyle='#292631';c.lineCap='round';c.stroke();
      oval(c,points[4],points[5],1.85,1.55,'#cc9764');
    };
    arm(raised?[-4,-16,-7,-20,0,-body/1.14]:flying?[-4,-16,-8,-13,-12,-15]:[-4,-15,-6,-10,-6,-8]);
    oval(c,-2.3,-22.4,6.15,5.8,'#ae6b43',-.15);
    poly(c,[-7,-22,-11,-27,-7,-29,-4,-25],'#cf9769');poly(c,[-7.3,-24,-9.4,-26.7,-7.5,-27.5,-5.9,-25],'#694537');
    poly(c,[-7,-26,-8,-30,-4,-28,-5,-32,-1,-29,1,-31,2,-27,4,-27,2,-25],'#b67748');
    line(c,-6.3,-28,-4,-26.5,'#f0b67a',.8);line(c,-3.2,-29.7,-.9,-27.2,'#e4a76a',.8);
    oval(c,3.9,-21,6,3.6,'#d69b68',.13);oval(c,8.6,-20.9,2.3,2.05,'#62463e');
    for(let i=0;i<3;i++)line(c,2.2+i*1.5,-23,1.6+i*1.5,-21,'#94613f',.6);
    line(c,1,-18.9,6,-18.2,'#825339',.7);oval(c,1,-24.6,1.4,1.5,'#2c2224');oval(c,1.45,-25,.43,.43,'#f8e8c8');
    if(raised)arm([3,-15,6,-18,0,-body/1.14]);
    else if(flying)arm([3,-15,8,-17,12,-20]);
    else arm(celebrate?[3,-16,7,-20,8,-25]:[3,-15,5,-11,5,-9]);
    c.restore();
  }
  function markTarget(){
    const mid=(L().left+L().right)/2;
    if(mode==='landed'||mode==='banked')return;
    const c=ctx;c.save();c.translate(mid,roofY-17);
    poly(c,[-4,-3,0,0,4,-3,4,-1,0,2,-4,-1],'#ffe2a1');
    c.restore();
  }
  function draw(now){
    ctx.setTransform(scaleX,0,0,scaleY,0,0);background();
    const resting=swing(0);
    let p=resting,ropePoint=resting,pose='idle';
    if(mode==='swing'){p=swing(Math.max(0,(now-swingStart)/1000));ropePoint=p;pose='swing';}
    if(mode==='flight'){
      const t=Math.max(0,(now-releaseAt)/1000);
      p={...where(launch,t),vx:launch.vx};pose='fly';
      const a=launch.a*Math.cos(t*2.8)*Math.exp(-t*.65);
      ropePoint={x:anchor.x+length*Math.sin(a),y:anchor.y+length*Math.cos(a)+body};
      ctx.save();ctx.beginPath();
      for(let i=0;i<8;i++){const q=where(launch,Math.max(0,t-.15+i*.02));if(i===0)ctx.moveTo(q.x,q.y-14);else ctx.lineTo(q.x,q.y-14);}
      ctx.strokeStyle='#f3d19b80';ctx.lineWidth=1;ctx.setLineDash([2,3]);ctx.stroke();ctx.restore();
    }
    if(mode==='landed'||mode==='banked'){
      p={x:lastX??(L().left+L().right)/2,y:roofY};pose='win';
    }
    const handY=ropePoint.y-body;
    line(ctx,anchor.x+.8,anchor.y,ropePoint.x+.8,handY,'#29252caf',2.7);
    line(ctx,anchor.x,anchor.y,ropePoint.x,handY,'#e6c890',1.3);
    oval(ctx,ropePoint.x,handY,1.8,1.8,'#d2aa72');
    markTarget();
    if(mode!=='lost'&&p.y<H+28)drawAlf(p,pose);
    if(mode==='lost'&&lastX!==null){
      const x=Math.min(W-8,Math.max(8,lastX));line(ctx,x-3,roofY-4,x+3,roofY+2,'#ffc1a5',1.7);line(ctx,x-3,roofY+2,x+3,roofY-4,'#ffc1a5',1.7);
    }
  }
  function resize(){
    const dpr=Math.min(window.devicePixelRatio||1,3),box=canvas.getBoundingClientRect();
    if(!box.width||!box.height)return;
    const w=Math.round(box.width*dpr),h=Math.round(box.height*dpr);
    if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;}
    scaleX=w/W;scaleY=h/H;draw(performance.now());
  }

  function frame(now){
    if(!canvas.isConnected)return;
    draw(now);
    if(mode==='swing'||(mode==='flight'&&now-releaseAt<1300))raf=requestAnimationFrame(frame);
  }
  const observer=new ResizeObserver(resize);
  observer.observe(canvas);resize();
  return {
    show(run){cancelAnimationFrame(raf);level=run?.level??0;mode=run?.state==='swing'?'ready':run?.state??'ready';lastX=run?.landing_x??null;draw(performance.now());},
    hold(){cancelAnimationFrame(raf);swingStart=performance.now();mode='swing';frame(swingStart);},
    fly(){releaseAt=performance.now();launch=swing((releaseAt-swingStart)/1000);mode='flight';},
    destroy(){cancelAnimationFrame(raf);observer.disconnect();}
  };
};
