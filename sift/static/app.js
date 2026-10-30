/* Sift — lokale interviewtranscriptie. Vanilla JS, geen build-stap.
   app.js: hulpfuncties, toestand, navigatie, automatisch opslaan (Saver), ongedaan maken (History), startpagina. */
'use strict';

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const api = async (path, opt = {}) => {
  const r = await fetch('/api' + path, opt);
  if (!r.ok) { let m = r.statusText; try { m = (await r.json()).detail || m; } catch (e) {} throw new Error(m); }
  const ct = r.headers.get('content-type') || '';
  return ct.includes('json') ? r.json() : r;
};
const post = (path, body) => api(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) });
const put = (path, body) => api(path, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) });
const del = path => api(path, { method: 'DELETE' });
const fmtT = (s, ms = false) => { if (s == null || isNaN(s)) return '--:--'; const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), sec = s % 60; const b = `${String(m).padStart(2, '0')}:${ms ? sec.toFixed(1).padStart(4, '0') : String(Math.floor(sec)).padStart(2, '0')}`; return h ? `${h}:${b}` : b; };
const fmtHMS = s => { s = Math.max(0, s || 0); const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), sec = Math.floor(s % 60); return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`; };
const fmtDur = s => { if (s == null) return ''; s = Math.round(s); if (s < 60) return `${s} s`; const m = Math.round(s / 60); return m < 60 ? `${m} min` : `${Math.floor(m / 60)} u ${m % 60} min`; };
const parseMMSS = v => { if (v == null || v === '') return null; const p = String(v).trim().split(':').map(Number); if (p.some(isNaN)) return null; return p.length === 1 ? p[0] : p.length === 2 ? p[0] * 60 + p[1] : p[0] * 3600 + p[1] * 60 + p[2]; };
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const normW = w => (w || '').toLowerCase().replace(/[^\p{L}\p{N}']/gu, '');
const deep = o => JSON.parse(JSON.stringify(o));
const SPEAKER_COLORS = ['#2b6cb0', '#9f3fbf', '#2f855a', '#c05621', '#b7791f', '#2c7a7b', '#702459', '#4a5568'];
let toastT; const toast = m => { let t = $('.toast'); if (!t) { t = document.createElement('div'); t.className = 'toast'; t.setAttribute('role', 'status'); document.body.appendChild(t); } t.textContent = m; clearTimeout(toastT); toastT = setTimeout(() => t.remove(), 3200); };
const pref = { get: (k, d) => { try { const v = localStorage.getItem('sift.' + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } }, set: (k, v) => { try { localStorage.setItem('sift.' + k, JSON.stringify(v)); } catch (e) {} } };

const S = {
  info: null, projects: [], studies: [], pid: null, meta: null, tr: null, runs: null, view: 'home',
  threshold: 0.6, heat: pref.get('heat', true), curWord: null, curSeg: null, curPoint: null, dirty: false, pollTimer: null,
  playWindow: null, wasPlaying: false, typingTimer: null, peaks: [], loopSel: null, style: 'verbatim',
  filters: pref.get('filters', { uncertain: true, disagree: true, later: true, gap: true, done: false }),
  panels: pref.get('panels', { side: true, right: window.innerWidth >= 1100 }),  // op kleine schermen (of 150 % zoom) start het rechterpaneel ingeklapt
};
const audio = $('#audio');

/* ======================= dialogen ======================= */
function modal(html, opts = {}) {
  const m = document.createElement('div'); m.className = 'modal'; m.innerHTML = `<div class="box ${opts.wide ? 'wide' : ''}" role="dialog" aria-modal="true" ${opts.label ? `aria-label="${esc(opts.label)}"` : ''}>${html}</div>`;
  m.onclick = e => { if (e.target === m && !opts.sticky) m.remove(); };
  m.addEventListener('keydown', e => { if (e.key === 'Escape') { e.stopPropagation(); m.remove(); } });
  document.body.appendChild(m);
  const f = m.querySelector('input,select,textarea,button'); if (f) f.focus();
  return m;
}
function confirmBox(text, okLabel = 'Ja', cancelLabel = 'Annuleren') {
  return new Promise(res => { const m = modal(`<p style="margin:0 0 14px">${esc(text)}</p><div class="actions"><button class="btn primary" id="cOk">${esc(okLabel)}</button><button class="btn" id="cNo">${esc(cancelLabel)}</button></div>`, { sticky: true }); $('#cOk', m).onclick = () => { m.remove(); res(true); }; $('#cNo', m).onclick = () => { m.remove(); res(false); }; });
}
function promptBox(label, value = '') {
  return new Promise(res => { const m = modal(`<div class="form"><label for="pIn">${esc(label)}</label><input type="text" id="pIn" value="${esc(value)}"><div class="actions"><button class="btn primary" id="pOk">OK</button><button class="btn" id="pNo">Annuleren</button></div></div>`, { sticky: true }); $('#pIn', m).onkeydown = e => { if (e.key === 'Enter') $('#pOk', m).click(); }; $('#pOk', m).onclick = () => { const v = $('#pIn', m).value; m.remove(); res(v); }; $('#pNo', m).onclick = () => { m.remove(); res(null); }; });
}
const inDialogOrField = e => !!(e.target.closest && (e.target.closest('.modal') || e.target.closest('.pop') || (e.target.matches('input,select,textarea') && !e.target.closest('.txt'))));

/* ======================= navigatie ======================= */
function show(view) {
  S.view = view;
  $$('.view').forEach(v => v.classList.toggle('hidden', v.id !== 'view-' + view));
  $$('.tab').forEach(t => { t.classList.toggle('on', t.dataset.view === view); t.setAttribute('aria-current', t.dataset.view === view ? 'page' : 'false'); });
  $('#topActions').innerHTML = '';
  if (view === 'home') loadHome();
  if (view === 'process') renderProcess();
  if (view === 'editor') renderEditor();
  if (view === 'compare') renderCompare();
  if (view === 'export') renderExport();
  if (S.pid && view !== 'home') history.replaceState(null, '', `#p=${encodeURIComponent(S.pid)}&v=${view}`); else history.replaceState(null, '', location.pathname);
}
$$('.tab').forEach(t => t.onclick = async () => { if (!(await Saver.leaveGuard())) return; show(t.dataset.view); });
function enableTabs(on, hasTranscript) { $$('.tab').forEach(t => { if (t.dataset.view === 'home') return; t.disabled = !on || (!hasTranscript && ['editor', 'compare', 'export'].includes(t.dataset.view)); }); }

