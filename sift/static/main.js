/* main.js: start. */
'use strict';
(async () => {
  if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {});
  S.info = await api('/info');
  // de telefoonfuncties (QR, code) zijn alleen vanaf deze computer zelf te bedienen
  try { await api('/lan'); S.lanOk = true; } catch (e) { S.lanOk = false; $('#btnPhone').classList.add('hidden'); }
  const h = new URLSearchParams(location.hash.slice(1));
  if (h.get('p')) { try { await openProject(h.get('p'), h.get('v') || undefined); return; } catch (e) { toast('Interview niet gevonden'); } }
  show('home');
})();
