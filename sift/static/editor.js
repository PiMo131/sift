/* editor.js: nakijkmodus — rustige tekst, aandachtspunten met Vorig/Volgend en filters, markeringen (citaat / later
   luisteren), inklapbare zijpanelen, luisteren, bewerken via History (ongedaan maken), sneltoetsen. */
'use strict';

/* ---------- woorden en aandachtspunten ---------- */
function cls(w) { if (w.p == null) return 'ed'; if (w.p < 0.4) return 'c1'; if (w.p < S.threshold) return 'c2'; if (w.p < 0.8) return 'c3'; return 'c4'; }
function attKinds(w) { const k = []; if (w.p != null && w.p < S.threshold && !w.edited) k.push('uncertain'); if (w.disagree) k.push('disagree'); if (w.later) k.push('later'); return k; }
function pointDone(w) { return !!w.checked && !w.later; }
function spName(id) { return S.tr?.speakers?.[id]?.name || id || '?'; }
function spColor(id) { const ids = Object.keys(S.tr?.speakers || {}); const i = ids.indexOf(id); return SPEAKER_COLORS[(i < 0 ? 0 : i) % SPEAKER_COLORS.length]; }
const KIND_LABEL = { uncertain: 'Aandacht nodig (lage modelscore)', disagree: 'Modellen geven verschillende woorden', later: 'Later opnieuw luisteren', gap: 'Mogelijk ontbrekende tekst — luister terug' };
const KIND_MARK = { uncertain: '?', disagree: '≠', later: '⟲' };

function wordHtml(w, si, wi) {
  const kinds = attKinds(w), open = kinds.length && !pointDone(w);
  const alts = Object.values(w.alts || {}).filter(Boolean);
  const mark = open ? kinds.map(k => KIND_MARK[k]).join('') : '';
  const title = [w.p != null ? `modelscore ${Math.round(w.p * 100)}%` : 'door jou bewerkt', alts.length ? 'andere modellen: ' + alts.join(' / ') : '', w.checked ? 'bevestigd' : ''].filter(Boolean).join(' · ');
  return `<w class="${cls(w)}${open ? ' att' : ''}${kinds.includes('disagree') ? ' dis' : ''}${w.checked ? ' chk' : ''}${w.edited ? ' ed' : ''}" data-s="${si}" data-w="${wi}" ${mark ? `data-m="${mark}"` : ''} title="${esc(title)}">${esc(w.word)}</w>`;
}
function gapHtml(g, gi) { return `<button class="gapmark ${g.dismissed ? 'dis' : ''}" data-g="${gi}" title="${esc(g.hint ? 'Ander model hoorde hier: ' + g.hint : 'Spraak gevonden zonder tekst')}">⚠ Mogelijk ontbrekende tekst ${fmtHMS(g.start)}–${fmtHMS(g.end)}${g.dismissed ? ' (afgewezen)' : ''}</button>`; }
function segHtml(s, si) {
  const words = s.words && s.words.length ? s.words.map((w, wi) => wordHtml(w, si, wi)).join(' ') : esc(s.text);
  const marks = [s.quote ? '★ citaat' : '', s.later ? '⟲ later luisteren' : '', (s.other_missing || []).length ? `niet herkend door ${s.other_missing.join(', ')}` : ''].filter(Boolean).join(' · ');
  return `<div class="seg ${s.reviewed ? 'reviewed' : ''} ${s.quote ? 'quote' : ''} ${s.later ? 'later' : ''}" data-s="${si}" id="seg${si}">
    <div class="meta"><button class="sp" style="color:${spColor(s.speaker)}" title="Spreker kiezen" aria-label="Spreker ${esc(spName(s.speaker))}, klik om te wijzigen">${esc(spName(s.speaker))}</button><button class="ts" title="Dit segment afspelen" aria-label="Afspelen vanaf ${fmtHMS(s.start)}">${fmtHMS(s.start)}</button>${s.reviewed ? '<span class="ok">✓ nagekeken</span>' : ''}${marks ? `<span class="mk">${marks}</span>` : ''}</div>
    <div class="txt" contenteditable="true" spellcheck="false" role="textbox" aria-multiline="true" aria-label="Tekst van segment ${fmtHMS(s.start)}">${words}</div></div>${s.note ? `<div class="notetxt" data-note="${si}">Opmerking: ${esc(s.note)}</div>` : ''}`;
}
function attentionPoints() {
  const pts = [];
  (S.tr.segments || []).forEach((s, si) => {
    (s.words || []).forEach((w, wi) => { const k = attKinds(w); if (k.length) pts.push({ id: `w:${si}:${wi}`, kind: k, si, wi, start: w.start, end: w.end, done: pointDone(w), text: w.word }); });
    if (s.later) pts.push({ id: `s:${si}`, kind: ['later'], si, wi: null, start: s.start, end: s.end, done: false, text: (s.text || '').slice(0, 60) });
  });
  (S.tr.gaps || []).forEach((g, gi) => pts.push({ id: `g:${gi}`, kind: ['gap'], si: null, wi: null, gi, start: g.start, end: g.end, done: !!g.dismissed, text: g.hint || '' }));
  pts.sort((a, b) => a.start - b.start || (a.si ?? -1) - (b.si ?? -1));
  return pts;
}
function filteredPoints() { const f = S.filters; return attentionPoints().filter(p => (f.done || !p.done) && p.kind.some(k => f[k])); }

