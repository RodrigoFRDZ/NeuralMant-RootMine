(function(g){
let connection;
const open=()=>connection||(connection=new Promise((resolve,reject)=>{const r=indexedDB.open('neuralmant-campo-v1',1);r.onupgradeneeded=()=>{r.result.createObjectStore('settings');r.result.createObjectStore('outbox',{keyPath:'uuid'});};r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);}));
async function run(name,mode,fn){const db=await open();return new Promise((resolve,reject)=>{const tx=db.transaction(name,mode);let value;try{const req=fn(tx.objectStore(name));if(req)req.onsuccess=()=>value=req.result;}catch(e){tx.abort();reject(e);return;}tx.oncomplete=()=>resolve(value);tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error||new Error('No se pudo guardar en el dispositivo'));});}
g.CampoStore={get:k=>run('settings','readonly',s=>s.get(k)),put:(k,v)=>run('settings','readwrite',s=>s.put(v,k)),del:k=>run('settings','readwrite',s=>s.delete(k)),events:()=>run('outbox','readonly',s=>s.getAll()),add:e=>run('outbox','readwrite',s=>s.add(e)),update:e=>run('outbox','readwrite',s=>s.put(e)),remove:id=>run('outbox','readwrite',s=>s.delete(id)),open};
})(globalThis);
