"use strict";
const canvas=document.getElementById("orb"),ctx=canvas.getContext("2d");
const mode=document.getElementById("mode"),motion=document.getElementById("motion"),saving=document.getElementById("saving");
const reduced=window.matchMedia("(prefers-reduced-motion: reduce)");
let tick=0,frame=0,last=0;
function draw(t){
 if(document.hidden)return;
 const interval=saving.checked?180:50;
 if(t-last>=interval){last=t;tick+=saving.checked?.025:.055;ctx.clearRect(0,0,300,300);
 const x=150,y=150;
 for(let i=0;i<4;i++){const r=108-i*22+(motion.checked&&!reduced.matches?Math.sin(tick+i)*4:0);
 ctx.beginPath();ctx.arc(x,y,r,0,Math.PI*2);ctx.strokeStyle=["#173d5b","#1d6685","#128fb6","#57e4ff"][i];ctx.lineWidth=i===3?3:2;ctx.stroke();}
 const grad=ctx.createRadialGradient(x,y,10,x,y,46);grad.addColorStop(0,"#128fb6");grad.addColorStop(1,"#073650");
 ctx.fillStyle=grad;ctx.beginPath();ctx.arc(x,y,43,0,Math.PI*2);ctx.fill();
 ctx.font="bold 46px system-ui";ctx.textAlign="center";ctx.textBaseline="middle";ctx.fillStyle="#f1f8ff";ctx.fillText("J",x,y);
 }
 if(motion.checked&&!reduced.matches)frame=requestAnimationFrame(draw);
}
function refresh(){cancelAnimationFrame(frame);draw(performance.now());}
motion.addEventListener("change",refresh);saving.addEventListener("change",refresh);
reduced.addEventListener?.("change",refresh);
document.addEventListener("visibilitychange",()=>{if(!document.hidden)refresh();else cancelAnimationFrame(frame);});
mode.addEventListener("change",()=>{const cloud=mode.value==="gemini";
 document.getElementById("engine").textContent=cloud?"Gemini · Demo":"Local Ollama · Demo";
 document.getElementById("modeNotice").textContent=cloud?"Gemini selected for UI preview only. No cloud connection or API key.":"Local Ollama selected for UI preview only. No backend connected.";
});
document.getElementById("chatForm").addEventListener("submit",event=>{event.preventDefault();const input=document.getElementById("prompt"),value=input.value.trim();if(!value)return;
 const chat=document.getElementById("chat");chat.textContent+="\n\nYOU: "+value+"\nJARVIS: செய்தி கிடைத்தது. இது UI Demo மட்டுமே; AI பதில் இல்லை.";input.value="";chat.scrollTop=chat.scrollHeight;});
refresh();