/* ---------- renderen ---------- */
function renderEditor() {
  if (!S.tr) { $('#editor').innerHTML = '<div class="sub" style="padding:30px">Nog geen transcript. Verwerk de opname eerst (tabblad "Opname verwerken").</div>'; $('#side').innerHTML = ''; $('#right').innerHTML = ''; return; }
  $('#topActions').innerHTML = `<button class="btn" id="btnFind">Zoek &amp; vervang</button> <button class="btn" id="btnKeys">Sneltoetsen</button> <button class="btn" id="btnSnap">Versie bewaren</button> <button class="btn primary" id="btnExportTop">Exporteren</button>`;
  $('#btnFind').onclick = findReplace; $('#btnKeys').onclick = showKeys; $('#btnExportTop').onclick = async () => { if (await Saver.leaveGuard()) show('export'); };
  $('#btnSnap').onclick = async () => { const label = await promptBox('Naam voor deze versie (optioneel)', ''); if (label == null) return; commitActiveSegment(); await post(`/projects/${S.pid}/snapshot`, { label, transcript: S.tr }); Saver.save(); toast('Versie bewaard, inclusief nog niet opgeslagen invoer'); };
  const ed = $('#ed'); ed.classList.toggle('noside', !S.panels.side); ed.classList.toggle('noright', !S.panels.right);
  $('#editor').classList.toggle('heat', S.heat); $('#editor').classList.toggle('nopick', !$('#clickPlay').checked);
  const gapsAt = {}; const segs = S.tr.segments;
  (S.tr.gaps || []).forEach((g, gi) => { let si = segs.findIndex(s => s.start >= g.start); if (si < 0) si = segs.length; (gapsAt[si] = gapsAt[si] || []).push(gi); });
  const pts = filteredPoints(), open = attentionPoints().filter(p => !p.done).length;
  $('#editor').innerHTML = `<div class="toolbar" role="toolbar" aria-label="Bewerken">
      <div class="grp"><button class="btn small" id="tgSide" aria-pressed="${S.panels.side}" title="Overzicht tonen/verbergen">◧ Overzicht</button></div>
      <div class="grp"><button class="btn small" id="btnUndo" title="Ongedaan maken (Ctrl+Z)" aria-label="Ongedaan maken">↶</button><button class="btn small" id="btnRedo" title="Opnieuw (Ctrl+Y)" aria-label="Opnieuw">↷</button><button class="btn small" id="btnDict" title="Namen en vaktermen voor het spraakmodel">Woordenlijst</button></div>
      <div class="grp"><button class="btn small" id="tbSpk" title="Spreker wisselen (Alt+S)">Spreker</button><button class="btn small" id="tbOk" title="Segment nagekeken (Ctrl+Enter)">✓ Nagekeken</button><button class="btn small" id="tbQuote" title="Interessant citaat (Alt+C)">★ Citaat</button><button class="btn small" id="tbLater" title="Later opnieuw luisteren (Alt+L)">⟲ Later</button><button class="btn small" id="tbNote">Opmerking</button></div>
      <div class="grp"><button class="btn small" id="tbTs" title="Tijdcode invoegen">[tijd]</button><button class="btn small" id="tbUnv" title="Onverstaanbaar (Ctrl+U)">[onverstaanbaar]</button><button class="btn small" id="tbPause">(pauze)</button><button class="btn small" id="tbLaugh">(lacht)</button><button class="btn small" id="tbBroken" title="Afgebroken zin">afgebroken</button><button class="btn small" id="tbOverlap" title="Overlap tussen sprekers">overlap</button></div>
      <div class="grp"><button class="btn small" id="tbSplit" title="Splitsen (Enter)">Splitsen</button><button class="btn small" id="tbMerge" title="Samenvoegen (Backspace aan het begin)">Samenvoegen</button></div>
      <div class="grp" style="margin-left:auto"><button class="btn small" id="tgRight" aria-pressed="${S.panels.right}" title="Aandachtspunt tonen/verbergen">Aandachtspunt ◨</button></div></div>
    <div class="attnav" role="navigation" aria-label="Aandachtspunten"><button class="btn small" id="attPrev" title="Vorig aandachtspunt (Alt+↑ of K)">▲ Vorig aandachtspunt</button><button class="btn small" id="attNext" title="Volgend aandachtspunt (Alt+↓ of J)">▼ Volgend aandachtspunt</button><span class="cnt">${pts.length} in dit filter · ${open} open in totaal</span><span class="cnt" style="margin-left:auto">Aandachtspunten helpen prioriteren, maar vinden niet alle fouten. Een volledige luistercontrole blijft nodig.</span></div>
    <div id="segs" data-pid="${esc(S.pid)}">${segs.map((s, si) => (gapsAt[si] || []).map(gi => gapHtml(S.tr.gaps[gi], gi)).join('') + segHtml(s, si)).join('')}${(gapsAt[segs.length] || []).map(gi => gapHtml(S.tr.gaps[gi], gi)).join('')}</div>`;
  bindEditor();
  renderSide(); renderRight();
  $('#tDur').textContent = '/ ' + fmtT(S.meta.audio.duration || 0);
  drawWave();
}
function bindEditor() {
  const ed = $('#segs');
  ed.onclick = e => {
    const w = e.target.closest('w');
    if (w) { selectWord(+w.dataset.s, +w.dataset.w); if ($('#clickPlay').checked) playWord(+w.dataset.s, +w.dataset.w); return; }
    const sp = e.target.closest('.sp'); if (sp) { e.preventDefault(); speakerMenu(+sp.closest('.seg').dataset.s, sp); return; }
    const ts = e.target.closest('.ts'); if (ts) { const si = +ts.closest('.seg').dataset.s; const s = S.tr.segments[si]; S.curSeg = si; playRange(s.start, s.end); return; }
    const g = e.target.closest('.gapmark'); if (g) { gotoPoint(`g:${g.dataset.g}`); return; }
    const n = e.target.closest('.notetxt'); if (n) { S.curSeg = +n.dataset.note; editNote(); }
  };
  // let op: onfocusin/onfocusout bestaan NIET als eigenschap in Chromium (de oorspronkelijke code gebruikte die en
  // legde wijzigingen daardoor nooit bij het verlaten van het tekstvak vast); daarom addEventListener.
  ed.addEventListener('focusin', e => { const seg = e.target.closest('.seg'); if (seg) { S.curSeg = +seg.dataset.s; $$('.seg.active').forEach(x => x.classList.remove('active')); seg.classList.add('active'); renderRight(); } });
  ed.addEventListener('focusout', e => { const txt = e.target.closest('.txt'); if (ownTxt(txt)) commitSegment(+txt.closest('.seg').dataset.s, true); });
  ed.oninput = e => { const txt = e.target.closest('.txt'); if (txt) { Saver.markDirty(); if ($('#autoPause').checked) typingPause(); } };
  ed.onkeydown = e => {
    const txt = e.target.closest('.txt'); if (!txt) return;
    const si = +txt.closest('.seg').dataset.s;
    if (e.key === 'Enter' && !e.ctrlKey && !e.shiftKey && !e.altKey) { e.preventDefault(); splitAtCaret(si); }
    if (e.key === 'Backspace' && caretAtStart(txt) && si > 0 && !window.getSelection().toString()) { e.preventDefault(); mergeWithPrevious(si); }
  };
  $('#tgSide').onclick = () => { S.panels.side = !S.panels.side; pref.set('panels', S.panels); renderEditor(); };
  $('#btnUndo').onclick = () => History.doUndo(); $('#btnRedo').onclick = () => History.doRedo(); $('#btnDict').onclick = editDictionary;
  $('#tgRight').onclick = () => { S.panels.right = !S.panels.right; pref.set('panels', S.panels); renderEditor(); };
  $('#attPrev').onclick = () => stepPoint(-1); $('#attNext').onclick = () => stepPoint(1);
  $('#tbSpk').onclick = () => S.curSeg != null && cycleSpeaker(S.curSeg);
  $('#tbTs').onclick = () => insertText(`[${fmtHMS(audio.currentTime)}] `);
  $('#tbQuote').onclick = () => toggleFlag('quote');
  $('#tbLater').onclick = () => toggleFlag('later');
  $('#tbUnv').onclick = () => insertText(convText('unintelligible'));
  $('#tbPause').onclick = () => insertText(convText('pauses'));
  $('#tbLaugh').onclick = () => insertText(convText('laughter'));
  $('#tbBroken').onclick = () => insertText(convText('broken'));
  $('#tbOverlap').onclick = () => insertText(convText('overlap'));
  $('#tbNote').onclick = editNote;
  $('#tbOk').onclick = () => toggleFlag('reviewed');
  $('#tbSplit').onclick = () => S.curSeg != null && splitAtCaret(S.curSeg);
  $('#tbMerge').onclick = () => S.curSeg != null && S.curSeg > 0 && mergeWithPrevious(S.curSeg);
}
/* notatie volgens de transcriptieafspraken van het onderzoek */
function convText(key) {
  const c = { ...(S.info?.conventions_default || {}), ...((S.meta?.study || {}).conventions || {}) }[key];
  const t = fmtHMS(audio.currentTime);
  return { unintelligible: { timecode: `[onverstaanbaar ${t}] `, unv: '(unv.) ', guess: '(woord?) ' }, pauses: { dots: '(...) ', seconds: '(3) ', word: '(pauze) ' }, laughter: { parens: '(lacht) ', brackets: '[lacht] ' },
    broken: { dash: '– ', ellipsis: '… ', slash: '/ ' }, overlap: { slashes: '//', brackets: '[overlap] ' } }[key]?.[c] || { unintelligible: `[onverstaanbaar ${t}] `, pauses: '(...) ', laughter: '(lacht) ', broken: '… ', overlap: '//' }[key];
}
function renderSide() {
  const segs = S.tr.segments, words = segs.flatMap(s => s.words || []);
  const all = attentionPoints(), openPts = all.filter(p => !p.done);
  const rev = segs.filter(s => s.reviewed).length, quotes = segs.map((s, i) => [s, i]).filter(([s]) => s.quote), later = segs.map((s, i) => [s, i]).filter(([s]) => s.later);
  const spk = Object.entries(S.tr.speakers || {});
  const counts = {}; segs.forEach(s => counts[s.speaker] = (counts[s.speaker] || 0) + (s.end - s.start));
  const tot = Object.values(counts).reduce((a, b) => a + b, 0) || 1;
  const pct = (a, b) => b ? Math.round(a / b * 100) : 0;
  const f = S.filters;
  const cnt = k => all.filter(p => p.kind.includes(k) && !p.done).length;
  $('#side').innerHTML = `<h4 class="lbl">Sprekers</h4>${spk.map(([id, sp]) => `<div class="spk"><span class="dot" style="background:${spColor(id)}"></span><input value="${esc(sp.name)}" data-sp="${id}" aria-label="Naam van spreker ${esc(id)}"><small>${Math.round((counts[id] || 0) / tot * 100)}%</small></div>`).join('')}<button class="btn small" id="addSpk">+ spreker toevoegen</button>
    <h4 class="lbl" style="margin-top:16px">Controlevoortgang</h4>
    <div class="stat"><span>Segmenten nagekeken</span><b>${rev} / ${segs.length}</b></div><div class="pbar"><i style="width:${pct(rev, segs.length)}%"></i></div>
    <div class="stat"><span>Aandachtspunten afgehandeld</span><b>${all.length - openPts.length} / ${all.length}</b></div><div class="pbar"><i style="width:${pct(all.length - openPts.length, all.length)}%"></i></div>
    <div class="stat"><span>Status</span><b>${esc(S.meta.status_label || '')}</b></div>
    ${S.meta.review_status === 'checked' ? `<button class="btn small" id="uncheck">Markering 'Gecontroleerd' intrekken</button>` : `<button class="btn small primary" id="markChecked">Als gecontroleerd markeren</button><div class="sub" style="margin:4px 0 0;font-size:11px">Alleen jij bepaalt wanneer het transcript gecontroleerd is; Sift doet dat nooit zelf.</div>`}
    <h4 class="lbl" style="margin-top:16px">Aandachtspunten tonen</h4>
    <label class="stat"><span>? Aandacht nodig</span><span><b>${cnt('uncertain')}</b> <input type="checkbox" data-f="uncertain" ${f.uncertain ? 'checked' : ''}></span></label>
    <label class="stat"><span>≠ Modellen verschillen</span><span><b>${cnt('disagree')}</b> <input type="checkbox" data-f="disagree" ${f.disagree ? 'checked' : ''}></span></label>
    <label class="stat"><span>⟲ Later opnieuw luisteren</span><span><b>${cnt('later')}</b> <input type="checkbox" data-f="later" ${f.later ? 'checked' : ''}></span></label>
    <label class="stat"><span>⚠ Mogelijk ontbrekende tekst</span><span><b>${cnt('gap')}</b> <input type="checkbox" data-f="gap" ${f.gap ? 'checked' : ''}></span></label>
    <label class="stat"><span>ook afgehandelde</span><input type="checkbox" data-f="done" ${f.done ? 'checked' : ''}></label>
    <h4 class="lbl" style="margin-top:16px">★ Interessante citaten (${quotes.length})</h4><div class="ptlist">${quotes.map(([s, i]) => `<button data-go="${i}">${fmtHMS(s.start)} ${esc((s.text || '').slice(0, 50))}</button>`).join('') || '<div class="sub">Nog geen. Knop ★ Citaat of Alt+C.</div>'}</div>
    <h4 class="lbl" style="margin-top:16px">⟲ Later luisteren (${later.length})</h4><div class="ptlist">${later.map(([s, i]) => `<button data-go="${i}">${fmtHMS(s.start)} ${esc((s.text || '').slice(0, 50))}</button>`).join('') || '<div class="sub">Nog geen. Knop ⟲ Later of Alt+L.</div>'}</div>
    <h4 class="lbl" style="margin-top:16px">Weergave</h4>
    <label class="stat"><span>Kleurmarkering van modelscores</span><input type="checkbox" id="heatChk" ${S.heat ? 'checked' : ''}></label>
    <div class="stat"><label for="thr">drempel 'aandacht nodig'</label><span><input type="range" id="thr" min="0.3" max="0.9" step="0.05" value="${S.threshold}" style="width:80px"><b id="thrV">${S.threshold}</b></span></div>
    <div style="font-size:11px;color:var(--muted2);margin-top:6px">Markeringen ? en ≠ blijven ook zonder kleur zichtbaar. Een modelscore is een hint, geen gemeten kans dat het woord klopt. Gestippeld = door jou bewerkt.</div>
    <details style="margin-top:10px"><summary>Modellen</summary>${(S.tr.models || []).map(m => `<div class="stat"><span>${esc(m)}${m === S.tr.base_model ? ' (basis)' : ''}</span><b>${S.meta.summary?.[m]?.mean_p ?? ''}</b></div>`).join('')}<div class="sub" style="font-size:11px">Gemiddelde ruwe modelscore per model.</div></details>`;
  $$('#side input[data-sp]').forEach(inp => inp.onchange = () => { History.edit(0, 0, () => { S.tr.speakers[inp.dataset.sp].name = inp.value; }, 'sprekernaam'); renderEditor(); });
  $('#addSpk').onclick = () => { History.edit(0, 0, () => { const n = Object.keys(S.tr.speakers).length + 1; S.tr.speakers['S' + n] = { name: 'Spreker ' + n }; }, 'spreker toevoegen'); renderSide(); };
  $$('#side input[data-f]').forEach(c => c.onchange = () => { S.filters[c.dataset.f] = c.checked; pref.set('filters', S.filters); renderEditor(); });
  $$('#side [data-go]').forEach(b => b.onclick = () => { const si = +b.dataset.go; S.curSeg = si; $(`#seg${si}`)?.scrollIntoView({ block: 'center', behavior: 'smooth' }); const s = S.tr.segments[si]; playRange(s.start, s.end); });
  $('#heatChk').onchange = e => { S.heat = e.target.checked; pref.set('heat', S.heat); $('#editor').classList.toggle('heat', S.heat); };
  $('#thr').oninput = e => { S.threshold = +e.target.value; $('#thrV').textContent = S.threshold; };
  $('#thr').onchange = () => { S.meta.settings.uncertain_threshold = S.threshold; put(`/projects/${S.pid}/settings`, { uncertain_threshold: S.threshold }); renderEditor(); };
  if ($('#markChecked')) $('#markChecked').onclick = async () => { const open = attentionPoints().filter(p => !p.done).length; if (!(await confirmBox(`Dit transcript als gecontroleerd markeren?${open ? ` Er staan nog ${open} aandachtspunten open.` : ''} Je kunt dit altijd intrekken.`, 'Ja, gecontroleerd'))) return; await Saver.flush(); await put(`/projects/${S.pid}/review_status`, { status: 'checked' }); await refreshMeta(); renderSide(); toast('Gemarkeerd als gecontroleerd'); };
  if ($('#uncheck')) $('#uncheck').onclick = async () => { await put(`/projects/${S.pid}/review_status`, { status: 'in_progress' }); await refreshMeta(); renderSide(); };
}
function renderRight() {
  let card;
  const pt = S.curPoint ? attentionPoints().find(p => p.id === S.curPoint) : null;
  if (pt && pt.kind.includes('gap')) {
    const g = S.tr.gaps[pt.gi];
    card = `<div class="card"><h5>⚠ ${esc(KIND_LABEL.gap)}</h5><div>${fmtHMS(g.start)} – ${fmtHMS(g.end)} (${(g.end - g.start).toFixed(1)} s)</div>
      <div class="sub" style="margin:6px 0">${g.kind === 'coverage' || g.kind === 'both' ? `Een ander model (${esc((g.models || []).join(', '))}) hoorde hier: <i>“${esc(g.hint)}”</i>. Het transcript bevat hier geen woorden. Luister terug en typ zelf wat je hoort; er wordt niets automatisch ingevoegd.` : 'De spraakdetectie vond hier spraak, maar het transcript bevat geen woorden. Het kan ook lachen, hoesten of achtergrondgeluid zijn.'}</div>
      <div class="actions"><button class="btn small" id="gapListen">▶ Luister terug</button><button class="btn small" id="gapInsert">Tekst toevoegen</button><button class="btn small" id="gapDismiss">${g.dismissed ? 'Toch als aandachtspunt' : 'Geen ontbrekende tekst'}</button></div></div>`;
  } else if (S.curWord) {
    const [si, wi] = S.curWord, w = S.tr.segments[si].words[wi], kinds = attKinds(w);
    const lanes = [[S.tr.base_model || 'model', w.base ?? w.word, w.p]].concat(Object.entries(w.alts || {}).map(([m, a]) => [m, a, null]));
    card = `<div class="card"><h5>${kinds.length ? kinds.map(k => esc(KIND_LABEL[k])).join(' · ') : 'Geselecteerd woord'} · ${fmtT(w.start, true)}</h5>
      ${lanes.map(([m, txt, p]) => `<div class="lane"><span class="m">${esc(m)}</span><button class="w ${normW(txt) === normW(w.word) ? 'pick' : ''}" data-alt="${esc(txt)}">${esc(txt || '—')}</button></div>`).join('')}
      <div style="margin-top:6px">${[...new Set(lanes.map(l => l[1]).filter(Boolean))].map(t => `<button class="chip ${normW(t) === normW(w.word) ? 'on' : ''}" data-alt="${esc(t)}">${esc(t)}</button>`).join('')}<button class="chip" id="altCustom">eigen tekst…</button></div>
      <div class="row" style="margin-top:6px"><span>Status</span><b>${w.checked ? 'door jou bevestigd' : w.edited ? 'door jou bewerkt' : 'herkend door het model'}</b></div>
      ${kinds.length ? `<div class="actions"><button class="btn small primary" id="ptOk" title="Alt+K">✓ Klopt zo</button><button class="btn small" id="ptEdit">Aangepast…</button><button class="btn small" id="ptLater" title="Alt+L">⟲ Later opnieuw luisteren</button></div>` : ''}
      <details style="margin-top:8px"><summary>Details</summary><div class="row"><span>Ruwe modelscore</span><b>${w.p == null ? '–' : w.p.toFixed(2)}</b></div><div class="row"><span>Modellen eens</span><b>${w.agree ?? 1} van ${w.n_models ?? 1}</b></div><div class="sub" style="font-size:11px">De score is wat het model zelf aan het woord toekent (token-kans). Het is geen gemeten kans dat het woord correct is en verandert niet als jij het bevestigt.</div></details></div>`;
  } else {
    card = '<div class="card"><h5>Aandachtspunt</h5><div class="sub">Gebruik ▲ Vorig / ▼ Volgend aandachtspunt (Alt+↑/↓) of klik op een woord. Per punt kies je: Klopt zo, Aangepast of Later opnieuw luisteren.</div></div>';
  }
  const seg = S.curSeg != null ? S.tr.segments[S.curSeg] : null;
  $('#right').innerHTML = card + `<div class="card"><h5>Opmerking bij segment</h5><div style="color:var(--muted);font-style:italic">${seg && seg.note ? esc(seg.note) : 'Geen.'}</div><button class="btn small" id="noteBtn" style="margin-top:6px">${seg && seg.note ? 'Wijzigen' : 'Opmerking toevoegen'}</button></div>`;
  $$('#right [data-alt]').forEach(el => el.onclick = () => { setWord(S.curWord[0], S.curWord[1], el.dataset.alt); toast('Aangepast en bevestigd'); });
  if ($('#altCustom')) $('#altCustom').onclick = async () => { const t = await promptBox('Vervang door', S.tr.segments[S.curWord[0]].words[S.curWord[1]].word); if (t != null && t.trim()) setWord(S.curWord[0], S.curWord[1], t.trim()); };
  if ($('#ptOk')) $('#ptOk').onclick = pointOk;
  if ($('#ptEdit')) $('#ptEdit').onclick = () => $('#altCustom').click();
  if ($('#ptLater')) $('#ptLater').onclick = pointLater;
  if ($('#gapListen')) $('#gapListen').onclick = () => { const g = S.tr.gaps[pt.gi]; playRange(g.start - 1, g.end + 1); };
  if ($('#gapDismiss')) $('#gapDismiss').onclick = () => { History.edit(0, 0, () => { S.tr.gaps[pt.gi].dismissed = !S.tr.gaps[pt.gi].dismissed; }, 'ontbrekende tekst afwijzen'); renderEditor(); };
  if ($('#gapInsert')) $('#gapInsert').onclick = () => insertGapSegment(pt.gi);
  $('#noteBtn').onclick = editNote;
}
function selectWord(si, wi, scroll) { S.curWord = [si, wi]; S.curSeg = si; S.curPoint = `w:${si}:${wi}`; $$('w.cur').forEach(x => x.classList.remove('cur')); const el = $(`w[data-s="${si}"][data-w="${wi}"]`); if (el) { el.classList.add('cur'); if (scroll) el.scrollIntoView({ block: 'center', behavior: 'smooth' }); } renderRight(); }
function setWord(si, wi, text) { History.edit(si, 1, () => { const w = S.tr.segments[si].words[wi]; if (!w) return; w.word = text; w.edited = true; w.checked = true; w.later = false; const s = S.tr.segments[si]; s.text = s.words.map(x => x.word).join(' '); }, 'woord aangepast'); rerenderSeg(si); selectWord(si, wi); }
function rerenderSeg(si) { const s = S.tr.segments[si]; const old = $(`#seg${si}`); if (!old) return renderEditor(); const tmp = document.createElement('div'); tmp.innerHTML = segHtml(s, si); const note = old.nextElementSibling && old.nextElementSibling.classList.contains('notetxt') ? old.nextElementSibling : null; if (note) note.remove(); old.replaceWith(...tmp.childNodes); }

