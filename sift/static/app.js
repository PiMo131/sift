/* Sift — lokale interviewtranscriptie. Vanilla JS, geen build-stap. */
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
const fmtT = (s, ms = false) => { if (s == null || isNaN(s)) return '--:--'; const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), sec = s % 60; const b = `${String(m).padStart(2, '0')}:${ms ? sec.toFixed(1).padStart(4, '0') : String(Math.floor(sec)).padStart(2, '0')}`; return h ? `${h}:${b}` : b; };
const fmtHMS = s => { const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), sec = Math.floor(s % 60); return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`; };
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const normW = w => (w || '').toLowerCase().replace(/[^\p{L}\p{N}']/gu, '');
const SPEAKER_COLORS = ['#2b6cb0', '#9f3fbf', '#2f855a', '#c05621', '#b7791f', '#2c7a7b', '#702459', '#4a5568'];
let toastT; const toast = m => { let t = $('.toast'); if (!t) { t = document.createElement('div'); t.className = 'toast'; document.body.appendChild(t); } t.textContent = m; clearTimeout(toastT); toastT = setTimeout(() => t.remove(), 2600); };

const S = {
  info: null, projects: [], pid: null, meta: null, tr: null, runs: null, view: 'home',
  threshold: 0.6, heat: true, curWord: null, curSeg: null, dirty: false, saveTimer: null, pollTimer: null,
  playWindow: null, wasPlaying: false, typingTimer: null, peaks: [], loopSel: null, saved: '', style: 'verbatim',
};
const audio = $('#audio');
let audioCtx, gainNode;

/* ======================= navigatie ======================= */
function show(view) {
  S.view = view;
  $$('.view').forEach(v => v.classList.toggle('hidden', v.id !== 'view-' + view));
  $$('.tab').forEach(t => t.classList.toggle('on', t.dataset.view === view));
  $('#topActions').innerHTML = '';
  if (view === 'home') loadHome();
  if (view === 'pipeline') renderPipeline();
  if (view === 'editor') { renderEditor(); $('#topActions').innerHTML = `<button class="btn" id="btnDict">Woordenlijst</button> <button class="btn" id="btnFind">Zoek &amp; vervang</button> <button class="btn" id="btnKeys">Sneltoetsen</button> <button class="btn" id="btnSnap">Versie bewaren</button> <button class="btn primary" id="btnExportTop">Exporteren</button>`; $('#btnFind').onclick = findReplace; $('#btnKeys').onclick = showKeys; $('#btnDict').onclick = editDictionary; $('#btnSnap').onclick = async () => { const label = prompt('Label voor deze versie (optioneel)') ?? ''; await post(`/projects/${S.pid}/snapshot`, { label }); toast('Versie bewaard'); }; $('#btnExportTop').onclick = () => show('export'); }
  if (view === 'compare') renderCompare();
  if (view === 'export') renderExport();
}
$$('.tab').forEach(t => t.onclick = () => show(t.dataset.view));
function enableTabs(on) { $$('.tab').forEach(t => { if (t.dataset.view !== 'home') t.disabled = !on; }); }

/* ======================= home ======================= */
async function loadHome() {
  S.info = S.info || await api('/info');
  S.projects = await api('/projects');
  const hw = S.info.hardware;
  $('#hw').innerHTML = `Hardware: ${hw.gpu_name ? `GPU ${esc(hw.gpu_name)}${hw.vram_gb ? ' (' + hw.vram_gb + ' GB)' : ''}` : 'geen CUDA-GPU, CPU-modus'} · ${hw.cpu_threads} threads · ffmpeg ${hw.ffmpeg ? 'ok' : '<b style="color:var(--warn)">niet gevonden</b>'} · sprekerscheiding ${S.info.diarize_available ? 'beschikbaar' : 'uit (speechbrain ontbreekt)'}`;
  $('#plist').innerHTML = S.projects.length ? S.projects.map(p => `<div class="item" data-id="${esc(p.id)}"><div><b>${esc(p.name)}</b><div style="font-size:12px;color:var(--muted)">${p.models.join(', ') || 'nog niet verwerkt'}</div></div><div class="meta"><span class="status ${esc(p.status)}">${esc(p.status)}</span><div>${p.duration ? fmtT(p.duration) : ''}</div></div></div>`).join('') : '<div class="sub">Nog geen projecten.</div>';
  $$('#plist .item').forEach(el => el.onclick = () => openProject(el.dataset.id));
  const box = $('#newModels');
  if (!box.children.length) {
    const models = Object.entries(S.info.models);
    box.innerHTML = models.map(([id, m]) => `<label class="cb"><input type="checkbox" value="${id}" ${S.info.defaults.models.includes(id) ? 'checked' : ''}> ${esc(m.label)} <small>· ${esc(m.note)}</small></label>`).join('') + `<label class="cb" style="border-color:var(--accent)"><input type="checkbox" id="newAll"> <b>Allemaal</b></label>`;
    $('#newAll').onchange = e => $$('#newModels input[type=checkbox]:not(#newAll)').forEach(c => c.checked = e.target.checked);
  }
}
let newFile = null;
const drop = $('#drop');
drop.ondragover = e => { e.preventDefault(); drop.classList.add('over'); };
drop.ondragleave = () => drop.classList.remove('over');
drop.ondrop = e => { e.preventDefault(); drop.classList.remove('over'); if (e.dataTransfer.files[0]) setFile(e.dataTransfer.files[0]); };
$('#fileInput').onchange = e => { if (e.target.files[0]) setFile(e.target.files[0]); };
function setFile(f) { newFile = f; $('#fileName').textContent = `${f.name} (${(f.size / 1048576).toFixed(1)} MB)`; if (!$('#newName').value) $('#newName').value = f.name.replace(/\.[^.]+$/, ''); }
$('#btnCreate').onclick = async () => {
  if (!newFile) return toast('Kies eerst een bestand');
  const models = $$('#newModels input:not(#newAll):checked').map(c => c.value);
  if (!models.length) return toast('Kies minstens één model');
  const settings = { models, start: $('#newStart').value ? +$('#newStart').value : null, end: $('#newEnd').value ? +$('#newEnd').value : null };
  const fd = new FormData(); fd.append('name', $('#newName').value || newFile.name); fd.append('settings', JSON.stringify(settings)); fd.append('file', newFile);
  $('#btnCreate').disabled = true; $('#btnCreate').textContent = 'Uploaden…';
  try { const r = await api('/projects', { method: 'POST', body: fd }); await post(`/projects/${r.id}/run`); newFile = null; $('#fileName').textContent = ''; $('#newName').value = ''; await openProject(r.id); }
  catch (e) { toast('Fout: ' + e.message); }
  $('#btnCreate').disabled = false; $('#btnCreate').textContent = 'Project aanmaken en starten';
};

async function openProject(id) {
  S.pid = id; S.tr = null; S.runs = null; S.curWord = null; S.curSeg = null;
  S.meta = await api(`/projects/${id}`);
  enableTabs(true);
  $('#topFile').textContent = `${S.meta.name} · ${S.meta.audio.duration ? fmtT(S.meta.audio.duration) : '…'} · ${Object.keys(S.meta.runs).join(' + ') || 'nog niet verwerkt'}`;
  if (S.meta.status === 'klaar') { await loadTranscript(); show('editor'); } else show('pipeline');
}
async function loadTranscript() {
  try { S.tr = await api(`/projects/${S.pid}/transcript`); S.saved = JSON.stringify(S.tr); S.dirty = false; } catch (e) { S.tr = null; }
  S.threshold = S.meta.settings.uncertain_threshold || 0.6;
  audio.src = `/api/projects/${S.pid}/audio${$('#origAudio').checked ? '?original=1' : ''}`;
  try { S.peaks = await api(`/projects/${S.pid}/peaks`); } catch (e) { S.peaks = []; }
}

/* ======================= pipeline ======================= */
function renderPipeline() {
  const m = S.meta, st = m.settings, sd = m.status_detail || {}, models = S.info.models, hw = S.info.hardware;
  const done = k => m.steps && m.steps[k] ? 'ok' : '';
  const est = id => { const x = models[id]; const dur = m.audio.duration || 0; const xrt = (st.device === 'cpu' || !hw.cuda) ? x.xrt_cpu : x.xrt_gpu; return dur ? `~${Math.max(1, Math.round(dur / xrt / 60))} min` : ''; };
  const runRows = Object.entries(m.runs || {}).map(([id, r]) => `<tr><td>${esc(models[id]?.label || id)}</td><td>${r.stats.device} ${r.stats.compute}</td><td>${r.stats.run_s}s (${r.stats.realtime_factor}×)</td><td>${r.stats.n_words}</td><td>${r.stats.mean_p}</td><td>${m.summary?.[id]?.uncertain ?? ''}</td></tr>`).join('');
  const lo = m.audio.loudness;
  $('#pipe').innerHTML = `
  <div>
    <h2 style="margin:0 0 4px">Verwerking</h2><div class="sub">Elke stap wordt gecached. Instellingen wijzigen en opnieuw starten draait alleen wat veranderd is. Modellen draaien na elkaar: tegelijk op één GPU is tien keer trager.</div>
    <div class="step"><div class="n ${done('convert')}">${done('convert') ? '✓' : '1'}</div><div style="flex:1"><h4>1. Inlezen</h4><p>ffmpeg → 16 kHz mono. ${m.audio.source_info ? `Bron: ${esc(m.audio.source_info.codec)} ${m.audio.source_info.sample_rate} Hz, ${m.audio.source_info.channels} kanaal, ${fmtT(m.audio.source_info.duration)}.` : ''}</p>
      <div class="opt"><span>Fragment (s):</span><input type="number" class="k" id="pStart" value="${st.start ?? ''}" placeholder="start" style="width:70px"><input type="number" class="k" id="pEnd" value="${st.end ?? ''}" placeholder="einde" style="width:70px"></div></div></div>
    <div class="step"><div class="n ${done('normalize')}">${done('normalize') ? '✓' : '2'}</div><div style="flex:1"><h4>2. Luidheid normaliseren</h4><p>Highpass 80 Hz, compressor 3:1, loudnorm (EBU R128). Belangrijkste stap voor een zachte spreker.</p>
      <div class="opt"><label class="cb"><input type="checkbox" id="pNorm" ${st.normalize ? 'checked' : ''}> normaliseren</label><label class="cb">doel <select id="pLufs" class="k"><option ${st.target_lufs == -16 ? 'selected' : ''}>-16</option><option ${st.target_lufs == -18 ? 'selected' : ''}>-18</option><option ${st.target_lufs == -20 ? 'selected' : ''}>-20</option></select> LUFS</label><label class="cb"><input type="checkbox" id="pComp" ${st.compressor ? 'checked' : ''}> compressor</label></div>
      ${lo ? `<p style="margin-top:6px">Gemeten: ${lo.before_lufs.toFixed(1)} LUFS → ${lo.after_lufs.toFixed(1)} LUFS (bereik ${lo.before_lra.toFixed(1)} → ${lo.after_lra.toFixed(1)} LU)</p>` : ''}</div></div>
    <div class="step"><div class="n ${done('normalize')}">${done('normalize') ? '✓' : '3'}</div><div style="flex:1"><h4>3. Ruisonderdrukking</h4><p>In de benchmark leverde dit niets op; alleen aanzetten bij echt rumoerige opnames.</p>
      <div class="opt">${['off', 'light', 'strong'].map(v => `<span class="chip ${st.denoise === v ? 'on' : ''}" data-den="${v}">${{ off: 'Uit', light: 'Licht', strong: 'Sterk' }[v]}</span>`).join('')}</div></div></div>
    <div class="step"><div class="n ${Object.keys(m.runs || {}).length ? 'ok' : (sd.running ? 'run' : '')}">${Object.keys(m.runs || {}).length ? '✓' : '4'}</div><div style="flex:1"><h4>4. Transcriberen</h4><p>Kies één of meer modellen; meerdere uitkomsten worden per woord over elkaar gelegd.</p>
      <div class="opt">${Object.entries(models).map(([id, x]) => `<label class="cb"><input type="checkbox" class="pModel" value="${id}" ${st.models.includes(id) ? 'checked' : ''}> ${esc(x.label)} <small>· ${est(id)}</small></label>`).join('')}<label class="cb" style="border-color:var(--accent)"><input type="checkbox" id="pAll"> <b>Allemaal</b></label></div>
      <p style="margin-top:8px">Combineren</p><div class="opt">${[['consensus', 'Consensus (meerderheid per woord)'], ['highest_p', 'Hoogste zekerheid wint'], ['base_plus_alts', 'Basismodel + alternatieven']].map(([v, l]) => `<span class="chip ${st.combine === v ? 'on' : ''}" data-comb="${v}">${l}</span>`).join('')}</div>
      <div class="opt" style="margin-top:8px"><span>Device</span>${[['auto', 'Automatisch'], ['cuda', 'GPU'], ['cpu', 'CPU']].map(([v, l]) => `<span class="chip ${st.device === v ? 'on' : ''}" data-dev="${v}">${l}</span>`).join('')}<span style="color:var(--muted2);font-size:12px">${hw.gpu_name ? esc(hw.gpu_name) : 'geen GPU gevonden'}</span></div>
      <div class="opt" style="margin-top:8px"><label style="flex:1">Woordenlijst / context (initial prompt)<input type="text" id="pPrompt" class="k" style="width:100%;margin-top:3px" value="${esc(st.initial_prompt)}" placeholder="namen, vaktermen, plaatsen…"></label></div>
      <div class="opt"><label style="flex:1">Stopwoord-hint (hotwords)<input type="text" id="pHot" class="k" style="width:100%;margin-top:3px" value="${esc(st.hotwords)}"></label></div>
      ${sd.running ? `<div class="prog"><i style="width:${Math.round((sd.progress || 0) * 100)}%"></i></div><p style="margin-top:6px"><b>${esc(sd.step)}</b> · ${Math.round((sd.progress || 0) * 100)}% · ${esc(sd.detail || '')}</p>` : ''}
      ${m.status === 'fout' ? `<p style="color:var(--warn);margin-top:6px">Fout: ${esc(m.error)}</p>` : ''}</div></div>
    <div class="step"><div class="n ${m.speakers && Object.keys(m.speakers).length > 1 ? 'ok' : ''}">5</div><div style="flex:1"><h4>5. Sprekers scheiden</h4><p>${S.info.diarize_available ? 'Spreker-embeddings per segment, lokaal geclusterd (SpeechBrain, open source, geen registratie). Geef het aantal sprekers op voor het beste resultaat.' : 'Niet actief: installeer speechbrain en torch (pip install -r requirements.txt). Zonder diarisatie wijs je sprekers in de editor toe.'}${m.diarization ? ` Laatste run: ${m.diarization.speakers} sprekers gevonden.` : ''}</p>
      <div class="opt"><label class="cb"><input type="checkbox" id="pDiar" ${st.diarize ? 'checked' : ''}> sprekerscheiding</label><label class="cb">aantal sprekers <input type="number" id="pNum" class="k" value="${st.num_speakers || ''}" min="1" max="10" style="width:50px"></label></div></div></div>
    <div style="display:flex;gap:8px;margin-top:6px">${sd.running ? `<button class="btn" id="pCancel">Annuleren</button>` : `<button class="btn primary" id="pRun">${Object.keys(m.runs || {}).length ? 'Opnieuw verwerken' : 'Starten'}</button>`}<button class="btn" id="pRecomb" ${Object.keys(m.runs || {}).length < 1 ? 'disabled' : ''}>Alleen opnieuw combineren</button>${m.status === 'klaar' ? `<button class="btn" id="pOpen">Open in editor</button>` : ''}</div>
  </div>
  <div>
    <h2 style="margin:0 0 4px">Resultaat</h2><div class="sub">Per model: snelheid, woorden en zekerheid.</div>
    <div class="card"><h5>Modelruns</h5>${runRows ? `<table class="t"><tr><th>model</th><th>device</th><th>tijd</th><th>woorden</th><th>gem. zekerheid</th><th>onzeker</th></tr>${runRows}</table>` : '<div class="sub">Nog geen runs.</div>'}</div>
    <div class="card"><h5>Logboek</h5><div class="log" id="pLog">${(m.log || []).map(esc).join('\n')}</div></div>
  </div>`;
  $$('[data-den]').forEach(c => c.onclick = () => { $$('[data-den]').forEach(x => x.classList.remove('on')); c.classList.add('on'); });
  $$('[data-comb]').forEach(c => c.onclick = () => { $$('[data-comb]').forEach(x => x.classList.remove('on')); c.classList.add('on'); });
  $$('[data-dev]').forEach(c => c.onclick = () => { $$('[data-dev]').forEach(x => x.classList.remove('on')); c.classList.add('on'); });
  $('#pAll').onchange = e => $$('.pModel').forEach(c => c.checked = e.target.checked);
  const collect = () => ({ start: $('#pStart').value ? +$('#pStart').value : null, end: $('#pEnd').value ? +$('#pEnd').value : null, normalize: $('#pNorm').checked, target_lufs: +$('#pLufs').value, compressor: $('#pComp').checked, denoise: $('[data-den].on').dataset.den, models: $$('.pModel:checked').map(c => c.value), combine: $('[data-comb].on').dataset.comb, device: $('[data-dev].on').dataset.dev, initial_prompt: $('#pPrompt').value, hotwords: $('#pHot').value, diarize: $('#pDiar').checked, num_speakers: $('#pNum').value ? +$('#pNum').value : null });
  if ($('#pRun')) $('#pRun').onclick = async () => { const s = collect(); if (!s.models.length) return toast('Kies minstens één model'); await put(`/projects/${S.pid}/settings`, s); await post(`/projects/${S.pid}/run`); S.meta = await api(`/projects/${S.pid}`); renderPipeline(); };
  if ($('#pCancel')) $('#pCancel').onclick = async () => { await post(`/projects/${S.pid}/cancel`); toast('Annuleren na huidige stap'); };
  if ($('#pRecomb')) $('#pRecomb').onclick = async () => { const s = collect(); await put(`/projects/${S.pid}/settings`, s); await post(`/projects/${S.pid}/recombine`, { combine: s.combine, models: s.models }); S.meta = await api(`/projects/${S.pid}`); await loadTranscript(); toast('Opnieuw gecombineerd'); renderPipeline(); };
  if ($('#pOpen')) $('#pOpen').onclick = async () => { await loadTranscript(); show('editor'); };
  clearTimeout(S.pollTimer);
  if (sd.running) S.pollTimer = setTimeout(async () => { if (S.view !== 'pipeline') return; const was = S.meta.status; S.meta = await api(`/projects/${S.pid}`); if (S.meta.status === 'klaar' && was !== 'klaar') { await loadTranscript(); toast('Verwerking klaar'); } renderPipeline(); }, 1500);
}

/* ======================= editor ======================= */
function cls(w) { if (w.p == null) return 'ed'; if (w.p < 0.4) return 'c1'; if (w.p < S.threshold) return 'c2'; if (w.p < 0.8) return 'c3'; return 'c4'; }
function spName(id) { return S.tr?.speakers?.[id]?.name || id || '?'; }
function spColor(id) { const ids = Object.keys(S.tr?.speakers || {}); const i = ids.indexOf(id); return SPEAKER_COLORS[(i < 0 ? 0 : i) % SPEAKER_COLORS.length]; }
function wordHtml(w, si, wi) { const alts = Object.values(w.alts || {}).filter(Boolean); return `<w class="${cls(w)}${alts.length ? ' alt' : ''}" data-s="${si}" data-w="${wi}" ${alts.length ? `data-n="${alts.length}" title="${esc(alts.join(' / '))}"` : ''}>${esc(w.word)}</w>`; }
function segHtml(s, si) {
  const words = s.words && s.words.length ? s.words.map((w, wi) => wordHtml(w, si, wi)).join(' ') : esc(s.text);
  return `<div class="seg ${s.reviewed ? 'reviewed' : ''} ${s.highlight ? 'hl' : ''}" data-s="${si}" id="seg${si}">
    <div class="meta"><span class="sp" style="color:${spColor(s.speaker)}" title="klik om spreker te kiezen">${esc(spName(s.speaker))}</span><span class="ts" title="klik om hier af te spelen">${fmtHMS(s.start)}</span>${s.reviewed ? '<span class="ok">✓ nagekeken</span>' : ''}</div>
    <div class="txt" contenteditable="true" spellcheck="false">${words}</div></div>${s.note ? `<div class="note">${esc(s.note)}</div>` : ''}`;
}
function renderEditor() {
  if (!S.tr) { $('#editor').innerHTML = '<div class="sub" style="padding:30px">Nog geen transcript. Verwerk het project eerst in het tabblad Pipeline.</div>'; $('#side').innerHTML = ''; $('#right').innerHTML = ''; return; }
  $('#editor').classList.toggle('heat', S.heat);
  $('#editor').innerHTML = `<div class="toolbar">
      <button class="btn small" id="tbSpk">Spreker wijzigen</button><button class="btn small" id="tbTs">Tijdcode invoegen</button><button class="btn small" id="tbHl">Markeren</button><button class="btn small" id="tbUnv">[onverstaanbaar]</button><button class="btn small" id="tbPause">(pauze)</button><button class="btn small" id="tbNote">Opmerking</button><button class="btn small" id="tbOk">✓ Nagekeken</button><button class="btn small" id="tbSplit" title="Enter">Splitsen</button><button class="btn small" id="tbMerge" title="Backspace aan begin">Samenvoegen</button>
      <span style="margin-left:auto">volgend onzeker <span class="kbd">Tab</span> · volgend meningsverschil <span class="kbd">Shift+Tab</span></span></div>
    <div id="segs">${S.tr.segments.map(segHtml).join('')}</div>`;
  bindEditor();
  renderSide(); renderRight();
  $('#tDur').textContent = '/ ' + fmtT(S.meta.audio.duration || 0);
  drawWave();
}
function bindEditor() {
  const ed = $('#segs');
  ed.onclick = e => {
    const w = e.target.closest('w');
    if (w) { selectWord(+w.dataset.s, +w.dataset.w); playWord(+w.dataset.s, +w.dataset.w); return; }
    const sp = e.target.closest('.sp'); if (sp) { speakerMenu(+sp.closest('.seg').dataset.s, sp); return; }
    const ts = e.target.closest('.ts'); if (ts) { const s = S.tr.segments[+ts.closest('.seg').dataset.s]; S.curSeg = +ts.closest('.seg').dataset.s; playRange(s.start, s.end); }
  };
  ed.onfocusin = e => { const seg = e.target.closest('.seg'); if (seg) { S.curSeg = +seg.dataset.s; $$('.seg.active').forEach(x => x.classList.remove('active')); seg.classList.add('active'); } };
  ed.onfocusout = e => { const txt = e.target.closest('.txt'); if (txt) commitSegment(+txt.closest('.seg').dataset.s); };
  ed.oninput = e => { const txt = e.target.closest('.txt'); if (txt) { markDirty(); if ($('#autoPause').checked) typingPause(); } };
  ed.onkeydown = e => {
    const txt = e.target.closest('.txt'); if (!txt) return;
    const si = +txt.closest('.seg').dataset.s;
    if (e.key === 'Enter' && !e.ctrlKey && !e.shiftKey) { e.preventDefault(); splitAtCaret(si); }
    if (e.key === 'Backspace' && caretAtStart(txt) && si > 0) { e.preventDefault(); mergeWithPrevious(si); }
  };
  $('#tbSpk').onclick = () => S.curSeg != null && cycleSpeaker(S.curSeg);
  $('#tbTs').onclick = () => insertText(`[${fmtHMS(audio.currentTime)}] `);
  $('#tbHl').onclick = () => toggleFlag('highlight');
  $('#tbUnv').onclick = () => insertText(`[onverstaanbaar ${fmtHMS(audio.currentTime)}] `);
  $('#tbPause').onclick = () => insertText('(...) ');
  $('#tbNote').onclick = () => { if (S.curSeg == null) return; const s = S.tr.segments[S.curSeg]; const n = prompt('Opmerking bij dit segment', s.note || ''); if (n != null) { s.note = n; markDirty(); rerenderSeg(S.curSeg); } };
  $('#tbOk').onclick = () => toggleFlag('reviewed', true);
  $('#tbSplit').onclick = () => S.curSeg != null && splitAtCaret(S.curSeg);
  $('#tbMerge').onclick = () => S.curSeg != null && S.curSeg > 0 && mergeWithPrevious(S.curSeg);
}
function renderSide() {
  const segs = S.tr.segments, words = segs.flatMap(s => s.words || []);
  const unc = words.filter(w => w.p != null && w.p < S.threshold).length, dis = words.filter(w => w.disagree).length;
  const rev = segs.filter(s => s.reviewed).length, hl = segs.filter(s => s.highlight).length;
  const spk = Object.entries(S.tr.speakers || {});
  const counts = {}; segs.forEach(s => counts[s.speaker] = (counts[s.speaker] || 0) + (s.end - s.start));
  const tot = Object.values(counts).reduce((a, b) => a + b, 0) || 1;
  $('#side').innerHTML = `<h4 class="lbl">Sprekers</h4>${spk.map(([id, sp]) => `<div class="spk"><span class="dot" style="background:${spColor(id)}"></span><input value="${esc(sp.name)}" data-sp="${id}"><small>${Math.round((counts[id] || 0) / tot * 100)}%</small></div>`).join('')}<div class="spk" style="color:var(--muted2);cursor:pointer" id="addSpk">+ spreker toevoegen</div>
    <h4 class="lbl" style="margin-top:16px">Weergave</h4>
    <div><span class="chip ${S.style === 'verbatim' ? 'on' : ''}" data-style="verbatim">Verbatim</span><span class="chip ${S.style === 'clean' ? 'on' : ''}" data-style="clean">Clean verbatim</span></div>
    <div class="stat" style="margin-top:6px"><label><input type="checkbox" id="heatChk" ${S.heat ? 'checked' : ''}> zekerheidsheatmap</label></div>
    <div class="stat"><span>drempel onzeker</span><input type="range" id="thr" min="0.3" max="0.9" step="0.05" value="${S.threshold}" style="width:90px"><b id="thrV">${S.threshold}</b></div>
    <h4 class="lbl" style="margin-top:16px">Voortgang</h4>
    <div class="stat"><span>Woorden</span><b>${words.length}</b></div>
    <div class="stat"><span>Onzeker (&lt;${S.threshold})</span><b style="color:var(--warn)">${unc}</b></div>
    <div class="stat"><span>Modellen oneens</span><b style="color:var(--blue)">${dis}</b></div>
    <div class="stat"><span>Segmenten nagekeken</span><b>${rev} / ${segs.length}</b></div>
    <div class="stat"><span>Highlights</span><b>${hl}</b></div>
    <h4 class="lbl" style="margin-top:16px">Zekerheid</h4><div class="bar"></div><div class="l"><span>&lt;0,4</span><span>${S.threshold}</span><span>0,8</span><span>zeker</span></div>
    <div style="font-size:11px;color:var(--muted2);margin-top:6px">Licht gekleurd is een hint, geen fout. Gestippeld = door jou bewerkt.</div>
    <h4 class="lbl" style="margin-top:16px">Modellen</h4>${(S.tr.models || []).map(m => `<div class="stat"><span>${esc(m)}${m === S.tr.base_model ? ' (basis)' : ''}</span><b>${S.meta.summary?.[m]?.mean_p ?? ''}</b></div>`).join('')}`;
  $$('#side input[data-sp]').forEach(inp => inp.onchange = () => { S.tr.speakers[inp.dataset.sp].name = inp.value; markDirty(); renderEditor(); });
  $('#addSpk').onclick = () => { const n = Object.keys(S.tr.speakers).length + 1; S.tr.speakers['S' + n] = { name: 'Spreker ' + n }; markDirty(); renderSide(); };
  $$('[data-style]').forEach(c => c.onclick = () => { S.style = c.dataset.style; toast(S.style === 'clean' ? 'Clean verbatim geldt bij export; de editor toont altijd alles' : 'Verbatim'); renderSide(); });
  $('#heatChk').onchange = e => { S.heat = e.target.checked; $('#editor').classList.toggle('heat', S.heat); };
  $('#thr').oninput = e => { S.threshold = +e.target.value; $('#thrV').textContent = S.threshold; };
  $('#thr').onchange = () => { S.meta.settings.uncertain_threshold = S.threshold; put(`/projects/${S.pid}/settings`, { uncertain_threshold: S.threshold }); renderEditor(); };
}
function renderRight() {
  let wordCard = '<div class="card"><h5>Geselecteerd woord</h5><div class="sub">Klik op een woord om het fragment af te spelen en alternatieven te zien.</div></div>';
  if (S.curWord) {
    const [si, wi] = S.curWord, w = S.tr.segments[si].words[wi];
    const lanes = [[S.tr.base_model, w.base ?? w.word, w.p]].concat(Object.entries(w.alts || {}).map(([m, a]) => [m, a, null]));
    const seen = new Set();
    wordCard = `<div class="card"><h5>Geselecteerd woord · ${fmtT(w.start, true)}</h5>
      ${lanes.map(([m, txt, p]) => `<div class="lane"><span class="m">${esc(m)}</span><span class="w ${normW(txt) === normW(w.word) ? 'pick' : ''}" data-alt="${esc(txt)}">${esc(txt || '—')}</span>${p != null ? `<span>${Math.round(p * 100)}%</span>` : ''}</div>`).join('')}
      <div class="row" style="margin-top:6px"><span>Modellen eens</span><b>${w.agree ?? 1} van ${w.n_models ?? 1}</b></div>
      <div class="row"><span>Zekerheid</span><b style="color:${w.p == null ? 'var(--muted)' : w.p < S.threshold ? 'var(--warn)' : 'var(--text)'}">${w.p == null ? 'bewerkt' : Math.round(w.p * 100) + '%'}</b></div>
      <div style="margin-top:6px">${[...new Set(lanes.map(l => l[1]).filter(Boolean))].map(t => `<span class="chip ${normW(t) === normW(w.word) ? 'on' : ''}" data-alt="${esc(t)}">${esc(t)}</span>`).join('')}<span class="chip" id="altCustom">eigen tekst…</span></div></div>`;
  }
  $('#right').innerHTML = wordCard + `
    <div class="card"><h5>Opmerking bij segment</h5><div style="color:var(--muted);font-style:italic">${S.curSeg != null && S.tr.segments[S.curSeg].note ? esc(S.tr.segments[S.curSeg].note) : 'Geen. Knop "Opmerking" in de werkbalk.'}</div></div>
    <div class="card"><h5>Sneltoetsen</h5>
      <div class="row"><span>Play / pauze</span><span class="kbd">Ctrl+Space</span></div><div class="row"><span>3 s terug / vooruit</span><span class="kbd">Ctrl+← →</span></div>
      <div class="row"><span>Volgend onzeker woord</span><span class="kbd">Tab</span></div><div class="row"><span>Volgend meningsverschil</span><span class="kbd">Shift+Tab</span></div>
      <div class="row"><span>Segment nagekeken</span><span class="kbd">Ctrl+Enter</span></div><div class="row"><span>Spreker wisselen</span><span class="kbd">Ctrl+S</span></div>
      <div class="row"><span>Highlight</span><span class="kbd">Ctrl+H</span></div><div class="row"><span>[onverstaanbaar]</span><span class="kbd">Ctrl+U</span></div>
      <div class="row"><span>Splitsen / samenvoegen</span><span class="kbd">Enter / ⌫</span></div></div>`;
  $$('#right [data-alt]').forEach(el => el.onclick = () => setWord(S.curWord[0], S.curWord[1], el.dataset.alt));
  if ($('#altCustom')) $('#altCustom').onclick = () => { const t = prompt('Vervang door', S.tr.segments[S.curWord[0]].words[S.curWord[1]].word); if (t != null) setWord(S.curWord[0], S.curWord[1], t); };
}
function selectWord(si, wi) { S.curWord = [si, wi]; S.curSeg = si; $$('w.cur').forEach(x => x.classList.remove('cur')); const el = $(`w[data-s="${si}"][data-w="${wi}"]`); if (el) { el.classList.add('cur'); } renderRight(); }
function setWord(si, wi, text) { const w = S.tr.segments[si].words[wi]; if (!w) return; w.word = text; w.edited = true; w.p = w.p ?? null; const s = S.tr.segments[si]; s.text = s.words.map(x => x.word).join(' '); markDirty(); rerenderSeg(si); selectWord(si, wi); }
function rerenderSeg(si) { const s = S.tr.segments[si]; const old = $(`#seg${si}`); if (!old) return renderEditor(); const tmp = document.createElement('div'); tmp.innerHTML = segHtml(s, si); const note = old.nextElementSibling && old.nextElementSibling.classList.contains('note') ? old.nextElementSibling : null; if (note) note.remove(); old.replaceWith(...tmp.childNodes); }

