importScripts('./assets/store.js','./assets/sync.js');
const CACHE='neuralmant-campo-4.8.0';const ROOT=new URL('./',self.location).pathname;
self.addEventListener('install',event=>event.waitUntil(caches.open(CACHE).then(c=>c.addAll([ROOT,ROOT+'assets/campo.css',ROOT+'assets/app.js',ROOT+'assets/store.js',ROOT+'assets/sync.js'])).then(()=>self.skipWaiting())));
self.addEventListener('activate',event=>event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k.startsWith('neuralmant-campo-')&&k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',event=>{const url=new URL(event.request.url);if(url.origin!==location.origin||!url.pathname.startsWith(ROOT)||url.pathname.includes('/api/')||event.request.method!=='GET')return;
if(event.request.mode==='navigate'){event.respondWith(caches.match(ROOT).then(cached=>cached||fetch(event.request)));return;}
event.respondWith(caches.match(event.request).then(cached=>cached||fetch(event.request)));});
self.addEventListener('sync',event=>{if(event.tag==='neuralmant-campo-sync')event.waitUntil(CampoSync.sincronizar());});