/* ---------- aandachtspunten: navigatie en acties ---------- */
function gotoPoint(id) {
  const pt = attentionPoints().find(p => p.id === id); if (!pt) return;
  S.curPoint = id;
  if (pt.kind.includes('gap')) { S.curWord = null; $$('w.cur').forEach(x => x.classList.remove('cur')); const el = $(`.gapmark[data-g="${pt.gi}"]`); if (el) el.scrollIntoView({ block: 'center', behavior: 'smooth' }); renderRight(); const g = S.tr.gaps[pt.gi]; playRange(g.start - 1, g.end + 1); return; }
  if (pt.wi == null) { S.curSeg = pt.si; S.curWord = null; $(`#seg${pt.si}`)?.scrollIntoView({ block: 'center', behavior: 'smooth' }); renderRight(); const s = S.tr.segments[pt.si]; playRange(s.start, s.end); return; }
  selectWord(pt.si, pt.wi, true); playWord(pt.si, pt.wi);
}
function stepPoint(dir) {
  commitActiveSegment();
  const pts = filteredPoints(); if (!pts.length) return toast('Geen aandachtspunten in dit filter');
  let i = pts.findIndex(p => p.id === S.curPoint);
  if (i < 0) { const t = S.curWord ? S.tr.segments[S.curWord[0]].words[S.curWord[1]].start : audio.currentTime || -1; i = dir > 0 ? pts.findIndex(p => p.start > t) : pts.length - 1 - [...pts].reverse().findIndex(p => p.start < t); if (i < 0 || i >= pts.length) i = dir > 0 ? 0 : pts.length - 1; }
  else { i += dir; if (i < 0 || i >= pts.length) { toast(dir > 0 ? 'Laatste aandachtspunt bereikt' : 'Eerste aandachtspunt bereikt'); i = Math.max(0, Math.min(pts.length - 1, i)); } }
  gotoPoint(pts[i].id);
}
function pointOk() { if (!S.curWord) return; const [si, wi] = S.curWord; History.edit(si, 1, () => { const w = S.tr.segments[si].words[wi]; w.checked = true; w.later = false; }, 'klopt zo'); rerenderSeg(si); renderSide(); const nxt = filteredPoints().find(p => p.start > S.tr.segments[si].words[wi].start); if (nxt) gotoPoint(nxt.id); else { selectWord(si, wi); toast('Alle aandachtspunten in dit filter zijn afgehandeld'); } }
function pointLater() { if (!S.curWord) return; const [si, wi] = S.curWord; History.edit(si, 1, () => { const w = S.tr.segments[si].words[wi]; w.later = !w.later; if (w.later) w.checked = false; S.tr.segments[si].later = S.tr.segments[si].words.some(x => x.later) || S.tr.segments[si].later; }, 'later luisteren'); rerenderSeg(si); renderSide(); selectWord(si, wi); }
function insertGapSegment(gi) {
  const g = S.tr.gaps[gi]; let si = S.tr.segments.findIndex(s => s.start >= g.start); if (si < 0) si = S.tr.segments.length;
  const prev = S.tr.segments[si - 1];
  History.edit(si, 0, () => { S.tr.segments.splice(si, 0, { id: Date.now(), start: g.start, end: g.end, text: '', words: [], speaker: prev ? prev.speaker : Object.keys(S.tr.speakers)[0], reviewed: false, quote: false, later: false, note: 'toegevoegd bij mogelijk ontbrekende tekst' }); S.tr.gaps[gi].dismissed = true; }, 'segment toegevoegd');
  renderEditor(); const t = $(`#seg${si} .txt`); if (t) { t.focus(); } playRange(g.start - 0.5, g.end + 0.5);
}

