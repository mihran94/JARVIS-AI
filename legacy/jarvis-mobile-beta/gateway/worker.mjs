// Cloudflare Worker gateway: deploy with Wrangler, set secrets via wrangler secret put.
// Required: ACCESS_TOKEN. Optional cloud keys: GEMINI_API_KEY, OPENAI_API_KEY. Optional Ollama: OLLAMA_URL (private HTTPS), OLLAMA_MODEL.
// Set ALLOWED_ORIGIN to https://mihran94.github.io (no trailing slash).
const reply=(data,status=200,origin="")=>new Response(JSON.stringify(data),{status,headers:{"Content-Type":"application/json; charset=utf-8","Cache-Control":"no-store","Access-Control-Allow-Origin":origin,"Vary":"Origin","X-Content-Type-Options":"nosniff"}});
export default {async fetch(request,env){
 const origin=request.headers.get("Origin")||"";
 const allowed=env.ALLOWED_ORIGIN||"https://mihran94.github.io";
 if(origin!==allowed)return reply({error:"Origin not allowed"},403);
 if(request.method==="OPTIONS")return new Response(null,{status:204,headers:{"Access-Control-Allow-Origin":allowed,"Access-Control-Allow-Methods":"POST, OPTIONS","Access-Control-Allow-Headers":"Content-Type, Authorization","Access-Control-Max-Age":"600","Vary":"Origin"}});
 if(request.method!=="POST"||new URL(request.url).pathname!=="/chat")return reply({error:"Not found"},404,allowed);
 const auth=request.headers.get("Authorization")||"";
 if(!env.ACCESS_TOKEN||auth!=="Bearer "+env.ACCESS_TOKEN)return reply({error:"Unauthorized"},401,allowed);
 if(Number(request.headers.get("Content-Length")||0)>10000)return reply({error:"Too large"},413,allowed);
 let data;try{data=await request.json()}catch{return reply({error:"Invalid JSON"},400,allowed)}
 if(!data||!["gemini","openai","ollama"].includes(data.mode)||typeof data.message!=="string"||!data.message.trim()||data.message.length>2000)return reply({error:"Invalid input"},400,allowed);
 const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),25000);
 try{
  let endpoint,headers={"Content-Type":"application/json"},body;
  if(data.mode==="gemini"){
   if(!env.GEMINI_API_KEY)return reply({error:"Gemini not configured"},503,allowed);
   endpoint="https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent";
   headers["x-goog-api-key"]=env.GEMINI_API_KEY;
   body={contents:[{role:"user",parts:[{text:data.message}]}],generationConfig:{maxOutputTokens:700}};
  }else if(data.mode==="openai"){
   if(!env.OPENAI_API_KEY)return reply({error:"OpenAI not configured"},503,allowed);
   endpoint="https://api.openai.com/v1/responses";
   headers.Authorization="Bearer "+env.OPENAI_API_KEY;
   body={model:env.OPENAI_MODEL||"gpt-4.1-mini",instructions:"You are JARVIS Blue, a helpful private AI assistant. Respond primarily in natural Sri Lankan Tamil unless the user requests another language. Do not claim you have performed external actions.",input:data.message,max_output_tokens:700,store:false};
  }else{
   if(!env.OLLAMA_URL||!env.OLLAMA_URL.startsWith("https://"))return reply({error:"Private Ollama gateway not configured"},503,allowed);
   endpoint=env.OLLAMA_URL.replace(/\/$/,"")+"/api/chat";
   if(env.OLLAMA_TOKEN)headers.Authorization="Bearer "+env.OLLAMA_TOKEN;
   body={model:env.OLLAMA_MODEL||"llama3.2",messages:[{role:"user",content:data.message}],stream:false};
  }
  const upstream=await fetch(endpoint,{method:"POST",headers,body:JSON.stringify(body),signal:controller.signal});
  if(!upstream.ok)return reply({error:"AI provider error",status:upstream.status},502,allowed);
  const out=await upstream.json();
  const text=data.mode==="gemini"?out.candidates?.[0]?.content?.parts?.map(p=>p.text||"").join(""):data.mode==="openai"?(out.output||[]).flatMap(item=>item.content||[]).filter(part=>part.type==="output_text").map(part=>part.text||"").join(""):out.message?.content;
  return reply({reply:typeof text==="string"&&text?text:"No text response"},200,allowed);
 }catch{return reply({error:"AI request timed out or failed"},502,allowed)}
 finally{clearTimeout(timer)}
}};