/* ---- tekst → woorden terugvertalen (LCS-diff op tokens) ---- */
function commitSegment(si) {
  const s = S.tr.segments[si]; const el = $(`#seg${si} .txt`); if (!el) return;
  const tokens = el.textContent.replace(/\s+/g, ' ').trim().split(' ').filter(Boolean);
  const oldWords = s.words || [];
  if (tokens.join(' ') === oldWords.map(w => w.word).join(' ')) return;
  // LCS op genormaliseerde tokens
  const a = oldWords.map(w => normW(w.word)), b = tokens.map(normW);
  const n = a.length, m = b.length, L = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) L[i][j] = a[i] === b[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
  const out = []; let i = 0, j = 0, lastEnd = s.start;
  const pending = [];
  const flush = (nextStart) => { // niet-gematchte nieuwe tokens krijgen tijd tussen lastEnd en nextStart
    if (!pending.length) return; const span = Math.max(0.05, (nextStart - lastEnd)) / pending.length;
    pending.forEach((t, k) => out.push({ start: lastEnd + k * span, end: lastEnd + (k + 1) * span, word: t, p: null, edited: true, alts: {}, agree: 1, n_models: 1 }));
    pending.length = 0;
  };
  while (i < n && j < m) {
    if (a[i] === b[j]) { flush(oldWords[i].start); const w = { ...oldWords[i], word: tokens[j] }; if (tokens[j] !== oldWords[i].word) w.edited = true; out.push(w); lastEnd = w.end; i++; j++; }
    else if (L[i + 1][j] >= L[i][j + 1]) i++; else { pending.push(tokens[j]); j++; }
  }
  while (j < m) pending.push(tokens[j++]);
  flush(s.end);
  s.words = out; s.text = tokens.join(' ');
  markDirty(); rerenderSeg(si);
}
function caretAtStart(el) { const sel = window.getSelection(); if (!sel.rangeCount) return false; const r = sel.getRangeAt(0).cloneRange(); r.selectNodeContents(el); r.setEnd(sel.anchorNode, sel.anchorOffset); return r.toString().trim().length === 0; }
function caretWordIndex(el) { const sel = window.getSelection(); if (!sel.rangeCount) return null; const r = sel.getRangeAt(0).cloneRange(); r.selectNodeContents(el); r.setEnd(sel.anchorNode, sel.anchorOffset); return r.toString().replace(/\s+/g, ' ').trim().split(' ').filter(Boolean).length; }
function splitAtCaret(si) {
  const el = $(`#seg${si} .txt`); commitSegment(si); const s = S.tr.segments[si]; const k = caretWordIndex(el);
  if (k == null || k <= 0 || k >= s.words.length) return;
  const w2 = s.words.slice(k), w1 = s.words.slice(0, k);
  const s2 = { ...s, id: Date.now(), start: w2[0].start, end: s.end, words: w2, text: w2.map(w => w.word).join(' '), reviewed: false, note: '' };
  Object.assign(s, { end: w1[w1.length - 1].end, words: w1, text: w1.map(w => w.word).join(' ') });
  S.tr.segments.splice(si + 1, 0, s2); markDirty(); renderEditor(); const t = $(`#seg${si + 1} .txt`); if (t) t.focus();
}
function mergeWithPrevious(si) {
  commitSegment(si); const a = S.tr.segments[si - 1], b = S.tr.segments[si];
  a.words = [...(a.words || []), ...(b.words || [])]; a.text = a.words.map(w => w.word).join(' '); a.end = b.end; a.note = [a.note, b.note].filter(Boolean).join(' | ');
  S.tr.segments.splice(si, 1); markDirty(); renderEditor(); const t = $(`#seg${si - 1} .txt`); if (t) t.focus();
}
function insertText(text) { if (S.curSeg == null) return toast('Klik eerst in een segment'); const el = $(`#seg${S.curSeg} .txt`); el.focus(); document.execCommand('insertText', false, text); markDirty(); }
function toggleFlag(flag, value) { if (S.curSeg == null) return; const s = S.tr.segments[S.curSeg]; s[flag] = value === undefined ? !s[flag] : (s[flag] ? false : value); markDirty(); rerenderSeg(S.curSeg); renderSide(); }
function cycleSpeaker(si) { const ids = Object.keys(S.tr.speakers); const s = S.tr.segments[si]; s.speaker = ids[(ids.indexOf(s.speaker) + 1) % ids.length]; markDirty(); rerenderSeg(si); renderSide(); }
function speakerMenu(si, anchor) {
  $$('.dropdown').forEach(d => d.remove()); const d = document.createElement('div'); d.className = 'dropdown';
  const r = anchor.getBoundingClientRect(); d.style.left = r.left + 'px'; d.style.top = (r.bottom + 4) + 'px';
  d.innerHTML = Object.entries(S.tr.speakers).map(([id, sp]) => `<div data-id="${id}" style="color:${spColor(id)}">${esc(sp.name)}</div>`).join('') + `<div data-id="__new">+ nieuwe spreker</div><div data-id="__rest" style="color:var(--muted)">deze én alle volgende van dezelfde spreker…</div>`;
  document.body.appendChild(d);
  d.onclick = e => { const id = e.target.dataset.id; if (!id) return; const s = S.tr.segments[si];
    if (id === '__new') { const n = Object.keys(S.tr.speakers).length + 1; S.tr.speakers['S' + n] = { name: 'Spreker ' + n }; s.speaker = 'S' + n; }
    else if (id === '__rest') { const target = prompt('Naar welke spreker? (nummer 1..' + Object.keys(S.tr.speakers).length + ')'); const tid = Object.keys(S.tr.speakers)[(+target) - 1]; if (tid) { const from = s.speaker; for (let k = si; k < S.tr.segments.length; k++) if (S.tr.segments[k].speaker === from) S.tr.segments[k].speaker = tid; } }
    else s.speaker = id;
    d.remove(); markDirty(); renderEditor(); };
  setTimeout(() => document.addEventListener('click', () => d.remove(), { once: true }), 0);
}

