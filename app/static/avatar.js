(() => {
  const canvas = document.getElementById("avatar");
  const gl = canvas.getContext("webgl", {alpha: true, antialias: true});
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
  let paused = reduced.matches;
  let state = "idle", pulse = 0, targetX = 0, targetY = 0;
  window.jarvisAvatar = {
    setState(value) { state = value; document.body.dataset.state = value; },
    pulse() { pulse = 1; },
  };
  const motion = document.getElementById("motion");
  function syncMotion() { motion.textContent = paused ? "Animation fortsetzen" : "Animation pausieren"; motion.setAttribute("aria-pressed", String(paused)); }
  syncMotion();
  motion.onclick = () => { paused = !paused; syncMotion(); };
  reduced.addEventListener("change", () => { paused = reduced.matches; syncMotion(); });
  if (!gl) { canvas.hidden = true; document.getElementById("avatar-fallback").hidden = false; motion.hidden = true; return; }
  const vert = `
    attribute vec3 aPosition; attribute vec3 aColor; attribute float aGroup;
    uniform float uTime; uniform float uEnergy; uniform float uAspect;
    uniform vec2 uLook; varying vec3 vColor; varying float vDepth;
    void main(){
      vec3 p=aPosition;
      float turn=sin(uTime*.35)*.15+uLook.x*.22;
      if(aGroup<2.5){
        if(aGroup>1.5){p.y-=uEnergy*.055;}
        p=vec3(p.x*cos(turn)+p.z*sin(turn),p.y,p.z*cos(turn)-p.x*sin(turn));
        p.y+=sin(uTime*.8)*.022+uLook.y*.06;
      }else{
        float angle=uTime*(aGroup>3.5?-.13:.17);
        p.xz=mat2(cos(angle),-sin(angle),sin(angle),cos(angle))*p.xz;
      }
      float depth=4.8-p.z;
      gl_Position=vec4(p.x*2.15/uAspect/depth,(p.y+.2)*2.0/depth+.09,0.,1.);
      gl_PointSize=(aGroup>0.5&&aGroup<2.5?3.6:1.6)*(1.+uEnergy*.3);
      vColor=aColor*(.9+uEnergy*.24);
      vDepth=clamp((p.z+2.5)/4.,.18,1.);
    }`;
  const frag = `precision mediump float; varying vec3 vColor; varying float vDepth; uniform float uAlpha; void main(){gl_FragColor=vec4(vColor,vDepth*uAlpha);}`;
  function shader(type, code) { const s=gl.createShader(type);gl.shaderSource(s,code);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw Error("shader");return s; }
  let program;
  try { program=gl.createProgram();gl.attachShader(program,shader(gl.VERTEX_SHADER,vert));gl.attachShader(program,shader(gl.FRAGMENT_SHADER,frag));gl.linkProgram(program);if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw Error("link"); }
  catch { canvas.hidden=true;document.getElementById("avatar-fallback").hidden=false;return; }
  gl.useProgram(program);gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE);
  const lines=[],points=[];
  function vertex(array,p,c=[.36,.78,.71],g=0){array.push(...p,...c,g);}
  function segment(a,b,c,g=0){vertex(lines,a,c,g);vertex(lines,b,c,g);}
  function head(lat,lon){
    const y=Math.cos(lat),r=Math.sin(lat);
    const jaw=y<0?1+y*.2:1;
    const x=r*Math.sin(lon)*.72*jaw;
    let z=r*Math.cos(lon)*.65;
    if(z>0){
      const nose=Math.exp(-x*x/0.015-Math.pow(y+.05,2)/.08)*.25;
      const brow=Math.exp(-Math.pow(y-.27,2)/.012)*.035;
      z+=nose+brow;
    }
    return [x,y*.99+.48,z];
  }
  for(let i=1;i<32;i++)for(let j=0;j<52;j++){
    const a=head(Math.PI*i/32,Math.PI*2*j/52);
    const b=head(Math.PI*i/32,Math.PI*2*(j+1)/52);
    const c=head(Math.PI*(i+1)/32,Math.PI*2*j/52);
    segment(a,b,[.22,.55,.52]);segment(a,c,[.22,.55,.52]);vertex(points,a,[.42,.87,.77]);
  }
  for(const side of [-1,1]){
    for(let j=0;j<28;j++){
      const x=side*(.19+j*.009),y=.72+Math.sin(j/27*Math.PI)*.025;
      vertex(points,[x,y,.645],[.67,1,.90],1);
      if(j<27)segment([x,y,.645],[x+side*.009,y,.645],[.55,.95,.85],1);
    }
  }
  for(let j=0;j<28;j++){const x=-.18+j*.0133;vertex(points,[x,.12-Math.cos(x*7)*.025,.658],[.48,.88,.8],2);}
  // Neck and a geometric shoulder silhouette.
  for(let j=0;j<32;j++){
    const angle=j/32*Math.PI*2;
    segment([Math.cos(angle)*.22,-.45,Math.sin(angle)*.23],[Math.cos(angle)*.29,-.83,Math.sin(angle)*.3],[.16,.42,.4]);
  }
  for(let row=0;row<9;row++)for(let j=0;j<60;j++){
    const a=j/60*Math.PI*2,b=(j+1)/60*Math.PI*2;
    const r=.3+row*.12,y=-.83-row*.055;
    segment([Math.cos(a)*r,y,Math.sin(a)*r*.48],[Math.cos(b)*r,y,Math.sin(b)*r*.48],[.15,.4,.4]);
  }
  for(let ring=0;ring<3;ring++)for(let j=0;j<130;j++){
    if(j%25>19)continue;
    const a=j/130*Math.PI*2,b=(j+1)/130*Math.PI*2,r=1.32+ring*.18;
    segment([Math.cos(a)*r,-1.43+ring*.07,Math.sin(a)*r*.68],[Math.cos(b)*r,-1.43+ring*.07,Math.sin(b)*r*.68],ring===1?[.53,.4,.22]:[.2,.53,.5],3+ring%2);
  }
  let seed=7;function rand(){seed=(seed*16807)%2147483647;return seed/2147483647;}
  for(let n=0;n<160;n++)vertex(points,[(rand()-.5)*4,(rand()-.5)*3,(rand()-.5)*2],[.17,.4,.44],4);
  const lineBuffer=gl.createBuffer(),pointBuffer=gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER,lineBuffer);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(lines),gl.STATIC_DRAW);
  gl.bindBuffer(gl.ARRAY_BUFFER,pointBuffer);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(points),gl.STATIC_DRAW);
  const attrs=["aPosition","aColor","aGroup"].map(n=>gl.getAttribLocation(program,n));
  const uniforms=Object.fromEntries(["uTime","uEnergy","uAspect","uLook","uAlpha"].map(n=>[n,gl.getUniformLocation(program,n)]));
  function draw(buffer,mode,count,alpha){gl.bindBuffer(gl.ARRAY_BUFFER,buffer);attrs.forEach((a,i)=>{gl.enableVertexAttribArray(a);gl.vertexAttribPointer(a,i===2?1:3,gl.FLOAT,false,28,i*12);});gl.uniform1f(uniforms.uAlpha,alpha);gl.drawArrays(mode,0,count/7);}
  canvas.addEventListener("pointermove",e=>{const r=canvas.getBoundingClientRect();targetX=(e.clientX-r.left)/r.width-.5;targetY=.5-(e.clientY-r.top)/r.height;});
  canvas.addEventListener("pointerleave",()=>{targetX=0;targetY=0;});
  let clock=0,last=0,lookX=0,lookY=0;
  function frame(now){
    requestAnimationFrame(frame);
    if(document.hidden){last=now;return;}
    const dt=Math.min((now-last)/1000,.05);last=now;if(!paused)clock+=dt;
    const dpr=Math.min(devicePixelRatio||1,2),w=Math.round(canvas.clientWidth*dpr),h=Math.round(canvas.clientHeight*dpr);
    if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;gl.viewport(0,0,w,h);}
    lookX+=(targetX-lookX)*.04;lookY+=(targetY-lookY)*.04;
    pulse*=.93;
    const energy=paused?0:state==="speaking"?.3+Math.abs(Math.sin(clock*13))*.4+pulse*.3:state==="thinking"?.25+Math.sin(clock*3)*.12:state==="listening"?.35:0;
    gl.clear(gl.COLOR_BUFFER_BIT);gl.uniform1f(uniforms.uTime,clock);gl.uniform1f(uniforms.uEnergy,energy);gl.uniform1f(uniforms.uAspect,w/h);gl.uniform2f(uniforms.uLook,paused?0:lookX,paused?0:lookY);
    draw(lineBuffer,gl.LINES,lines.length,.38);draw(pointBuffer,gl.POINTS,points.length,.8);
  }
  requestAnimationFrame(frame);
})();