/* ---- tekst → woorden terugvertalen (LCS-diff op tokens) ---- */
/* Een tekstvak hoort alleen bij het huidige interview als het nog in het document staat én in de container met dezelfde
   project-id. Zo kan een los tekstvak van een vorig interview nooit in het nieuwe transcript terechtkomen. */
function ownTxt(el) { return !!(el && el.isConnected && S.tr && el.closest('#segs') && el.closest('#segs').dataset.pid === S.pid); }
function commitActiveSegment() { const a = document.activeElement; const txt = a && a.closest ? a.closest('.txt') : null; if (ownTxt(txt)) commitSegment(+txt.closest('.seg').dataset.s, false); }
function commitSegment(si, render = true) {
  if (!S.tr) return;
  const s = S.tr.segments[si]; const el = $(`#seg${si} .txt`); if (!el || !s || !ownTxt(el)) return;
  const tokens = el.textContent.replace(/\s+/g, ' ').trim().split(' ').filter(Boolean);
  const oldWords = s.words || [];
  if (tokens.join(' ') === oldWords.map(w => w.word).join(' ')) return;
  History.edit(si, 1, () => {
    const a = oldWords.map(w => normW(w.word)), b = tokens.map(normW);
    const n = a.length, m = b.length, L = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
    for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) L[i][j] = a[i] === b[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
    const out = []; let i = 0, j = 0, lastEnd = s.start;
    const pending = [];
    const flush = (nextStart) => { if (!pending.length) return; const span = Math.max(0.05, (nextStart - lastEnd)) / pending.length; pending.forEach((t, k) => out.push({ start: lastEnd + k * span, end: lastEnd + (k + 1) * span, word: t, p: null, edited: true, checked: true, alts: {}, agree: 1, n_models: 1 })); pending.length = 0; };
    while (i < n && j < m) {
      if (a[i] === b[j]) { flush(oldWords[i].start); const w = { ...oldWords[i], word: tokens[j] }; if (tokens[j] !== oldWords[i].word) { w.edited = true; w.checked = false; } out.push(w); lastEnd = w.end; i++; j++; }
      else if (L[i + 1][j] >= L[i][j + 1]) i++; else { pending.push(tokens[j]); j++; }
    }
    while (j < m) pending.push(tokens[j++]);
    flush(s.end);
    s.words = out; s.text = tokens.join(' '); s.later = out.some(w => w.later) || (s.later && !oldWords.some(w => w.later));
  }, 'tekst gewijzigd');
  if (render) { rerenderSeg(si); renderSide(); }
}
function caretAtStart(el) { const sel = window.getSelection(); if (!sel.rangeCount) return false; const r = sel.getRangeAt(0).cloneRange(); r.selectNodeContents(el); r.setEnd(sel.anchorNode, sel.anchorOffset); return r.toString().trim().length === 0; }
function caretWordIndex(el) { const sel = window.getSelection(); if (!sel.rangeCount) return null; const r = sel.getRangeAt(0).cloneRange(); r.selectNodeContents(el); r.setEnd(sel.anchorNode, sel.anchorOffset); return r.toString().replace(/\s+/g, ' ').trim().split(' ').filter(Boolean).length; }
function splitAtCaret(si) {
  const el = $(`#seg${si} .txt`); const k = caretWordIndex(el); commitSegment(si, false); const s = S.tr.segments[si];
  if (k == null || k <= 0 || k >= s.words.length) return;
  History.edit(si, 1, () => {
    const w2 = s.words.slice(k), w1 = s.words.slice(0, k);
    const s2 = { ...s, id: Date.now(), start: w2[0].start, end: s.end, words: w2, text: w2.map(w => w.word).join(' '), reviewed: false, note: '', quote: s.quote, later: w2.some(w => w.later) };
    Object.assign(s, { end: w1[w1.length - 1].end, words: w1, text: w1.map(w => w.word).join(' '), later: w1.some(w => w.later) });
    S.tr.segments.splice(si + 1, 0, s2);
  }, 'splitsen');
  renderEditor(); const t = $(`#seg${si + 1} .txt`); if (t) t.focus();
}
function mergeWithPrevious(si) {
  commitSegment(si, false);
  History.edit(si - 1, 2, () => { const a = S.tr.segments[si - 1], b = S.tr.segments[si]; a.words = [...(a.words || []), ...(b.words || [])]; a.text = a.words.map(w => w.word).join(' '); a.end = b.end; a.note = [a.note, b.note].filter(Boolean).join(' | '); a.quote = a.quote || b.quote; a.later = a.later || b.later; S.tr.segments.splice(si, 1); }, 'samenvoegen');
  renderEditor(); const t = $(`#seg${si - 1} .txt`); if (t) t.focus();
}
function insertText(text) { if (S.curSeg == null) return toast('Klik eerst in een segment'); const el = $(`#seg${S.curSeg} .txt`); el.focus(); document.execCommand('insertText', false, text); Saver.markDirty(); }
function toggleFlag(flag) { if (S.curSeg == null) return toast('Klik eerst in een segment'); commitActiveSegment(); const si = S.curSeg; History.edit(si, 1, () => { const s = S.tr.segments[si]; s[flag] = !s[flag]; if (flag === 'later' && !s.later) (s.words || []).forEach(w => w.later = false); }, { quote: 'citaat', later: 'later luisteren', reviewed: 'nagekeken' }[flag]); rerenderSeg(si); renderSide(); }
async function editNote() { if (S.curSeg == null) return toast('Klik eerst in een segment'); const si = S.curSeg; const n = await promptBox('Opmerking bij dit segment', S.tr.segments[si].note || ''); if (n == null) return; History.edit(si, 1, () => { S.tr.segments[si].note = n; }, 'opmerking'); rerenderSeg(si); renderRight(); }
function cycleSpeaker(si) { History.edit(si, 1, () => { const ids = Object.keys(S.tr.speakers); const s = S.tr.segments[si]; s.speaker = ids[(ids.indexOf(s.speaker) + 1) % ids.length]; }, 'spreker'); rerenderSeg(si); renderSide(); }
function speakerMenu(si, anchor) {
  $$('.dropdown').forEach(d => d.remove()); const d = document.createElement('div'); d.className = 'dropdown'; d.setAttribute('role', 'menu');
  const r = anchor.getBoundingClientRect(); d.style.left = r.left + 'px'; d.style.top = (r.bottom + 4) + 'px';
  d.innerHTML = Object.entries(S.tr.speakers).map(([id, sp]) => `<button role="menuitem" data-id="${id}" style="color:${spColor(id)}">${esc(sp.name)}</button>`).join('') + `<button role="menuitem" data-id="__new">+ nieuwe spreker</button><button role="menuitem" data-id="__rest" style="color:var(--muted)">deze én alle volgende van deze spreker…</button>`;
  document.body.appendChild(d); d.querySelector('button').focus();
  d.onkeydown = e => { if (e.key === 'Escape') { d.remove(); anchor.focus(); } };
  d.onclick = async e => { const id = e.target.dataset.id; if (!id) return; d.remove();
    if (id === '__new') History.edit(si, 1, () => { const n = Object.keys(S.tr.speakers).length + 1; S.tr.speakers['S' + n] = { name: 'Spreker ' + n }; S.tr.segments[si].speaker = 'S' + n; }, 'nieuwe spreker');
    else if (id === '__rest') { const names = Object.entries(S.tr.speakers); const target = await promptBox('Naar welke spreker? (nummer: ' + names.map(([, sp], i) => `${i + 1}=${sp.name}`).join(', ') + ')'); const tid = names[(+target) - 1]?.[0]; if (!tid) return; History.edit(si, S.tr.segments.length - si, () => { const from = S.tr.segments[si].speaker; for (let k = si; k < S.tr.segments.length; k++) if (S.tr.segments[k].speaker === from) S.tr.segments[k].speaker = tid; }, 'sprekers vanaf hier'); }
    else History.edit(si, 1, () => { S.tr.segments[si].speaker = id; }, 'spreker');
    renderEditor(); };
  setTimeout(() => document.addEventListener('click', () => d.remove(), { once: true }), 0);
}