/* ======================= automatisch opslaan ======================= */
/* Toestanden: clean | dirty (wijzigingen aanwezig) | saving | saved | failed.
   - vóór elke opslag wordt het actieve tekstvak naar S.tr vastgelegd (commitActiveSegment);
   - elke opslag krijgt een token én de project-id: een laat antwoord van een ander interview of een oudere poging
     kan nooit 'opgeslagen' tonen of gegevens van het huidige interview overschrijven;
   - wijzigingen tijdens een lopende opslag blijven 'dirty' en worden daarna opnieuw opgeslagen;
   - bij een fout: status 'mislukt', automatische nieuwe poging met oplopende wachttijd, knop 'Opnieuw'. */
const Saver = {
  state: 'clean', token: 0, inflight: null, timer: null, retryTimer: null, retries: 0, lastError: '',
  set(state, extra = '') {
    this.state = state;
    const el = $('#saveState'); if (!el) return;
    el.className = 'save ' + state;
    const txt = { clean: '', dirty: '● Wijzigingen aanwezig', saving: '● Bezig met opslaan…', saved: `✓ Opgeslagen ${new Date().toLocaleTimeString().slice(0, 5)}${extra}`, failed: `✖ Opslaan mislukt: ${extra}` }[state];
    el.innerHTML = esc(txt) + (state === 'failed' ? ' <button class="btn small" id="saveRetry">Opnieuw</button>' : '');
    if (state === 'failed') $('#saveRetry').onclick = () => Saver.save({ force: true });
  },
  markDirty() { S.dirty = true; if (this.state !== 'saving') this.set('dirty'); clearTimeout(this.timer); this.timer = setTimeout(() => this.save(), 1500); },
  async save({ force = false } = {}) {
    clearTimeout(this.timer);
    if (!S.tr || !S.pid) return true;
    if (typeof commitActiveSegment === 'function') commitActiveSegment();
    if (!S.dirty && !force) return true;
    if (this.inflight) return this.inflight;           // loopt al; markDirty hield S.dirty op true → volgt vanzelf
    const pid = S.pid, token = ++this.token, body = JSON.stringify({ ...S.tr, client_token: token });
    S.dirty = false; this.set('saving');
    this.inflight = (async () => {
      let ok = false;
      try {
        const r = await api(`/projects/${pid}/transcript`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body });
        ok = true;
        if (S.pid !== pid || r.project !== pid) return true;   // antwoord hoort bij een ander (inmiddels gesloten) interview
        if (r.client_token !== token || token !== this.token) return true; // ouder antwoord: niets tonen
        S.tr.version = r.version; this.retries = 0;
        if (S.dirty) this.set('dirty'); else this.set('saved', ` · versie ${r.version}`);
      } catch (e) {
        if (S.pid === pid) { S.dirty = true; this.lastError = e.message; this.set('failed', e.message); this.retries++; clearTimeout(this.retryTimer); this.retryTimer = setTimeout(() => this.save(), Math.min(30000, 2000 * 2 ** (this.retries - 1))); }
      } finally {
        this.inflight = null;
        if (ok && S.dirty && S.pid === pid) { this.timer = setTimeout(() => this.save(), 300); }
      }
      return ok;
    })();
    return this.inflight;
  },
  async flush() { clearTimeout(this.timer); clearTimeout(this.retryTimer); if (this.inflight) await this.inflight; if (typeof commitActiveSegment === 'function') commitActiveSegment(); if (!S.dirty) return true; return this.save({ force: true }); },
  reset() { clearTimeout(this.timer); clearTimeout(this.retryTimer); this.token++; this.retries = 0; S.dirty = false; this.set('clean'); },  // na laden/herstellen: niets mag nog nalopen
  async leaveGuard() {
    if (!S.tr) return true;
    const ok = await this.flush();
    if (ok) return true;
    return confirmBox(`Opslaan is mislukt (${this.lastError}). Als je nu verder gaat, gaan de laatste wijzigingen verloren. Blijf hier om het opnieuw te proberen.`, 'Toch verder (wijzigingen verliezen)', 'Hier blijven');
  },
};
window.addEventListener('beforeunload', e => {
  if (!S.tr || !S.pid) return;
  if (typeof commitActiveSegment === 'function') commitActiveSegment();
  if (S.dirty || Saver.inflight) {
    try { navigator.sendBeacon(`/api/projects/${S.pid}/transcript/beacon`, new Blob([JSON.stringify({ ...S.tr, client_token: 'beacon' })], { type: 'application/json' })); } catch (err) {}
    e.preventDefault(); e.returnValue = '';
  }
});
setInterval(() => { if (S.dirty && Saver.state !== 'saving' && Saver.state !== 'failed') Saver.save(); }, 10000);