/* ---- zoeken, woordenlijst, sneltoetsen ---- */
function modal(html) { const m = document.createElement('div'); m.className = 'modal'; m.innerHTML = `<div class="box">${html}</div>`; m.onclick = e => { if (e.target === m) m.remove(); }; document.body.appendChild(m); return m; }
function findReplace() {
  const m = modal(`<h3>Zoek &amp; vervang</h3><div class="form"><label>Zoek</label><input type="text" id="fFind"><label>Vervang door</label><input type="text" id="fRepl"><label><input type="checkbox" id="fCase"> hoofdlettergevoelig</label><label><input type="checkbox" id="fSpk"> ook in sprekernamen</label><div style="margin-top:12px;display:flex;gap:8px"><button class="btn primary" id="fGo">Vervang alles</button><button class="btn" id="fCount">Tel</button></div><div id="fRes" class="sub" style="margin-top:8px"></div></div>`);
  const run = (doit) => { const f = $('#fFind').value; if (!f) return; const cs = $('#fCase').checked; const re = new RegExp(f.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), cs ? 'g' : 'gi'); let n = 0;
    S.tr.segments.forEach(s => (s.words || []).forEach(w => { if (re.test(w.word)) { n++; if (doit) { w.word = w.word.replace(re, $('#fRepl').value); w.edited = true; } } re.lastIndex = 0; }));
    if (doit) { S.tr.segments.forEach(s => s.text = (s.words || []).map(w => w.word).join(' ')); if ($('#fSpk').checked) Object.values(S.tr.speakers).forEach(sp => sp.name = sp.name.replace(re, $('#fRepl').value)); markDirty(); renderEditor(); }
    $('#fRes').textContent = `${n} ${doit ? 'vervangen' : 'gevonden'}`; };
  $('#fGo').onclick = () => run(true); $('#fCount').onclick = () => run(false); $('#fFind').focus();
}
function editDictionary() {
  const m = modal(`<h3>Woordenlijst</h3><div class="sub">Namen, plaatsen en vaktermen. Wordt als context aan Whisper meegegeven bij een volgende verwerking, zodat ze beter herkend worden.</div><div class="form"><textarea id="dictTxt" style="min-height:120px">${esc(S.meta.settings.initial_prompt || '')}</textarea><div style="margin-top:10px"><button class="btn primary" id="dictSave">Opslaan</button></div></div>`);
  $('#dictSave').onclick = async () => { S.meta.settings.initial_prompt = $('#dictTxt').value; await put(`/projects/${S.pid}/settings`, { initial_prompt: $('#dictTxt').value }); m.remove(); toast('Woordenlijst opgeslagen; geldt bij de volgende verwerking'); };
}
function showKeys() { modal(`<h3>Sneltoetsen</h3>${$('#right .card:last-child').innerHTML.replace('<h5>Sneltoetsen</h5>', '')}<div class="row"><span>Klik op woord</span><span>fragment afspelen</span></div><div class="row"><span>Klik op tijdcode</span><span>segment afspelen</span></div><div class="row"><span>Sleep in golfvorm</span><span>selectie loopen</span></div>`); }