/* ---- zoeken, woordenlijst, sneltoetsen ---- */
function findReplace() {
  const m = modal(`<h3>Zoek &amp; vervang</h3><div class="form"><label for="fFind">Zoek</label><input type="text" id="fFind"><label for="fRepl">Vervang door</label><input type="text" id="fRepl"><label class="inline" for="fCase"><input type="checkbox" id="fCase"> hoofdlettergevoelig</label><label class="inline" for="fSpk"><input type="checkbox" id="fSpk"> ook in sprekernamen</label><div class="actions"><button class="btn primary" id="fGo">Vervang alles</button><button class="btn" id="fCount">Tel</button></div><div id="fRes" class="sub" style="margin-top:8px" aria-live="polite"></div><div class="note">Dit wijzigt het transcript zelf (ongedaan te maken met Ctrl+Z). Voor namen vervangen bij het exporteren, zonder het transcript te wijzigen, gebruik je 'Namen en herkenbare gegevens vervangen' in Exporteren.</div></div>`, { label: 'Zoek en vervang' });
  const run = (doit) => { const f = $('#fFind').value; if (!f) return; const cs = $('#fCase').checked; const re = new RegExp(f.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), cs ? 'g' : 'gi'); let n = 0;
    const work = () => { S.tr.segments.forEach(s => (s.words || []).forEach(w => { if (re.test(w.word)) { n++; if (doit) { w.word = w.word.replace(re, $('#fRepl').value); w.edited = true; } } re.lastIndex = 0; })); if (doit) { S.tr.segments.forEach(s => s.text = (s.words || []).map(w => w.word).join(' ')); if ($('#fSpk').checked) Object.values(S.tr.speakers).forEach(sp => sp.name = sp.name.replace(re, $('#fRepl').value)); } };
    if (doit) { commitActiveSegment(); History.edit(0, S.tr.segments.length, work, 'zoek en vervang'); renderEditor(); } else work();
    $('#fRes').textContent = `${n} ${doit ? 'vervangen' : 'gevonden'}`; };
  $('#fGo').onclick = () => run(true); $('#fCount').onclick = () => run(false); $('#fFind').focus();
}
function editDictionary() {
  const m = modal(`<h3>Woordenlijst van dit interview</h3><div class="sub">Namen, afkortingen en vaktermen. Worden bij een volgende verwerking aan het spraakmodel meegegeven.${S.meta.study ? ` De woordenlijst van onderzoek "${esc(S.meta.study.name)}" (${esc(S.meta.study.terms || 'leeg')}) komt daar automatisch bij.` : ''}</div><div class="form"><textarea id="dictTxt" style="min-height:120px" aria-label="Woordenlijst">${esc(S.meta.settings.initial_prompt || '')}</textarea><div class="actions"><button class="btn primary" id="dictSave">Opslaan</button></div><div class="note">Opslaan start geen verwerking en verandert geen bestaande correcties.</div></div>`, { label: 'Woordenlijst' });
  $('#dictSave').onclick = async () => { S.meta.settings.initial_prompt = $('#dictTxt').value; await put(`/projects/${S.pid}/settings`, { initial_prompt: $('#dictTxt').value }); m.remove(); toast('Woordenlijst opgeslagen; geldt bij de volgende verwerking'); };
}
const KEYS = [['Ctrl+Spatie', 'Afspelen / pauze (springt bij hervatten iets terug)'], ['Ctrl+← / Ctrl+→', '3 seconden terug / vooruit'], ['Alt+↓ / Alt+↑ (of J / K buiten de tekst)', 'Volgend / vorig aandachtspunt'], ['Alt+K', 'Aandachtspunt: klopt zo'], ['Alt+L', 'Later opnieuw luisteren'], ['Alt+C', 'Interessant citaat'], ['Alt+S', 'Spreker van dit segment wisselen'], ['Ctrl+Enter', 'Segment nagekeken en door naar het volgende'], ['Ctrl+S', 'Opslaan'], ['Ctrl+Z / Ctrl+Y', 'Ongedaan maken / opnieuw'], ['Ctrl+U', '[onverstaanbaar hh:mm:ss] invoegen'], ['Ctrl+F', 'Zoek en vervang'], ['Enter / Backspace aan het begin', 'Segment splitsen / samenvoegen'], ['Tab / Shift+Tab', 'Gewone focusnavigatie (knoppen en velden)'], ['Esc', 'Afspelen stoppen']];
function showKeys() { modal(`<h3>Sneltoetsen</h3>${KEYS.map(([k, d]) => `<div class="row"><span>${esc(d)}</span><span class="kbd">${esc(k)}</span></div>`).join('')}<div class="row"><span>Klik op woord</span><span>fragment afspelen (uit te zetten bij Luisteropties)</span></div><div class="row"><span>Klik op tijdcode</span><span>segment afspelen</span></div><div class="row"><span>Slepen in golfvorm</span><span>selectie herhalen</span></div>`, { label: 'Sneltoetsen' }); }