/* ======================= ongedaan maken / opnieuw ======================= */
/* Elke bewerking van het transcript loopt via edit(from, count, fn): vóór en na worden de geraakte segmenten (en de
   sprekerlijst) gekopieerd. Ongedaan maken zet precies die reeks terug en rendert opnieuw vanuit de toestand, dus
   ook na opnieuw renderen van een segment blijft het betrouwbaar. */
const History = {
  undo: [], redo: [], max: 100,
  edit(from, count, fn, label = '') {
    if (!S.tr) return;
    const segs = S.tr.segments, lenBefore = segs.length;
    const before = { from, items: deep(segs.slice(from, from + count)), speakers: deep(S.tr.speakers || {}) };
    fn();
    const countAfter = count + (segs.length - lenBefore);
    const after = { from, items: deep(segs.slice(from, from + countAfter)), speakers: deep(S.tr.speakers || {}) };
    this.undo.push({ before, after, label }); if (this.undo.length > this.max) this.undo.shift();
    this.redo = []; Saver.markDirty();
  },
  apply(st, other) {
    S.tr.segments.splice(st.from, other.items.length, ...deep(st.items));
    S.tr.speakers = deep(st.speakers);
    S.curWord = null; S.curSeg = Math.min(st.from, S.tr.segments.length - 1);
    Saver.markDirty(); renderEditor();
    const el = $(`#seg${st.from}`); if (el) el.scrollIntoView({ block: 'center' });
  },
  doUndo() { if (typeof commitActiveSegment === 'function') commitActiveSegment(); const op = this.undo.pop(); if (!op) return toast('Niets om ongedaan te maken'); this.redo.push(op); this.apply(op.before, op.after); toast('Ongedaan gemaakt' + (op.label ? ': ' + op.label : '')); },
  doRedo() { const op = this.redo.pop(); if (!op) return toast('Niets om opnieuw te doen'); this.undo.push(op); this.apply(op.after, op.before); toast('Opnieuw: ' + (op.label || 'bewerking')); },
  clear() { this.undo = []; this.redo = []; },
};

/* ======================= project openen ======================= */
async function openProject(id, view) {
  if (!(await Saver.leaveGuard())) return;
  clearTimeout(S.pollTimer);
  S.pid = id; S.tr = null; S.runs = null; S.curWord = null; S.curSeg = null; S.curPoint = null; S.dirty = false; Saver.set('clean'); History.clear(); audio.pause();
  S.meta = await api(`/projects/${id}`);
  const hasT = S.meta.status === 'klaar' || (S.meta.status !== 'nieuw' && S.meta.runs && Object.keys(S.meta.runs).length && S.meta.status !== 'bezig');
  if (hasT) await loadTranscript();
  enableTabs(true, !!S.tr);
  updateTopFile();
  show(view || (S.tr && S.meta.status === 'klaar' ? 'editor' : 'process'));
}
function updateTopFile() { if (!S.meta) return; const f = S.meta.settings.start != null || S.meta.settings.end != null; $('#topFile').textContent = `${S.meta.name}${S.meta.study ? ' · ' + S.meta.study.name : ''} · ${S.meta.audio.duration ? fmtT(S.meta.audio.duration) : '…'}${f ? ' (fragment)' : ''} · ${S.meta.status_label || ''}`; }
async function loadTranscript() {
  Saver.reset();
  try { S.tr = await api(`/projects/${S.pid}/transcript`); } catch (e) { S.tr = null; }
  S.threshold = S.meta.settings.uncertain_threshold || 0.6;
  audio.src = `/api/projects/${S.pid}/audio${$('#origAudio').checked ? '?original=1' : ''}`;
  try { S.peaks = await api(`/projects/${S.pid}/peaks`); } catch (e) { S.peaks = []; }
}
async function refreshMeta() { S.meta = await api(`/projects/${S.pid}`); updateTopFile(); }

