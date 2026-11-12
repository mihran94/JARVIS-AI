// JARVIS bridge v1. Secrets are never persisted or logged.
const $=id=>document.getElementById(id);
const enc=new TextEncoder();
const hex=bytes=>Array.from(new Uint8Array(bytes),b=>b.toString(16).padStart(2,'0')).join('');
async function sha256(value){return hex(await crypto.subtle.digest('SHA-256',enc.encode(value)));}
async function signature(method,path,timestamp,nonce,body,secret){
 const canonical=[method.toUpperCase(),path,timestamp,nonce,await sha256(body)].join('\n');
 const key=await crypto.subtle.importKey('raw',enc.encode(secret),{name:'HMAC',hash:'SHA-256'},false,['sign']);
 return hex(await crypto.subtle.sign('HMAC',key,enc.encode(canonical)));
}
async function request(path){
 const base=$('url').value.trim().replace(/\/+$/,'');
 const key=$('key').value.trim(),secret=$('secret').value;
 if(!base.startsWith('https://')||!key||secret.length<32)throw Error('Enter an HTTPS bridge URL, device key ID and 32+ character approved secret.');
 const parsed=new URL(base);
 if(parsed.username||parsed.password||parsed.search||parsed.hash)throw Error('Use a clean HTTPS bridge URL.');
 const nonce=hex(crypto.getRandomValues(new Uint8Array(16)));
 const timestamp=String(Date.now()),body='';
 const headers={'X-Jarvis-Key-Id':key,'X-Jarvis-Timestamp':timestamp,'X-Jarvis-Nonce':nonce,'X-Jarvis-Signature':await signature('GET',path,timestamp,nonce,body,secret)};
 const response=await fetch(base+path,{method:'GET',headers,cache:'no-store',credentials:'omit',redirect:'error'});
 if(!response.ok)throw Error('Bridge returned HTTP '+response.status);
 return response.json();
}
async function execute(button,path,target){button.disabled=true;$(target).textContent='Connecting…';try{const data=await request(path);$(target).textContent=JSON.stringify(data,null,2);}catch(error){$(target).textContent='Connection failed: '+error.message;}finally{button.disabled=false;}}
$('connect').addEventListener('click',()=>execute($('connect'),'/api/status','status'));
$('refresh').addEventListener('click',()=>execute($('refresh'),'/api/jobs','jobs'));
if('serviceWorker' in navigator)navigator.serviceWorker.register('./sw.js').catch(()=>{});