/* ======================= audio ======================= */
let audioCtx, gainNode;
function ensureAudioGraph() { if (audioCtx) return; try { audioCtx = new (window.AudioContext || window.webkitAudioContext)(); const src = audioCtx.createMediaElementSource(audio); gainNode = audioCtx.createGain(); src.connect(gainNode).connect(audioCtx.destination); } catch (e) { console.warn('geen Web Audio', e); } }
function play() { ensureAudioGraph(); if (audioCtx && audioCtx.state === 'suspended') audioCtx.resume(); audio.play().catch(() => {}); }
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
audio.onplay = () => { $('#btnPlay').textContent = '❚❚'; $('#btnPlay').setAttribute('aria-label', 'Pauzeren'); }; audio.onpause = () => { $('#btnPlay').textContent = '▶'; $('#btnPlay').setAttribute('aria-label', 'Afspelen'); };
$('#btnPlay').onclick = togglePlay;
$('#btnBack').onclick = () => audio.currentTime = Math.max(0, audio.currentTime - 3);
$('#btnFwd').onclick = () => audio.currentTime += 3;
$('#speed').onchange = e => audio.playbackRate = +e.target.value;
$('#gain').onchange = e => { ensureAudioGraph(); if (gainNode) gainNode.gain.value = +e.target.value; };
$('#origAudio').onchange = () => { const t = audio.currentTime, p = !audio.paused; audio.src = `/api/projects/${S.pid}/audio${$('#origAudio').checked ? '?original=1' : ''}`; audio.currentTime = t; if (p) play(); };
$('#clickPlay').checked = pref.get('clickPlay', true);
$('#clickPlay').onchange = e => { pref.set('clickPlay', e.target.checked); $('#editor').classList.toggle('nopick', !e.target.checked); };
function closeListen() { $('#listenPop').classList.add('hidden'); $('#btnListen').setAttribute('aria-expanded', 'false'); }
$('#btnListen').onclick = () => { const p = $('#listenPop'); const nowHidden = p.classList.toggle('hidden'); $('#btnListen').setAttribute('aria-expanded', String(!nowHidden)); if (!nowHidden) $('#preRoll').focus(); };
$('#listenPop').addEventListener('keydown', e => { if (e.key === 'Escape') { e.stopPropagation(); closeListen(); $('#btnListen').focus(); } });
document.addEventListener('click', e => { if (!e.target.closest('.set')) closeListen(); });
let lastPlaying = null;
function highlightPlaying() {
  if (!S.tr) return; const t = audio.currentTime;
  const segs = S.tr.segments; let found = null;
  for (let si = 0; si < segs.length; si++) { const s = segs[si]; if (t < s.start - 0.3 || t > s.end + 0.3) continue; for (let wi = 0; wi < (s.words || []).length; wi++) { const w = s.words[wi]; if (t >= w.start && t <= w.end) { found = `w[data-s="${si}"][data-w="${wi}"]`; break; } } if (found) break; }
  if (found !== lastPlaying) { $$('w.playing').forEach(x => x.classList.remove('playing')); if (found) { const el = $(found); if (el) { el.classList.add('playing'); if (document.activeElement && !document.activeElement.closest('.txt')) el.scrollIntoView({ block: 'nearest' }); } } lastPlaying = found; }
}
function drawWave() {
  const c = $('#waveCanvas'); if (!c || S.view !== 'editor' || !S.meta) return; const W = c.clientWidth, H = 42; if (c.width !== W * devicePixelRatio) { c.width = W * devicePixelRatio; c.height = H * devicePixelRatio; }
  const ctx = c.getContext('2d'); ctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0); ctx.clearRect(0, 0, W, H);
  const dur = S.meta.audio.duration || audio.duration || 1, pk = S.peaks; const n = pk.length || 1;
  const sel = S.loopSel || S.playWindow;
  if (sel) { ctx.fillStyle = 'rgba(43,108,176,.10)'; ctx.fillRect(sel[0] / dur * W, 0, (sel[1] - sel[0]) / dur * W, H); }
  (S.tr?.gaps || []).forEach(g => { if (!g.dismissed) { ctx.fillStyle = 'rgba(192,86,33,.18)'; ctx.fillRect(g.start / dur * W, 0, Math.max(2, (g.end - g.start) / dur * W), H); } });
  for (let x = 0; x < W; x += 3) { const i = Math.floor(x / W * n); const v = pk[i] || 0; const h = Math.max(2, v * (H - 6)); const t = x / W * dur; ctx.fillStyle = (S.heat && S.tr && S.tr.segments.some(s => t >= s.start && t <= s.end && s.words && s.words.some(w => w.p != null && w.p < S.threshold && !w.checked && t >= w.start && t <= w.end))) ? '#f0a042' : '#d9d6ce'; ctx.fillRect(x, H - h, 2, h); }
  ctx.fillStyle = '#2b6cb0'; ctx.fillRect(audio.currentTime / dur * W - 1, 0, 2, H);
}
const wave = $('#wave'); let dragStart = null;
wave.onmousedown = e => { dragStart = e.offsetX; };
wave.onmousemove = e => { if (dragStart == null) return; const dur = S.meta.audio.duration || 1, W = wave.clientWidth; const a = Math.min(dragStart, e.offsetX) / W * dur, b = Math.max(dragStart, e.offsetX) / W * dur; if (b - a > 0.3) { S.loopSel = [a, b]; drawWave(); } };
wave.onmouseup = e => { const dur = S.meta.audio.duration || 1, W = wave.clientWidth; if (S.loopSel && Math.abs(e.offsetX - dragStart) > 4) { audio.currentTime = S.loopSel[0]; play(); } else { S.loopSel = null; S.playWindow = null; audio.currentTime = e.offsetX / W * dur; play(); } dragStart = null; drawWave(); };
window.addEventListener('resize', drawWave);