/* ======================= startpagina ======================= */
let newFile = null;
async function loadHome() {
  S.info = S.info || await api('/info');
  [S.projects, S.studies] = await Promise.all([api('/projects'), api('/studies')]);
  const hw = S.info.hardware, rec = S.info.recommended, models = S.info.models;
  const groups = [...S.studies.map(s => ({ study: s, items: S.projects.filter(p => p.study_id === s.id) })), { study: null, items: S.projects.filter(p => !p.study_id || !S.studies.some(s => s.id === p.study_id)) }];
  const item = p => `<button class="item" data-id="${esc(p.id)}" aria-label="${esc(p.name)}, ${esc(p.status_label)}"><div><b>${esc(p.name)}</b><div style="font-size:12px;color:var(--muted)">Volgende stap: ${esc(p.next_action)}${p.review ? ` · nagekeken ${p.review.reviewed}/${p.review.segments}` : ''}${p.fragment && (p.fragment.start != null || p.fragment.end != null) ? ' · fragment' : ''}</div></div><div class="meta"><span class="status ${esc(p.review_status === 'checked' ? 'checked' : p.status)}">${esc(p.status_label)}</span><div>${p.duration ? fmtT(p.duration) : ''}</div></div></button>`;
  const studyBlock = g => `<div class="study"><div class="sh">${g.study ? `<b>${esc(g.study.name)}</b><span class="meta">${g.items.length} interview(s) · ${g.study.checked} gecontroleerd</span><button class="btn small" data-study="${esc(g.study.id)}">Instellingen</button>` : `<b>Zonder onderzoek</b><span class="meta">${g.items.length} interview(s)</span>`}</div><div class="plist">${g.items.length ? g.items.map(item).join('') : '<div class="sub" style="padding:10px 12px;margin:0">Nog geen interviews.</div>'}</div></div>`;
  // een half ingevuld formulier overleeft een herbouw van de startpagina (bijv. na het opslaan van een onderzoek)
  const keep = {}; ['newName', 'newStudySel', 'newLang', 'newSpk', 'newTerms', 'tryStart', 'tryLen'].forEach(id => { const el = $('#' + id); if (el && el.value) keep[id] = el.value; });
  const keepTry = $('#tryFirst')?.checked;
  const modelOpt = ([id, m]) => { const avail = m.available; return `<label class="cb ${avail ? '' : 'na'}"><input type="checkbox" class="nModel" value="${id}" ${rec.models.includes(id) ? 'checked' : ''} ${avail ? '' : 'disabled'}> ${esc(m.label)} <small>· ${esc(m.note)}${m.downloaded ? '' : ` · eenmalige download ± ${m.size_gb} GB`}${avail ? '' : ' · niet geïnstalleerd'}</small></label>`; };
  $('#home').innerHTML = `
  <div class="grid2">
    <div>
      <h2>Onderzoeken en interviews</h2>
      <div class="sub">Een onderzoek bundelt interviews met een gedeelde woordenlijst, transcriptieafspraken en exportvoorkeuren. <button class="btn small" id="newStudy">+ Nieuw onderzoek</button> <button class="btn small" id="restoreBackup">Back-up terugzetten</button></div>
      ${groups.filter(g => g.study || g.items.length).map(studyBlock).join('') || '<div class="sub">Nog niets. Maak rechts een eerste interview aan.</div>'}
      <details><summary>Hoe werkt Sift?</summary><p class="sub">Je kiest een opname, Sift zet die op je eigen computer om in tekst, wijst sprekers toe en laat zien welke passages aandacht nodig hebben. Daarna kijk je het transcript na met de audio ernaast en exporteer je naar Word, MAXQDA, NVivo of een gegevensformaat. Er wordt niets naar internet gestuurd; alleen het spraakmodel wordt eenmalig gedownload.</p><p class="sub">Probeer het eerst met het fictieve demo-interview in de map <code>demo/</code>.</p></details>
    </div>
    <div>
      <h2>Nieuw interview</h2>
      <div class="sub">Sleep een opname hierheen (mp3, m4a, wav, mp4, WhatsApp-audio …). De opname blijft op deze computer.</div>
      <div class="form">
        <div class="drop" id="drop">Sleep een bestand hierheen of <label for="fileInput">kies een bestand</label><input type="file" id="fileInput" accept="audio/*,video/*" style="display:none"><div id="fileName" style="margin-top:6px;color:var(--text)"></div></div>
        <label for="newName">Naam van het interview</label><input type="text" id="newName" placeholder="bijv. R03 – ervaringen eerste jaar">
        <label for="newStudySel">Onderzoek</label><select id="newStudySel"><option value="">Zonder onderzoek</option>${S.studies.map(s => `<option value="${esc(s.id)}">${esc(s.name)}</option>`).join('')}</select>
        <label for="newLang">Gesproken taal</label><select id="newLang">${S.info.languages.map(([c, l]) => `<option value="${c}" ${c === 'nl' ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select>
        <label for="newSpk">Aantal sprekers</label><select id="newSpk"><option value="2">2 (interviewer en respondent)</option><option value="1">1</option><option value="3">3</option><option value="4">4</option><option value="5">5</option><option value="">Weet ik niet</option></select>
        <div class="note" id="spkNote" style="display:none">Bij "weet ik niet" schat Sift het aantal sprekers (2 tot 5) op basis van stemkenmerken. Dat is een schatting: controleer en corrigeer de sprekers daarna in het transcript.</div>
        <label for="newTerms">Namen, afkortingen en vaktermen (optioneel)</label><textarea id="newTerms" placeholder="bijv. methotrexaat, reumaverpleegkundige, dr. Pieters"></textarea>
        <div class="sub" style="margin:4px 0 0">Helpt het spraakmodel deze woorden te herkennen. De woordenlijst van het onderzoek wordt automatisch meegenomen.</div>
        <label class="inline" for="tryFirst"><input type="checkbox" id="tryFirst"> Probeer eerst twee minuten</label>
        <div id="tryBox" style="display:none;margin-left:22px"><span class="sub">Vanaf <input type="text" class="short" id="tryStart" value="0:00" aria-label="Begin van het fragment (mm:ss)"> gedurende <input type="text" class="short" id="tryLen" value="2:00" aria-label="Lengte van het fragment (mm:ss)"> (mm:ss). Daarna kun je de hele opname verwerken. Tijdcodes van een fragment tellen vanaf de fragmentstart; bij exporteren kun je ze omrekenen naar de bronopname.</span></div>
        <details id="advBox"><summary>Geavanceerd</summary>
          <div class="sub">Standaard gekozen voor deze computer: ${esc(rec.why)}</div>
          <label>Spraakmodellen</label><div class="opt">${Object.entries(models).filter(([id, m]) => m.available || !m.optional).map(modelOpt).join('')}</div>
          <label for="advComb">Combineren van meerdere modellen</label><select id="advComb"><option value="consensus">Consensus (meerderheid per woord)</option><option value="highest_p">Hoogste modelscore wint</option><option value="base_plus_alts">Eerste model + alternatieven</option></select>
          <label for="advDev">Rekenen op</label><select id="advDev"><option value="auto">Automatisch</option><option value="cuda" ${hw.cuda ? '' : 'disabled'}>GPU${hw.gpu_name ? ' (' + esc(hw.gpu_name) + ')' : ''}</option><option value="cpu">CPU</option></select>
          <label class="inline" for="advNorm"><input type="checkbox" id="advNorm" checked> Luidheid normaliseren</label>
          <label class="inline" for="advComp"><input type="checkbox" id="advComp" checked> Compressor</label>
          <label for="advLufs">Doelluidheid (LUFS)</label><select id="advLufs"><option>-16</option><option>-18</option><option>-20</option></select>
          <label for="advDen">Ruisonderdrukking</label><select id="advDen"><option value="off">Uit (aanbevolen)</option><option value="light">Licht</option><option value="strong">Sterk</option></select>
          <label for="advHot">Stopwoord-hint (hotwords)</label><input type="text" id="advHot" value="${esc(S.info.defaults.hotwords)}">
        </details>
        <div style="margin-top:14px"><button class="btn primary" id="btnCreate">Transcript maken</button></div>
        <div class="hw" id="hw">Deze computer: ${hw.gpu_name ? `GPU ${esc(hw.gpu_name)}${hw.vram_gb ? ' (' + hw.vram_gb + ' GB)' : ''}` : 'geen NVIDIA-GPU, verwerking op de processor'} · ffmpeg ${hw.ffmpeg ? 'gevonden' : '<b style="color:var(--warn)">niet gevonden (vereist)</b>'} · sprekerscheiding ${S.info.diarize_available ? 'beschikbaar' : 'niet beschikbaar'}</div>
      </div>
      <div class="card phone" id="phoneCard"></div>
    </div>
  </div>`;
  renderPhoneCard();
  $$('#home .item').forEach(el => el.onclick = () => openProject(el.dataset.id));
  $$('#home [data-study]').forEach(b => b.onclick = () => studySettings(b.dataset.study));
  $('#newStudy').onclick = async () => { const name = await promptBox('Naam van het onderzoek'); if (name) { await post('/studies', { name }); loadHome(); } };
  $('#restoreBackup').onclick = restoreBackupDialog;
  $('#newSpk').onchange = e => $('#spkNote').style.display = e.target.value === '' ? '' : 'none';
  $('#tryFirst').onchange = e => $('#tryBox').style.display = e.target.checked ? '' : 'none';
  const drop = $('#drop');
  drop.ondragover = e => { e.preventDefault(); drop.classList.add('over'); };
  drop.ondragleave = () => drop.classList.remove('over');
  drop.ondrop = e => { e.preventDefault(); drop.classList.remove('over'); if (e.dataTransfer.files[0]) setFile(e.dataTransfer.files[0]); };
  $('#fileInput').onchange = e => { if (e.target.files[0]) setFile(e.target.files[0]); };
  Object.entries(keep).forEach(([id, v]) => { const el = $('#' + id); if (el) el.value = v; });
  if (keepTry) { $('#tryFirst').checked = true; $('#tryBox').style.display = ''; }
  if (newFile) setFile(newFile);
  $('#btnCreate').onclick = createInterview;
}
function setFile(f) { newFile = f; $('#fileName').textContent = `${f.name} (${(f.size / 1048576).toFixed(1)} MB)`; if (!$('#newName').value) $('#newName').value = f.name.replace(/\.[^.]+$/, ''); }
async function createInterview() {
  if (!newFile) return toast('Kies eerst een opname');
  const models = $$('.nModel:checked').map(c => c.value);
  if (!models.length) return toast('Kies onder Geavanceerd minstens één spraakmodel');
  let start = null, end = null;
  if ($('#tryFirst').checked) { start = parseMMSS($('#tryStart').value) || 0; const len = parseMMSS($('#tryLen').value) || 120; end = start + len; }
  const settings = { models, language: $('#newLang').value, num_speakers: $('#newSpk').value ? +$('#newSpk').value : null, initial_prompt: $('#newTerms').value.trim(), start: start || null, end,
    combine: $('#advComb').value, device: $('#advDev').value, normalize: $('#advNorm').checked, compressor: $('#advComp').checked, target_lufs: +$('#advLufs').value, denoise: $('#advDen').value, hotwords: $('#advHot').value, diarize: true };
  const fd = new FormData(); fd.append('name', $('#newName').value || newFile.name); fd.append('settings', JSON.stringify(settings)); fd.append('file', newFile); fd.append('study_id', $('#newStudySel').value);
  const b = $('#btnCreate'); b.disabled = true; b.textContent = 'Opname kopiëren…';
  try { const r = await api('/projects', { method: 'POST', body: fd }); await post(`/projects/${r.id}/run`); newFile = null; await openProject(r.id, 'process'); }
  catch (e) { toast('Fout: ' + e.message); b.disabled = false; b.textContent = 'Transcript maken'; }
}

/* ---- telefoon (LAN + QR) ---- */
async function renderPhoneCard() {
  const card = $('#phoneCard'); if (!card) return;
  if (!S.lanOk) { card.classList.remove('hidden'); card.innerHTML = `<h5 style="margin:0 0 4px">Opname sturen vanaf deze telefoon</h5><div class="sub" style="margin-bottom:8px">Kies een opname of neem er een op; die verschijnt op de computer als interview.</div><a class="btn primary" href="/drop" style="display:inline-flex;text-decoration:none">Opname kiezen of opnemen</a>`; return; }
  let l; try { l = await api('/lan'); } catch (e) { card.classList.add('hidden'); return; }
  card.classList.remove('hidden');
  card.innerHTML = `<div class="ph"><img src="/api/lan/qr.svg?${Date.now()}" alt="QR-code met het adres van Sift op dit netwerk" class="qr small"><div style="flex:1;min-width:0"><h5 style="margin:0 0 4px">Vanaf je telefoon</h5>
    <div class="sub" style="margin-bottom:6px">Scan de QR op hetzelfde wifi, kies of maak een opname; die verschijnt hier als interview (zonder onderzoek; koppelen kan daarna).</div>
    <div class="code">${esc(l.code)}</div><div class="url">${esc(l.url.replace(/\?code=.*/, ''))}</div>
    <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:8px"><label class="cb"><input type="checkbox" id="phCardLan" ${l.enabled ? 'checked' : ''}> bereikbaar op het netwerk</label><button class="btn small" id="phCardMore">Details en QR groot</button></div></div></div>`;
  $('#phCardLan').onchange = async e => { await post('/lan/enable', { enabled: e.target.checked }); toast(e.target.checked ? 'Sift is bereikbaar op het netwerk' : 'Netwerktoegang uit'); };
  $('#phCardMore').onclick = phoneModal;
}
async function phoneModal() {
  let l; try { l = await api('/lan'); } catch (e) { return toast('Alleen beschikbaar op de computer zelf'); }
  const m = modal('', { label: 'Vanaf je telefoon' });
  const fw = { allowed: 'Windows Firewall laat Sift door.', blocked: '<b style="color:var(--warn)">Windows Firewall blokkeert Sift.</b> Verwijder de blokkeerregel voor python.exe in "Windows Defender Firewall → Toegestane apps" of sta hem toe.', none: 'Windows Firewall kan bij de eerste verbinding een melding tonen; kies dan <b>Toegang toestaan</b> (privénetwerken).', unknown: 'Controleer bij problemen of de firewall Sift toelaat.' };
  const render = () => {
    m.querySelector('.box').innerHTML = `<h3>Vanaf je telefoon</h3>
      <div class="sub">Scan de QR met de camera van je telefoon. Daar kies je een opname of neem je er een op; die verschijnt hier als interview en wordt (optioneel) direct verwerkt. Transcripten nakijken kan ook op de telefoon.</div>
      <label class="cb" style="display:inline-flex;margin-bottom:12px"><input type="checkbox" id="phLan" ${l.enabled ? 'checked' : ''}> <b>Bereikbaar op het netwerk</b>&nbsp;<small>(${l.enabled ? 'aan' : 'uit: telefoon krijgt "LAN uit"'})</small></label>
      <div class="ph big"><img src="/api/lan/qr.svg?${Date.now()}" alt="QR-code met het adres van Sift op dit netwerk" class="qr"><div>
        <div class="lbl">Adres</div><div class="url">${esc((l.url || '').replace(/\?code=.*/, ''))}</div>
        <div class="lbl" style="margin-top:10px">Code</div><div class="code">${esc(l.code)}</div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:12px"><button class="btn" id="phNew">Nieuwe code</button><button class="btn" id="phCopy">Kopieer link</button><button class="btn" id="phClose">Sluiten</button></div></div></div>
      <div class="sub" style="margin-top:12px">Zelfde wifi vereist (geen gasten-netwerk). ${l.ip ? `Dit adres is ${esc(l.ip)}${l.ips && l.ips.length > 1 ? ' (andere: ' + l.ips.slice(1).map(esc).join(', ') + ')' : ''}.` : '<b style="color:var(--warn)">Geen netwerkadres gevonden.</b>'} ${fw[l.firewall] || fw.unknown} Start Sift met <span class="kbd">--lan</span> om netwerktoegang meteen aan te zetten.</div>`;
    $('#phLan', m).onchange = async e => { l = await post('/lan/enable', { enabled: e.target.checked }); render(); toast(l.enabled ? 'Sift is bereikbaar op het netwerk' : 'Netwerktoegang uit'); renderPhoneCard(); };
    $('#phNew', m).onclick = async () => { l = await post('/lan/newcode'); render(); toast('Nieuwe code: ' + l.code); renderPhoneCard(); };
    $('#phCopy', m).onclick = async () => { try { await navigator.clipboard.writeText(l.url); toast('Link gekopieerd'); } catch (e) { prompt('Kopieer de link', l.url); } };
    $('#phClose', m).onclick = () => m.remove();
  };
  render();
}
$('#btnPhone').onclick = phoneModal;

/* ---- onderzoek: instellingen, woordenlijst, transcriptieafspraken ---- */
async function studySettings(sid) {
  const s = await api(`/studies/${sid}`), cat = S.info.conventions, conv = { ...S.info.conventions_default, ...(s.conventions || {}) };
  const convRow = ([key, c]) => `<div class="card"><h5>${esc(c.label)}</h5>${Object.entries(c.options).map(([ok, o]) => `<label class="inline" style="display:flex;align-items:flex-start;gap:8px;margin:4px 0"><input type="radio" name="cv_${key}" value="${ok}" ${conv[key] === ok ? 'checked' : ''}><span>${esc(o.label)}<br><small style="color:var(--muted)">vóór: ${esc(o.before)}<br>na: ${esc(o.after)}</small></span></label>`).join('')}${c.extra ? `<label for="cv_${c.extra.key}">${esc(c.extra.label)}</label><input type="text" id="cv_${c.extra.key}" value="${esc(conv[c.extra.key] ?? c.extra.default)}">` : ''}<div class="note">Automatisch: ${esc(c.automatic)}${c.caveat ? ' ' + esc(c.caveat) : ''}</div></div>`;
  const m = modal(`<h3>Onderzoek: ${esc(s.name)}</h3><div class="form">
    <label for="stName">Naam</label><input type="text" id="stName" value="${esc(s.name)}">
    <label for="stLang">Standaardtaal</label><select id="stLang">${S.info.languages.map(([c, l]) => `<option value="${c}" ${c === (s.language || 'nl') ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select>
    <label for="stTerms">Gedeelde woordenlijst (namen, afkortingen, vaktermen)</label><textarea id="stTerms">${esc(s.terms || '')}</textarea>
    <div class="note">Geldt voor alle interviews van dit onderzoek bij de <b>volgende</b> verwerking. Wijzigen start geen verwerking en verandert geen bestaande correcties.</div>
    <h3 style="margin-top:16px">Transcriptieafspraken</h3>
    <div class="note">Leg vast hoe je omgaat met aarzelingen, herhalingen, pauzes en overlap. Per keuze staat wat Sift automatisch doet en wat je zelf controleert. Deze afspraken stem je af met je begeleider; Sift beoordeelt niet of ze methodologisch passend zijn. "Verbatim" betekent: zoals herkend en door jou gecorrigeerd; een model herkent niet alle aarzelingen.</div>
    ${Object.entries(cat).map(convRow).join('')}
    <div class="actions"><button class="btn primary" id="stSave">Opslaan</button><a class="btn" href="/api/studies/${esc(sid)}/conventions.txt" download>Afspraken exporteren (.txt)</a><button class="btn danger" id="stDel">Onderzoek verwijderen</button></div></div>`, { wide: true, label: 'Onderzoek instellen' });
  $('#stSave', m).onclick = async () => {
    const c = {}; Object.keys(cat).forEach(k => { const r = $(`input[name="cv_${k}"]:checked`, m); if (r) c[k] = r.value; if (cat[k].extra) c[cat[k].extra.key] = $(`#cv_${cat[k].extra.key}`, m).value; });
    await put(`/studies/${sid}`, { name: $('#stName', m).value, language: $('#stLang', m).value, terms: $('#stTerms', m).value, conventions: c });
    m.remove(); toast('Onderzoek opgeslagen'); loadHome();
  };
  $('#stDel', m).onclick = async () => { if (!(await confirmBox('Onderzoek verwijderen? Interviews blijven bestaan (zonder onderzoek).'))) return; try { await del(`/studies/${sid}`); m.remove(); loadHome(); } catch (e) { toast(e.message); } };
}

/* ---- back-up terugzetten ---- */
function restoreBackupDialog() {
  const m = modal(`<h3>Back-up terugzetten</h3><div class="sub">Een Sift-back-up (.zip) bevat de oorspronkelijke opname, het transcript, sprekers, opmerkingen, versies en instellingen. Herstellen maakt altijd een <b>nieuw</b> interview aan; een bestaand interview wordt nooit overschreven.</div><div class="form"><input type="file" id="bkFile" accept=".zip"><div id="bkInfo" class="sub" style="margin-top:10px"></div><div class="actions"><button class="btn primary" id="bkGo" disabled>Terugzetten</button></div></div>`, { label: 'Back-up terugzetten' });
  let file = null;
  $('#bkFile', m).onchange = async e => {
    file = e.target.files[0]; if (!file) return;
    const fd = new FormData(); fd.append('file', file);
    try { const i = await api('/backups/inspect', { method: 'POST', body: fd }); $('#bkInfo', m).innerHTML = `<b>${esc(i.name)}</b> (id ${esc(i.project_id)}) · ${i.has_audio ? 'met opname' : '<span style="color:var(--warn)">zonder opname</span>'} · ${i.versions} versie(s)${i.study ? ` · onderzoek "${esc(i.study.name)}"` : ''}<br>${i.exists ? '<span style="color:var(--warn)">Er bestaat al een interview met deze id; de back-up wordt als kopie met achtervoegsel teruggezet.</span>' : 'Wordt als nieuw interview teruggezet.'}`; $('#bkGo', m).disabled = false; }
    catch (err) { $('#bkInfo', m).innerHTML = `<span style="color:var(--warn)">${esc(err.message)}</span>`; $('#bkGo', m).disabled = true; }
  };
  $('#bkGo', m).onclick = async () => { const fd = new FormData(); fd.append('file', file); try { const r = await api('/backups/restore', { method: 'POST', body: fd }); m.remove(); toast(`Teruggezet als "${r.id}"${r.renamed ? ' (kopie)' : ''}`); loadHome(); } catch (err) { toast(err.message); } };
}
