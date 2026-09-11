// Photopea's documented live-messaging API. INDD bytes stay in the local browser.
import { chromium } from 'playwright';
import { createServer } from 'node:http';
import { readFile, writeFile, appendFile, access } from 'node:fs/promises';
import { randomBytes } from 'node:crypto';

const [input, output, seconds = '240'] = process.argv.slice(2);
if (!input || !output) throw new Error('Usage: node photopea.mjs INPUT.indd OUTPUT.psd [timeout-seconds]');
const timeout = Number(seconds) * 1000;
if (!Number.isFinite(timeout) || timeout < 1000) throw new Error('Invalid timeout');
const token = randomBytes(24).toString('hex');
const prefix = '/' + token;
let resolveResult, rejectResult;
const result = new Promise((resolve, reject) => { resolveResult=resolve; rejectResult=reject; });
// Attach immediately, including while Chromium is still starting.
result.catch(() => {});
const html = `<!doctype html><meta charset="utf-8"><title>INDD conversion</title>
<p id="status">Loading conversion engine</p><iframe id="engine" style="width:1200px;height:850px"></iframe>
<script>
const engine=document.getElementById('engine'),status=document.getElementById('status');
let stage='boot';
async function fail(message){status.textContent=message;await fetch('${prefix}/error',{method:'POST',body:message});}
window.addEventListener('message',async event=>{
 if(event.source!==engine.contentWindow || event.origin!=='https://www.photopea.com')return;
 try{
  if(event.data instanceof ArrayBuffer){
   if(stage!=='export')return;
   stage='saving';status.textContent='Saving layered document';
   const chunkSize=4*1024*1024;
   for(let offset=0;offset<event.data.byteLength;offset+=chunkSize){
    const response=await fetch('${prefix}/chunk',{method:'POST',body:event.data.slice(offset,offset+chunkSize)});
    if(!response.ok)throw new Error('Could not save intermediate chunk');
   }
   await fetch('${prefix}/result',{method:'POST',body:String(event.data.byteLength)});stage='finished';return;
  }
  if(typeof event.data==='string' && event.data.startsWith('ERROR:')){await fail(event.data);return;}
  if(event.data!=='done')return;
  if(stage==='boot'){
   stage='import';status.textContent='Reading INDD';
   const data=await (await fetch('${prefix}/input')).arrayBuffer();
   engine.contentWindow.postMessage(data,'https://www.photopea.com');
  }else if(stage==='import'){
   stage='export';status.textContent='Exporting editable layers';
   engine.contentWindow.postMessage('try { if(app.documents.length!==1) throw new Error("No document imported"); app.activeDocument.saveToOE("psd"); } catch(e) { app.echoToOE("ERROR:"+e); }','https://www.photopea.com');
  }
 }catch(e){await fail(String(e));}
});
engine.src='https://www.photopea.com#'+encodeURIComponent(JSON.stringify({environment:{intro:false}}));
</script>`;
let received=0;
await writeFile(output,Buffer.alloc(0));
const server=createServer(async(req,res)=>{
 try{
  if(req.url===prefix+'/'){res.setHeader('Content-Type','text/html');res.end(html);return;}
  if(req.url===prefix+'/input'&&req.method==='GET'){res.end(await readFile(input));return;}
  if(req.method==='POST'&&[prefix+'/result',prefix+'/error',prefix+'/chunk'].includes(req.url)){
   const chunks=[];let length=0;
   for await(const chunk of req){length+=chunk.length;if(length>5*1024**2)throw new Error('Oversized transfer chunk');chunks.push(chunk);}
   const data=Buffer.concat(chunks);
   if(req.url.endsWith('/error')){rejectResult(new Error(data.toString()));res.end('error');return;}
   if(req.url.endsWith('/chunk')){
    if(received===0&&data.subarray(0,4).toString()!=='8BPS')throw new Error('Engine returned an invalid PSD');
    received+=data.length;if(received>1024**3)throw new Error('Intermediate exceeds 1 GiB');
    await appendFile(output,data);res.end('ok');return;
   }
   if(received<26||Number(data.toString())!==received)throw new Error('Incomplete intermediate');
   res.end('ok');resolveResult();return;
  }
  res.statusCode=404;res.end();
 }catch(e){res.statusCode=500;res.end('Conversion failed');rejectResult(e);}
});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
let browser;
const timer=setTimeout(()=>rejectResult(new Error('Photopea conversion timed out')),timeout);
try{
 let executablePath=process.env.INDD_CHROME;
 if(!executablePath&&process.platform==='darwin'){
  const chrome='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
  try{await access(chrome);executablePath=chrome;}catch{}
 }
 browser=await chromium.launch({headless:true,...(executablePath?{executablePath}:{})});
 const context=await browser.newContext({viewport:{width:1400,height:1000}});
 // No external write requests or WebSockets. GET requests load the engine/fonts.
 await context.route('**/*',route=>{
  const req=route.request(),url=new URL(req.url());
  if(url.hostname==='127.0.0.1'||['GET','HEAD'].includes(req.method()))return route.continue();
  return route.abort('blockedbyclient');
 });
 await context.routeWebSocket('**/*',socket=>socket.close());
 const page=await context.newPage();
 await page.goto(`http://127.0.0.1:${server.address().port}${prefix}/`,{waitUntil:'domcontentloaded'});
 await result;
 console.error('Read INDD with Photopea; saved local layered intermediate.');
}finally{
 clearTimeout(timer);
 await browser?.close();
 server.closeAllConnections();await new Promise(r=>server.close(r));
}
