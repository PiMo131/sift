/* main.js: start. */
'use strict';
(async () => {
  S.info = await api('/info');
  const h = new URLSearchParams(location.hash.slice(1));
  if (h.get('p')) { try { await openProject(h.get('p'), h.get('v') || undefined); return; } catch (e) { toast('Interview niet gevonden'); } }
  show('home');
})();