/* ---- navigatie door onzekere woorden ---- */
function nextWord(pred) {
  const segs = S.tr.segments; let [si, wi] = S.curWord || [S.curSeg ?? 0, -1];
  for (let k = 0; k < segs.length + 1; k++) { const s = segs[si]; for (let j = (k === 0 ? wi + 1 : 0); j < (s.words || []).length; j++) if (pred(s.words[j])) { selectWord(si, j); $(`#seg${si}`).scrollIntoView({ block: 'center', behavior: 'smooth' }); playWord(si, j); return; } si = (si + 1) % segs.length; }
  toast('Niets meer gevonden');
}

/* ======================= audio ======================= */
function ensureAudioGraph() { if (audioCtx) return; try { audioCtx = new (window.AudioContext || window.webkitAudioContext)(); const src = audioCtx.createMediaElementSource(audio); gainNode = audioCtx.createGain(); src.connect(gainNode).connect(audioCtx.destination); } catch (e) { console.warn('geen Web Audio', e); } }
function play() { ensureAudioGraph(); if (audioCtx && audioCtx.state === 'suspended') audioCtx.resume(); audio.play(); }
function playRange(a, b) { S.playWindow = [Math.max(0, a), b]; audio.currentTime = Math.max(0, a); play(); }
function playWord(si, wi) { const w = S.tr.segments[si].words[wi]; if (!w) return; const pre = +$('#preRoll').value || 0, post = +$('#postRoll').value || 0; playRange(w.start - pre, w.end + post); }
function togglePlay() { if (audio.paused) { const rw = +$('#rewind').value || 0; if (rw && audio.currentTime > 0) audio.currentTime = Math.max(0, audio.currentTime - rw); S.playWindow = null; play(); } else audio.pause(); }
function typingPause() { if (!audio.paused) { S.wasPlaying = true; audio.pause(); } clearTimeout(S.typingTimer); S.typingTimer = setTimeout(() => { if (S.wasPlaying) { S.wasPlaying = false; const rw = +$('#rewind').value || 0; audio.currentTime = Math.max(0, audio.currentTime - rw); play(); } }, 2000); }
audio.ontimeupdate = () => {
  $('#tCur').textContent = fmtT(audio.currentTime, true);
  if (S.playWindow && audio.currentTime >= S.playWindow[1]) { if ($('#loopChk').checked) audio.currentTime = S.playWindow[0]; else { audio.pause(); } }
  if (S.loopSel && audio.currentTime >= S.loopSel[1]) audio.currentTime = S.loopSel[0];
  highlightPlaying(); drawWave();
};
audio.onplay = () => $('#btnPlay').textContent = '❚❚'; audio.onpause = () => $('#btnPlay').textContent = '▶';
$('#btnPlay').onclick = togglePlay;
$('#btnBack').onclick = () => audio.currentTime = Math.max(0, audio.currentTime - 3);
$('#btnFwd').onclick = () => audio.currentTime += 3;
$('#speed').onchange = e => audio.playbackRate = +e.target.value;
$('#gain').onchange = e => { ensureAudioGraph(); if (gainNode) gainNode.gain.value = +e.target.value; };
$('#origAudio').onchange = () => { const t = audio.currentTime, p = !audio.paused; audio.src = `/api/projects/${S.pid}/audio${$('#origAudio').checked ? '?original=1' : ''}`; audio.currentTime = t; if (p) play(); };
let lastPlaying = null;
function highlightPlaying() {
  if (!S.tr) return; const t = audio.currentTime;
  const segs = S.tr.segments; let found = null;
  for (let si = 0; si < segs.length; si++) { const s = segs[si]; if (t < s.start - 0.3 || t > s.end + 0.3) continue; for (let wi = 0; wi < (s.words || []).length; wi++) { const w = s.words[wi]; if (t >= w.start && t <= w.end) { found = `w[data-s="${si}"][data-w="${wi}"]`; break; } } if (found) break; }
  if (found !== lastPlaying) { $$('w.playing').forEach(x => x.classList.remove('playing')); if (found) { const el = $(found); if (el) { el.classList.add('playing'); if (document.activeElement && !document.activeElement.closest('.txt')) el.scrollIntoView({ block: 'nearest' }); } } lastPlaying = found; }
}
/* ---- golfvorm ---- */
function drawWave() {
  const c = $('#waveCanvas'); if (!c || S.view !== 'editor') return; const W = c.clientWidth, H = 46; if (c.width !== W * devicePixelRatio) { c.width = W * devicePixelRatio; c.height = H * devicePixelRatio; }
  const ctx = c.getContext('2d'); ctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0); ctx.clearRect(0, 0, W, H);
  const dur = S.meta.audio.duration || audio.duration || 1, pk = S.peaks; const n = pk.length || 1;
  const sel = S.loopSel || S.playWindow;
  if (sel) { ctx.fillStyle = 'rgba(43,108,176,.10)'; ctx.fillRect(sel[0] / dur * W, 0, (sel[1] - sel[0]) / dur * W, H); }
  for (let x = 0; x < W; x += 3) { const i = Math.floor(x / W * n); const v = pk[i] || 0; const h = Math.max(2, v * (H - 6)); const t = x / W * dur; ctx.fillStyle = (S.tr && S.tr.segments.some(s => t >= s.start && t <= s.end && s.words && s.words.some(w => w.p != null && w.p < S.threshold && t >= w.start && t <= w.end))) ? '#f0a042' : '#d9d6ce'; ctx.fillRect(x, H - h, 2, h); }
  ctx.fillStyle = '#2b6cb0'; ctx.fillRect(audio.currentTime / dur * W - 1, 0, 2, H);
}
const wave = $('#wave'); let dragStart = null;
wave.onmousedown = e => { dragStart = e.offsetX; };
wave.onmousemove = e => { if (dragStart == null) return; const dur = S.meta.audio.duration || 1, W = wave.clientWidth; const a = Math.min(dragStart, e.offsetX) / W * dur, b = Math.max(dragStart, e.offsetX) / W * dur; if (b - a > 0.3) { S.loopSel = [a, b]; drawWave(); } };
wave.onmouseup = e => { const dur = S.meta.audio.duration || 1, W = wave.clientWidth; if (S.loopSel && Math.abs(e.offsetX - dragStart) > 4) { audio.currentTime = S.loopSel[0]; play(); } else { S.loopSel = null; S.playWindow = null; audio.currentTime = e.offsetX / W * dur; play(); } dragStart = null; drawWave(); };
window.addEventListener('resize', drawWave);

