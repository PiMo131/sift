/* process.js: 'Opname verwerken' — voortgang in gewone taal, modeldownload apart, resterende tijd met marge,
   fouten als vervolgstappen, technische details ingeklapt. */
'use strict';

const PHASE_ORDER = [['prepare', 'Opname voorbereiden', 'Inlezen, luidheid gelijktrekken, spraak en stilte in kaart brengen.'],
  ['transcribe', 'Tekst herkennen', 'Elk gekozen spraakmodel zet de opname om in woorden met tijdcodes.'],
  ['diarize', 'Sprekers toewijzen', 'Stemkenmerken per segment vergelijken en groeperen.'],
  ['combine', 'Transcript voorbereiden', 'Uitkomsten combineren en controleren op mogelijk ontbrekende tekst.']];

function renderProcess() {
  const m = S.meta, st = m.settings, sd = m.status_detail || {}, models = S.info.models, hw = S.info.hardware;
  const runsDone = Object.keys(m.runs || {});
  const isFragment = st.start != null || st.end != null;
  const phaseIdx = { prepare: 0, download: 1, transcribe: 1, diarize: 2, combine: 3, done: 4, cancelled: -1, error: -1, idle: -1 }[sd.phase] ?? -1;
  const stepState = i => { if (m.status === 'klaar') return 'ok'; if (!sd.running) { if (i === 0 && m.steps?.normalize) return 'ok'; if (i === 1 && runsDone.length >= (st.models || []).length && runsDone.length) return 'ok'; return ''; } return i < phaseIdx ? 'ok' : i === phaseIdx ? 'run' : ''; };
  const eta = sd.eta ? `Nog ongeveer ${fmtDur(sd.eta.low)} tot ${fmtDur(sd.eta.high)}` : (sd.running && sd.phase === 'transcribe' ? 'Resterende tijd wordt geschat zodra er genoeg gegevens zijn…' : '');
  const dl = sd.download;
  const est = () => { const dur = m.audio.duration || 0; if (!dur) return ''; const cpu = st.device === 'cpu' || !hw.cuda; const tot = (st.models || []).reduce((a, id) => a + dur / (cpu ? models[id].xrt_cpu : models[id].xrt_gpu), 0); return `Verwachte duur op deze computer: ongeveer ${fmtDur(tot * 0.8)} tot ${fmtDur(tot * 1.6)}${(st.models || []).some(id => !models[id].downloaded) ? ', plus de eenmalige modeldownload' : ''}.`; };
  const errBox = m.status === 'fout' || m.status === 'onderbroken' ? `<div class="err"><h4>${esc(m.error_help?.title || 'Verwerking mislukt')}</h4><ol>${(m.error_help?.steps || []).map(s => `<li>${esc(s)}</li>`).join('')}</ol></div>` : '';
  const runRows = Object.entries(m.runs || {}).map(([id, r]) => `<tr><td>${esc(models[id]?.label || id)}</td><td>${esc(r.stats.device)} ${esc(r.stats.compute)}</td><td>${r.stats.run_s}s (${r.stats.realtime_factor}×)</td><td>${r.stats.n_words}</td><td>${r.stats.mean_p}</td><td>${m.summary?.[id]?.uncertain ?? ''}</td></tr>`).join('');
  const lo = m.audio.loudness;
  $('#pipe').innerHTML = `
  <div>
    <h2 style="margin:0 0 4px">Opname verwerken</h2>
    <div class="sub">${esc(m.name)}${m.audio.source_info ? ` · ${fmtT(m.audio.source_info.duration)}${isFragment ? ` · fragment ${fmtHMS(st.start || 0)}–${st.end != null ? fmtHMS(st.end) : 'einde'}` : ''}` : ''}. Alles gebeurt op deze computer. ${sd.running ? '' : est()}</div>
    ${errBox}
    ${PHASE_ORDER.map(([k, label, text], i) => `<div class="step"><div class="n ${stepState(i)}">${stepState(i) === 'ok' ? '✓' : i + 1}</div><div style="flex:1"><h4>${esc(label)}</h4><p>${esc(text)}</p>
      ${k === 'transcribe' ? `<p style="margin-top:4px">Modellen: ${(st.models || []).map(id => `${esc(models[id]?.label || id)}${runsDone.includes(id) ? ' ✓' : ''}`).join(', ')}${(st.models || []).some(id => !models[id]?.downloaded && !runsDone.includes(id)) ? ' · een model dat nog niet op deze computer staat wordt eerst eenmalig gedownload (internet nodig)' : ''}</p>` : ''}
      ${k === 'diarize' ? `<p style="margin-top:4px">${st.diarize ? (st.num_speakers ? `${st.num_speakers} sprekers opgegeven.` : 'Aantal sprekers wordt geschat (2–5); controleer dit in het transcript.') : 'Uitgeschakeld.'}${m.diarization ? ` Gevonden: ${m.diarization.speakers}.` : ''}</p>` : ''}
      ${sd.running && i === phaseIdx ? `${dl ? `<div class="prog"><i class="dl" style="width:${dl.total ? Math.min(100, Math.round(dl.bytes / dl.total * 100)) : 0}%"></i></div><p style="margin-top:6px"><b>Model downloaden</b> · ${(dl.bytes / 1e9).toFixed(2)} van ± ${(dl.total / 1e9).toFixed(1)} GB · eenmalig, daarna werkt Sift offline</p>` : `<div class="prog"><i style="width:${Math.round((sd.progress || 0) * 100)}%"></i></div><p style="margin-top:6px"><b>${esc(sd.step)}</b> · ${Math.round((sd.progress || 0) * 100)}% · ${esc(sd.detail || '')}${sd.models_total > 1 && k === 'transcribe' ? ` · model ${Math.min(sd.models_done + 1, sd.models_total)} van ${sd.models_total}` : ''}</p>${eta ? `<p style="margin-top:2px;color:var(--muted)">${esc(eta)} (schatting met marge)</p>` : ''}`}` : ''}
    </div></div>`).join('')}
    <div class="actions" style="margin-top:6px">
      ${sd.running ? `<button class="btn" id="pCancel">Onderbreken</button>` : `<button class="btn primary" id="pRun">${m.status === 'klaar' ? 'Opnieuw verwerken' : m.status === 'nieuw' ? 'Starten' : 'Hervatten'}</button>`}
      ${m.status === 'klaar' && isFragment ? `<button class="btn" id="pFull">Nu de hele opname verwerken</button>` : ''}
      ${S.tr ? `<button class="btn" id="pOpen">Open transcript</button>` : ''}
    </div>
    ${sd.running ? '<div class="note">Onderbreken stopt het lopende model; afgeronde stappen en jouw correcties blijven bewaard. Hervatten gaat verder waar het bleef.</div>' : ''}
    ${m.status === 'klaar' && !isFragment ? '' : ''}
    ${isFragment ? '<div class="note">Dit is een fragment: tijdcodes in het transcript tellen vanaf de fragmentstart (' + fmtHMS(st.start || 0) + ' in de bronopname). Bij exporteren kun je ze omrekenen naar de bronopname.</div>' : ''}
    <details id="pSettings"><summary>Instellingen voor deze verwerking</summary>
      <div class="form">
        <label for="pLang">Gesproken taal</label><select id="pLang">${S.info.languages.map(([c, l]) => `<option value="${c}" ${c === (st.language || '') ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select>
        <label for="pNum">Aantal sprekers</label><select id="pNum"><option value="">Weet ik niet (schatten)</option>${[1, 2, 3, 4, 5].map(n => `<option value="${n}" ${st.num_speakers === n ? 'selected' : ''}>${n}</option>`).join('')}</select>
        <label for="pPrompt">Namen, afkortingen en vaktermen van dit interview</label><input type="text" id="pPrompt" value="${esc(st.initial_prompt || '')}">
        ${m.study ? `<div class="note">Woordenlijst van onderzoek "${esc(m.study.name)}" wordt erbij gevoegd: <i>${esc(m.study.terms || '(leeg)')}</i>. Samen: <i>${esc(m.effective_terms || '(leeg)')}</i>.</div>` : ''}
        <label>Fragment (leeg = hele opname)</label><div style="display:flex;gap:8px;align-items:center"><input type="text" class="short" id="pStart" value="${st.start != null ? fmtT(st.start) : ''}" placeholder="start mm:ss" aria-label="start"><input type="text" class="short" id="pEnd" value="${st.end != null ? fmtT(st.end) : ''}" placeholder="einde mm:ss" aria-label="einde"></div>
        <details><summary>Geavanceerd</summary>
          <label>Spraakmodellen</label><div class="opt">${Object.entries(models).filter(([id, x]) => x.available || st.models.includes(id)).map(([id, x]) => `<label class="cb ${x.available ? '' : 'na'}"><input type="checkbox" class="pModel" value="${id}" ${st.models.includes(id) ? 'checked' : ''} ${x.available ? '' : 'disabled'}> ${esc(x.label)} <small>· ${x.downloaded ? 'op deze computer' : `download ± ${x.size_gb} GB`}${x.available ? '' : ' · niet geïnstalleerd'}</small></label>`).join('')}</div>
          <label for="pComb">Combineren</label><select id="pComb">${[['consensus', 'Consensus (meerderheid per woord)'], ['highest_p', 'Hoogste modelscore wint'], ['base_plus_alts', 'Eerste model + alternatieven']].map(([v, l]) => `<option value="${v}" ${st.combine === v ? 'selected' : ''}>${l}</option>`).join('')}</select>
          <label for="pDev">Rekenen op</label><select id="pDev">${[['auto', 'Automatisch'], ['cuda', 'GPU'], ['cpu', 'CPU']].map(([v, l]) => `<option value="${v}" ${st.device === v ? 'selected' : ''} ${v === 'cuda' && !hw.cuda ? 'disabled' : ''}>${l}</option>`).join('')}</select>
          <label class="inline" for="pNorm"><input type="checkbox" id="pNorm" ${st.normalize ? 'checked' : ''}> Luidheid normaliseren</label>
          <label class="inline" for="pComp"><input type="checkbox" id="pComp" ${st.compressor ? 'checked' : ''}> Compressor</label>
          <label class="inline" for="pDiar"><input type="checkbox" id="pDiar" ${st.diarize ? 'checked' : ''}> Sprekers toewijzen</label>
          <label for="pLufs">Doelluidheid (LUFS)</label><select id="pLufs">${[-16, -18, -20].map(v => `<option ${st.target_lufs == v ? 'selected' : ''}>${v}</option>`).join('')}</select>
          <label for="pDen">Ruisonderdrukking</label><select id="pDen">${[['off', 'Uit'], ['light', 'Licht'], ['strong', 'Sterk']].map(([v, l]) => `<option value="${v}" ${st.denoise === v ? 'selected' : ''}>${l}</option>`).join('')}</select>
          <label for="pHot">Stopwoord-hint (hotwords)</label><input type="text" id="pHot" value="${esc(st.hotwords)}">
          <div class="actions"><button class="btn" id="pRecomb" ${runsDone.length < 1 || sd.running ? 'disabled' : ''}>Alleen opnieuw combineren</button></div>
        </details>
        <div class="note">Gewijzigde instellingen gelden bij 'Opnieuw verwerken' of 'Hervatten'. Alleen de stappen die geraakt worden, draaien opnieuw.</div>
      </div>
    </details>
  </div>
  <div>
    <details ${sd.running ? '' : ''}><summary>Technische details</summary>
      <div class="card"><h5>Modelruns</h5>${runRows ? `<table class="t"><tr><th>model</th><th>apparaat</th><th>tijd</th><th>woorden</th><th>gem. score</th><th>aandacht</th></tr>${runRows}</table>` : '<div class="sub">Nog geen runs.</div>'}<div class="sub" style="margin:6px 0 0">"Gem. score" is de gemiddelde ruwe modelscore; het is geen gemeten kans dat een woord correct is.</div></div>
      ${lo ? `<div class="card"><h5>Luidheid</h5>${lo.before_lufs.toFixed(1)} LUFS → ${lo.after_lufs.toFixed(1)} LUFS (bereik ${lo.before_lra.toFixed(1)} → ${lo.after_lra.toFixed(1)} LU)</div>` : ''}
      ${m.error ? `<div class="card"><h5>Foutmelding</h5><div class="log">${esc(m.error)}</div></div>` : ''}
      <div class="card"><h5>Logboek</h5><div class="log" id="pLog">${(m.log || []).map(esc).join('\n')}</div></div>
    </details>
  </div>`;
  const collect = () => ({ language: $('#pLang').value, num_speakers: $('#pNum').value ? +$('#pNum').value : null, initial_prompt: $('#pPrompt').value, start: parseMMSS($('#pStart').value) || null, end: parseMMSS($('#pEnd').value),
    models: $$('.pModel:checked').map(c => c.value), combine: $('#pComb').value, device: $('#pDev').value, normalize: $('#pNorm').checked, compressor: $('#pComp').checked, diarize: $('#pDiar').checked, target_lufs: +$('#pLufs').value, denoise: $('#pDen').value, hotwords: $('#pHot').value });
  const startRun = async (extra = {}) => { const s = { ...collect(), ...extra }; if (!s.models.length) return toast('Kies minstens één spraakmodel'); await put(`/projects/${S.pid}/settings`, s); await post(`/projects/${S.pid}/run`); await refreshMeta(); renderProcess(); };
  if ($('#pRun')) $('#pRun').onclick = () => startRun();
  if ($('#pFull')) $('#pFull').onclick = async () => { if (await confirmBox('De hele opname verwerken? Het fragmenttranscript wordt vervangen door het volledige transcript (er wordt eerst een versie bewaard).')) { if (S.tr) await post(`/projects/${S.pid}/snapshot`, { label: 'fragment', transcript: S.tr }); startRun({ start: null, end: null }); } };
  if ($('#pCancel')) $('#pCancel').onclick = async () => { await post(`/projects/${S.pid}/cancel`); toast('Wordt onderbroken…'); };
  if ($('#pRecomb')) $('#pRecomb').onclick = async () => { const s = collect(); await put(`/projects/${S.pid}/settings`, s); await post(`/projects/${S.pid}/recombine`, { combine: s.combine, models: s.models }); await refreshMeta(); await loadTranscript(); toast('Opnieuw gecombineerd'); renderProcess(); };
  if ($('#pOpen')) $('#pOpen').onclick = async () => { if (!S.tr) await loadTranscript(); enableTabs(true, !!S.tr); show('editor'); };
  clearTimeout(S.pollTimer);
  if (sd.running) S.pollTimer = setTimeout(async () => { if (S.view !== 'process') return; const was = S.meta.status; const open = $('#pSettings')?.open; await refreshMeta(); if (S.meta.status === 'klaar' && was !== 'klaar') { await loadTranscript(); enableTabs(true, !!S.tr); toast('Transcript beschikbaar'); } renderProcess(); if (open) $('#pSettings').open = true; }, 1500);
}
