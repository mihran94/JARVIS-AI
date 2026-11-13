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
const modeDescriptions={gemini:["Gemini · Gateway","Gemini uses your private gateway and cloud AI."],openai:["ChatGPT · Gateway","ChatGPT requires an OpenAI API key stored only as a Worker secret."],ollama:["Ollama · Gateway","Ollama requires a private authenticated connection to your Windows laptop."]};
function updateMode(){const [name,description]=modeDescriptions[mode.value];document.getElementById("engine").textContent=name;document.getElementById("modeNotice").textContent=description;}
mode.addEventListener("change",updateMode);updateMode();
const chatForm=document.getElementById("chatForm"),chat=document.getElementById("chat");
chatForm.addEventListener("submit",async event=>{
 event.preventDefault();
 const input=document.getElementById("prompt"),message=input.value.trim();
 if(!message)return;
 const gateway=document.getElementById("gateway").value.trim();
 const token=document.getElementById("accessToken").value.trim();
 if(!gateway||!token){chat.textContent+="\\nJARVIS: முதலில் Secure HTTPS Gateway மற்றும் Access Token அமைக்கவும்.";return;}
 let url;
 try{url=new URL(gateway);if(url.protocol!=="https:"||url.username||url.password||url.search||url.hash)throw Error("Invalid gateway");}
 catch{chat.textContent+="\\nJARVIS: செல்லுபடியான HTTPS Gateway URL தேவை.";return;}
 chat.textContent+="\\n\\nYOU: "+message+"\\nJARVIS: Connecting securely...";
 const button=chatForm.querySelector("button");button.disabled=true;
 const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),30000);
 try{
  const response=await fetch(url.href.replace(/\\/$/,"")+"/chat",{method:"POST",headers:{"Content-Type":"application/json","Authorization":"Bearer "+token},body:JSON.stringify({mode:mode.value,message}),signal:controller.signal,cache:"no-store"});
  if(!response.ok)throw Error("Gateway returned "+response.status);
  const data=await response.json();if(typeof data.reply!=="string")throw Error("Invalid gateway response");
  chat.textContent=chat.textContent.replace(/JARVIS: Connecting securely\.\.\.$/,"JARVIS: "+data.reply.slice(0,8000));input.value="";
 }catch(e){chat.textContent=chat.textContent.replace(/JARVIS: Connecting securely\.\.\.$/,"JARVIS: Connection failed ("+String(e.message||"network error").slice(0,100)+").");}
 finally{clearTimeout(timeout);button.disabled=false;chat.scrollTop=chat.scrollHeight;}
});
refresh();