/* ======================= autosave ======================= */
function markDirty() { S.dirty = true; $('#saveState').textContent = '● niet opgeslagen'; $('#saveState').classList.add('dirty'); clearTimeout(S.saveTimer); S.saveTimer = setTimeout(save, 1500); }
async function save() {
  if (!S.dirty || !S.tr) return; S.dirty = false;
  try { const r = await put(`/projects/${S.pid}/transcript`, S.tr); S.tr.version = r.version; $('#saveState').textContent = `● opgeslagen ${new Date().toLocaleTimeString().slice(0, 5)} · versie ${r.version}`; $('#saveState').classList.remove('dirty'); }
  catch (e) { S.dirty = true; $('#saveState').textContent = '● opslaan mislukt: ' + e.message; toast('Opslaan mislukt'); }
}
window.addEventListener('beforeunload', e => { if (S.dirty) { save(); e.preventDefault(); e.returnValue = ''; } });
setInterval(() => { if (S.dirty) save(); }, 10000);

/* ======================= sneltoetsen ======================= */
document.addEventListener('keydown', e => {
  if (S.view !== 'editor' || !S.tr) return;
  const inTxt = e.target.closest && e.target.closest('.txt');
  if (e.ctrlKey && e.code === 'Space') { e.preventDefault(); togglePlay(); }
  else if (e.ctrlKey && e.key === 'ArrowLeft') { e.preventDefault(); audio.currentTime = Math.max(0, audio.currentTime - 3); }
  else if (e.ctrlKey && e.key === 'ArrowRight') { e.preventDefault(); audio.currentTime += 3; }
  else if (e.key === 'Tab' && !e.ctrlKey) { e.preventDefault(); if (inTxt) commitSegment(+inTxt.closest('.seg').dataset.s); nextWord(e.shiftKey ? (w => w.disagree) : (w => w.p != null && w.p < S.threshold)); }
  else if (e.ctrlKey && e.key === 'Enter') { e.preventDefault(); if (inTxt) commitSegment(+inTxt.closest('.seg').dataset.s); toggleFlag('reviewed', true); const n = S.curSeg + 1; if (S.tr.segments[n]) { const t = $(`#seg${n} .txt`); if (t) { t.focus(); S.curSeg = n; } } }
  else if (e.ctrlKey && e.key.toLowerCase() === 's') { e.preventDefault(); if (S.curSeg != null) cycleSpeaker(S.curSeg); }
  else if (e.ctrlKey && e.key.toLowerCase() === 'h') { e.preventDefault(); toggleFlag('highlight'); }
  else if (e.ctrlKey && e.key.toLowerCase() === 'u') { e.preventDefault(); insertText(`[onverstaanbaar ${fmtHMS(audio.currentTime)}] `); }
  else if (e.ctrlKey && e.key.toLowerCase() === 'f') { e.preventDefault(); findReplace(); }
  else if (e.key === 'Escape') { audio.pause(); S.loopSel = null; S.playWindow = null; drawWave(); }
});