/* ======================= sneltoetsen ======================= */
document.addEventListener('keydown', e => {
  if (S.view !== 'editor' || !S.tr) return;
  if (inDialogOrField(e)) return;                      // nooit ingrijpen in dialogen en instellingenvelden
  const inTxt = e.target.closest && e.target.closest('.txt');
  const k = e.key.toLowerCase();
  if (e.ctrlKey && e.code === 'Space') { e.preventDefault(); togglePlay(); }
  else if (e.ctrlKey && e.key === 'ArrowLeft') { e.preventDefault(); audio.currentTime = Math.max(0, audio.currentTime - 3); }
  else if (e.ctrlKey && e.key === 'ArrowRight') { e.preventDefault(); audio.currentTime += 3; }
  else if (e.ctrlKey && !e.shiftKey && k === 's') { e.preventDefault(); Saver.save({ force: true }); }
  else if (e.ctrlKey && !e.shiftKey && k === 'z') { e.preventDefault(); History.doUndo(); }
  else if (e.ctrlKey && (k === 'y' || (e.shiftKey && k === 'z'))) { e.preventDefault(); History.doRedo(); }
  else if (e.altKey && e.key === 'ArrowDown') { e.preventDefault(); stepPoint(1); }
  else if (e.altKey && e.key === 'ArrowUp') { e.preventDefault(); stepPoint(-1); }
  else if (!inTxt && !e.ctrlKey && !e.altKey && (k === 'j' || k === 'k')) { e.preventDefault(); stepPoint(k === 'j' ? 1 : -1); }
  else if (e.altKey && k === 'k') { e.preventDefault(); pointOk(); }
  else if (e.altKey && k === 'l') { e.preventDefault(); if (!inTxt && S.curWord && attKinds(S.tr.segments[S.curWord[0]].words[S.curWord[1]]).length) pointLater(); else toggleFlag('later'); }  // in een tekstvak: het segment waarin je typt
  else if (e.altKey && k === 'c') { e.preventDefault(); toggleFlag('quote'); }
  else if (e.altKey && k === 's') { e.preventDefault(); if (S.curSeg != null) cycleSpeaker(S.curSeg); }
  else if (e.ctrlKey && e.key === 'Enter') { e.preventDefault(); if (inTxt) commitSegment(+inTxt.closest('.seg').dataset.s, false); const si = S.curSeg; if (si == null) return; History.edit(si, 1, () => { S.tr.segments[si].reviewed = true; }, 'nagekeken'); rerenderSeg(si); renderSide(); const n = si + 1; if (S.tr.segments[n]) { const t = $(`#seg${n} .txt`); if (t) { t.focus(); S.curSeg = n; t.scrollIntoView({ block: 'center' }); } } }
  else if (e.ctrlKey && k === 'u') { e.preventDefault(); insertText(convText('unintelligible')); }
  else if (e.ctrlKey && k === 'f') { e.preventDefault(); findReplace(); }
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
  $('#cmp').innerHTML = `<h2 style="margin:0 0 4px">Modellen vergelijken</h2><div class="sub">${models.length} model(len), per segment op tijd uitgelijnd. Klik een woord in een modelrij om die variant in het transcript te zetten. Oranje: een model geeft een ander woord. Rood: geen meerderheid.</div>
    <div class="legend"><span><i style="background:var(--accent-bg);border-bottom:2px solid var(--accent)"></i>In transcript</span><span><i style="background:var(--c2b);border-bottom:2px solid var(--c2)"></i>Ander woord</span><span><i style="background:var(--c1b);border-bottom:2px solid var(--c1)"></i>Geen meerderheid</span></div>
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:14px"><div class="card"><small>Alle modellen eens</small><div style="font-size:22px;font-weight:700">${pct('all')}</div></div><div class="card"><small>Meerderheid</small><div style="font-size:22px;font-weight:700">${pct('maj')}</div></div><div class="card"><small>Geen meerderheid</small><div style="font-size:22px;font-weight:700;color:var(--warn)">${pct('none')}</div><small>${stats.none} woorden</small></div><div class="card"><small>Segmenten</small><div style="font-size:22px;font-weight:700">${segs.length}</div></div></div>
    <div class="card"><h5>Overeenstemming over het hele interview (klik om te springen)</h5><div class="tl">${tl.map((c, i) => `<i class="${c}" data-i="${i}" title="${fmtHMS(segs[i].start)}"></i>`).join('')}</div></div>
    <label class="cb" style="display:inline-flex;margin-bottom:10px"><input type="checkbox" id="cmpOnly" checked> alleen segmenten met verschillen</label>
    <div id="cmpList"></div>`;
  const render = () => {
    const only = $('#cmpOnly').checked;
    $('#cmpList').innerHTML = segs.map((s, si) => {
      if (only && !(s.words || []).some(w => w.disagree)) return '';
      const rows = models.map(m => { const ws = wordsIn(m, s.start, s.end); const cur = new Set((s.words || []).map(w => normW(w.word)));
        return `<div class="lbl2">${esc(m)}<small>gem. score ${S.runs[m].stats.mean_p}</small></div><div class="t">${ws.map(w => `<w class="${cur.has(normW(w.word)) ? 'same' : 'diff'}" data-si="${si}" data-t="${w.start}" data-txt="${esc(w.word)}" title="score ${Math.round((w.p || 0) * 100)}%">${esc(w.word)}</w>`).join(' ')}</div>`; }).join('');
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