/* ======================= vergelijken ======================= */
async function renderCompare() {
  if (!S.tr) { $('#cmp').innerHTML = '<div class="sub">Nog geen transcript.</div>'; return; }
  S.runs = S.runs || await api(`/projects/${S.pid}/runs`);
  const models = [...(S.tr.models || []).filter(m => S.runs[m]), ...Object.keys(S.runs).filter(m => !(S.tr.models || []).includes(m))]; const segs = S.tr.segments;
  const wordsIn = (m, a, b) => S.runs[m].words.filter(w => w.end > a && w.start < b);
  const stats = { all: 0, maj: 0, none: 0, n: 0 }; const tl = [];
  segs.forEach(s => { let bad = 0; (s.words || []).forEach(w => { stats.n++; if (!w.disagree) stats.all++; else if ((w.agree || 1) * 2 > (w.n_models || 1)) stats.maj++; else { stats.none++; bad++; } }); tl.push(bad ? (bad > 2 ? 'x' : 'd') : ''); });
  const pct = k => stats.n ? Math.round(stats[k] / stats.n * 100) + '%' : '–';
  $('#cmp').innerHTML = `<h2 style="margin:0 0 4px">Modellen vergelijken</h2><div class="sub">${models.length} model(len), per segment op tijd uitgelijnd. Klik een woord in een modelrij om die variant in het transcript te zetten. Oranje wijkt af van het transcript, rood heeft geen meerderheid.</div>
    <div class="legend"><span><i style="background:var(--accent-bg);border-bottom:2px solid var(--accent)"></i>In transcript</span><span><i style="background:var(--c2b);border-bottom:2px solid var(--c2)"></i>Wijkt af</span><span><i style="background:var(--c1b);border-bottom:2px solid var(--c1)"></i>Geen meerderheid</span></div>
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:14px"><div class="card"><small>Alle modellen eens</small><div style="font-size:22px;font-weight:700">${pct('all')}</div></div><div class="card"><small>Meerderheid</small><div style="font-size:22px;font-weight:700">${pct('maj')}</div></div><div class="card"><small>Geen meerderheid</small><div style="font-size:22px;font-weight:700;color:var(--warn)">${pct('none')}</div><small>${stats.none} woorden</small></div><div class="card"><small>Segmenten</small><div style="font-size:22px;font-weight:700">${segs.length}</div></div></div>
    <div class="card"><h5>Overeenstemming over het hele interview (klik om te springen)</h5><div class="tl">${tl.map((c, i) => `<i class="${c}" data-i="${i}" title="${fmtHMS(segs[i].start)}"></i>`).join('')}</div></div>
    <label class="cb" style="display:inline-flex;margin-bottom:10px"><input type="checkbox" id="cmpOnly" checked> alleen segmenten met verschillen</label>
    <div id="cmpList"></div>`;
  const render = () => {
    const only = $('#cmpOnly').checked;
    $('#cmpList').innerHTML = segs.map((s, si) => {
      if (only && !(s.words || []).some(w => w.disagree)) return '';
      const rows = models.map(m => { const ws = wordsIn(m, s.start, s.end); const cur = new Set((s.words || []).map(w => normW(w.word)));
        return `<div class="lbl2">${esc(m)}<small>${S.runs[m].stats.mean_p}</small></div><div class="t">${ws.map(w => `<w class="${cur.has(normW(w.word)) ? 'same' : 'diff'}" data-si="${si}" data-t="${w.start}" data-txt="${esc(w.word)}" title="${Math.round(w.p * 100)}%">${esc(w.word)}</w>`).join(' ')}</div>`; }).join('');
      const cons = `<div class="lbl2" style="background:var(--accent-bg)">Transcript<small>${esc(spName(s.speaker))}</small></div><div class="t">${(s.words || []).map((w, wi) => `<w class="${w.disagree ? ((w.agree || 1) * 2 > (w.n_models || 1) ? 'pick' : 'open') : 'pick'}" data-go="${si}:${wi}">${esc(w.word)}</w>`).join(' ')}</div>`;
      return `<div style="font-size:13px;color:var(--muted);margin:10px 0 4px"><b>${fmtHMS(s.start)} – ${fmtHMS(s.end)}</b> · ${esc(spName(s.speaker))}</div><div class="grid" id="cmpSeg${si}">${rows}${cons}</div>`; }).join('') || '<div class="sub">Geen verschillen.</div>';
  };
  render(); $('#cmpOnly').onchange = render;
  $('#cmp').onclick = e => {
    const tli = e.target.closest('.tl i'); if (tli) { const el = $(`#cmpSeg${tli.dataset.i}`); if (el) el.scrollIntoView({ block: 'center', behavior: 'smooth' }); else { $('#cmpOnly').checked = false; render(); $(`#cmpSeg${tli.dataset.i}`)?.scrollIntoView({ block: 'center' }); } return; }
    const w = e.target.closest('w'); if (!w) return;
    if (w.dataset.go) { const [si, wi] = w.dataset.go.split(':').map(Number); playWord(si, wi); return; }
    const si = +w.dataset.si, t = +w.dataset.t, s = S.tr.segments[si];
    let best = null, bd = 9; (s.words || []).forEach((x, i) => { const d = Math.abs(x.start - t); if (d < bd) { bd = d; best = i; } });
    if (best != null && bd < 1.0) { setWord(si, best, w.dataset.txt); render(); toast(`"${w.dataset.txt}" overgenomen`); }
    playRange(t - 1.5, t + 2);
  };
}

/* ======================= export ======================= */
function renderExport() {
  if (!S.tr) { $('#exp').innerHTML = '<div class="sub">Nog geen transcript.</div>'; return; }
  const names = Object.values(S.tr.speakers).map(s => s.name);
  $('#exp').innerHTML = `<h2 style="margin:0 0 4px">Exporteren</h2><div class="sub">Alle exports komen uit hetzelfde transcript; instellingen hieronder gelden voor elk formaat.</div>
    <div class="form card">
      <div class="row"><span>Stijl</span><span><span class="chip ${S.style === 'verbatim' ? 'on' : ''}" data-es="verbatim">Verbatim</span><span class="chip ${S.style === 'clean' ? 'on' : ''}" data-es="clean">Clean verbatim (eh/uhm weg)</span></span></div>
      <div class="row"><span>Tijdcodes</span><select id="eTs" class="k"><option value="paragraph">per alinea</option><option value="minute">per minuut</option><option value="none">geen</option></select></div>
      <div class="row"><span>Tijdcodeformaat</span><select id="eFmt" class="k"><option value="brackets">[00:01:23] (MAXQDA, NVivo)</option><option value="dp">#00:01:23-4# (Dresing &amp; Pehl, f4)</option></select></div>
      <div class="row"><span>Sprekernamen</span><input type="checkbox" id="eSpk" checked></div>
      <div class="row"><span>Alleen highlights</span><input type="checkbox" id="eHl"></div>
      <label>Anonimiseren (één per regel: naam = plaatshouder)</label><textarea id="eAnon" placeholder="${esc(names.join(' = [persoon1]\n'))} = [persoon1]"></textarea>
    </div>
    <div class="fmt">
      <button data-f="docx"><b>Word (.docx)</b><small>alinea per spreker, tijdcodes</small></button>
      <button data-f="txt"><b>Tekst (.txt)</b><small>platte tekst met tijdcodes</small></button>
      <button data-f="maxqda"><b>MAXQDA / NVivo</b><small>tijdcode per alinea, spreker bij wissel</small></button>
      <button data-f="csv"><b>CSV segmenten</b><small>start, eind, spreker, tekst, zekerheid, status</small></button>
      <button data-f="csv_words"><b>CSV woorden</b><small>elk woord met tijd, zekerheid en alternatieven</small></button>
      <button data-f="srt"><b>Ondertitels (.srt)</b><small>per segment</small></button>
      <button data-f="json"><b>JSON</b><small>volledig projectbestand</small></button>
    </div>`;
  $$('[data-es]').forEach(c => c.onclick = () => { S.style = c.dataset.es; renderExport(); });
  $$('.fmt button').forEach(b => b.onclick = async () => {
    const anon = {}; $('#eAnon').value.split('\n').forEach(l => { const [k, v] = l.split('='); if (k && v) anon[k.trim()] = v.trim(); });
    const opts = { style: S.style, timestamps: $('#eTs').value, ts_format: $('#eFmt').value, speakers: $('#eSpk').checked, highlights_only: $('#eHl').checked, anonymize: anon, threshold: S.threshold };
    await save();
    const r = await fetch(`/api/projects/${S.pid}/export/${b.dataset.f}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(opts) });
    if (!r.ok) return toast('Export mislukt');
    const blob = await r.blob(); const cd = r.headers.get('content-disposition') || ''; const fn = (cd.match(/filename="([^"]+)"/) || [])[1] || 'export';
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = fn; a.click(); URL.revokeObjectURL(a.href);
  });
}

/* ======================= start ======================= */
(async () => {
  S.info = await api('/info');
  const h = new URLSearchParams(location.hash.slice(1));
  if (h.get('p')) { try { await openProject(h.get('p')); if (h.get('v')) show(h.get('v')); return; } catch (e) { toast('Project niet gevonden'); } }
  show('home');
})();
const _show = show; show = function (v) { _show(v); if (S.pid && v !== 'home') history.replaceState(null, '', `#p=${encodeURIComponent(S.pid)}&v=${v}`); else history.replaceState(null, '', location.pathname); };
