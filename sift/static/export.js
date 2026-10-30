/* export.js: exporteren vanuit het doel (Word / MAXQDA / NVivo / Citaten / Ondertitels / Geavanceerd) met een contract
   per formaat, vervangingstabel, voorbeeld en bewaarde instellingen; versiegeschiedenis; back-up. */
'use strict';

const PURPOSES = [
  { id: 'word', label: 'Naar Word', small: 'nakijken, bijlage, delen', fmt: 'docx' },
  { id: 'maxqda', label: 'Naar MAXQDA', small: 'tekst met tijdstempels', fmt: 'maxqda' },
  { id: 'nvivo', label: 'Naar NVivo', small: 'tekst met tijdcodes', fmt: 'nvivo' },
  { id: 'quotes', label: 'Citaten exporteren', small: 'alleen gemarkeerde citaten', fmt: 'quotes' },
  { id: 'srt', label: 'Ondertitels', small: '.srt per segment', fmt: 'srt' },
  { id: 'advanced', label: 'Geavanceerde gegevensformaten', small: 'tekst, CSV, JSON', fmt: 'txt' },
];
const OPTION_LABEL = { style: 'Stijl', timestamps: 'Tijdcodes', ts_format: 'Tijdcodeformaat', speakers: 'Sprekernamen opnemen', quotes_only: 'Alleen gemarkeerde citaten', notes: 'Opmerkingen opnemen', time_offset: 'Tijdcodes t.o.v. de bronopname (fragment)', title: 'Titel', line_numbers: 'Regelnummering', control_overview: 'Controleoverzicht toevoegen', pseudonymize: 'Namen en herkenbare gegevens vervangen' };
const EX = { purpose: pref.get('ex.purpose', 'word'), fmt: null, opts: null, timer: null };

function exportDefaults() {
  const study = S.meta.study?.export_prefs || {}, proj = S.meta.export_prefs || {};
  const names = Object.values(S.tr.speakers || {}).map(s => s.name).filter(n => !/^Spreker \d+$/.test(n));
  return { style: 'verbatim', timestamps: 'paragraph', ts_format: 'brackets', speakers: true, quotes_only: false, notes: false, source_timecodes: true, title: 'Transcript', line_numbers: true, control_overview: false,
    pseudonymize: names.map((n, i) => ({ find: n, replace: `[persoon${i + 1}]` })), pseudonymize_on: false, ...study, ...proj };
}
function renderExport() {
  if (!S.tr) { $('#exp').innerHTML = '<div class="sub">Nog geen transcript.</div>'; return; }
  if (!EX.opts) EX.opts = exportDefaults();
  const purpose = PURPOSES.find(p => p.id === EX.purpose) || PURPOSES[0];
  EX.fmt = EX.fmt && (purpose.id === 'advanced' ? ['txt', 'csv', 'csv_words', 'json'].includes(EX.fmt) : EX.fmt === purpose.fmt) ? EX.fmt : purpose.fmt;
  const c = S.info.export_contracts[EX.fmt], o = EX.opts, has = k => c.options.includes(k);
  const isFragment = S.meta.settings.start != null || S.meta.settings.end != null;
  const rv = S.meta.review || {};
  const sel = (id, items, val) => `<select id="${id}" class="k">${items.map(([v, l]) => `<option value="${v}" ${val === v ? 'selected' : ''}>${l}</option>`).join('')}</select>`;
  const chk = (id, val, label) => `<label class="inline" for="${id}"><input type="checkbox" id="${id}" ${val ? 'checked' : ''}> ${label}</label>`;
  $('#exp').innerHTML = `<h2 style="margin:0 0 4px">Exporteren</h2><div class="sub">Kies eerst het doel. Je ziet alleen instellingen die voor dat formaat gelden; het transcript zelf verandert niet.</div>
    <div class="purpose" role="tablist">${PURPOSES.map(p => `<button role="tab" aria-selected="${p.id === purpose.id}" class="${p.id === purpose.id ? 'on' : ''}" data-p="${p.id}"><b>${esc(p.label)}</b><small>${esc(p.small)}</small></button>`).join('')}</div>
    ${purpose.id === 'advanced' ? `<div class="opt" style="margin-bottom:12px">${[['txt', 'Tekst (.txt)'], ['csv', 'CSV per segment'], ['csv_words', 'CSV per woord'], ['json', 'Transcriptgegevens (JSON)']].map(([f, l]) => `<button class="chip ${EX.fmt === f ? 'on' : ''}" data-f="${f}">${l}</button>`).join('')}</div>` : ''}
    ${rv.reviewed != null && rv.reviewed < rv.segments ? `<div class="note warn">Nog niet alles is nagekeken: ${rv.reviewed} van ${rv.segments} segmenten, ${rv.attention_open} aandachtspunten open. Exporteren kan gewoon; in Word kun je een controleoverzicht meenemen.</div>` : ''}
    <div class="exgrid">
      <div class="form card">
        <h5 style="margin:0">${esc(c.label)}</h5>
        ${c.note ? `<div class="note">${esc(c.note)}</div>` : ''}
        ${has('style') ? `<label for="eStyle">${OPTION_LABEL.style}</label>${sel('eStyle', [['verbatim', 'Verbatim (zoals herkend en gecorrigeerd)'], ['clean', 'Clean verbatim (geselecteerde stopwoorden weg)']], o.style)}<div class="sub" style="margin-top:4px">Verbatim betekent niet dat het model élke aarzeling heeft herkend. Welke stopwoorden weggaan staat in de transcriptieafspraken van het onderzoek${S.meta.study ? '' : ' (zonder onderzoek: eh, ehm, uh, uhm, hm, hmm, mm, mhm)'}.</div>` : ''}
        ${has('timestamps') ? `<label for="eTs">${OPTION_LABEL.timestamps}</label>${sel('eTs', [['paragraph', 'per alinea'], ['minute', 'per minuut'], ['none', 'geen']], o.timestamps)}` : ''}
        ${has('ts_format') ? `<label for="eFmt">${OPTION_LABEL.ts_format}</label>${sel('eFmt', [['brackets', '[00:01:23]'], ['dp', '#00:01:23-4# aan het einde (notatie Dresing & Pehl / f4; dit is alleen het tijdcodeformaat, geen volledig protocol)']], o.ts_format)}` : ''}
        ${c.fixed?.timestamps ? `<div class="sub">Tijdcodes: vast voor dit formaat (${c.fixed.timestamps === 'segment' ? 'per segment' : 'per alinea'}).</div>` : ''}
        <div style="margin-top:8px">${has('speakers') ? chk('eSpk', o.speakers, OPTION_LABEL.speakers) : ''}${has('quotes_only') ? chk('eQ', o.quotes_only, OPTION_LABEL.quotes_only) : (c.fixed?.quotes_only ? '<span class="sub">Alleen gemarkeerde citaten (vast).</span>' : '')}${has('notes') ? chk('eNotes', o.notes, OPTION_LABEL.notes) : ''}${has('time_offset') && isFragment ? chk('eOff', o.source_timecodes, OPTION_LABEL.time_offset + ` (+${fmtHMS(S.meta.settings.start || 0)})`) : ''}</div>
        ${has('title') ? `<label for="eTitle">${OPTION_LABEL.title} (neutraal; de interviewnaam staat er niet automatisch in)</label><input type="text" id="eTitle" value="${esc(o.title)}">` : ''}
        ${has('line_numbers') ? `<div style="margin-top:8px">${chk('eLn', o.line_numbers, OPTION_LABEL.line_numbers)}${chk('eCtl', o.control_overview, OPTION_LABEL.control_overview + ' (nagekeken, open aandachtspunten, afspraken)')}</div>` : ''}
        ${has('pseudonymize') ? `<h5 style="margin:14px 0 4px">${OPTION_LABEL.pseudonymize}</h5>${chk('ePsOn', o.pseudonymize_on, 'Vervangingen toepassen bij deze export')}
          <table class="t tbl" id="psTable"><tr><th>Te vervangen tekst</th><th>Vervanging</th><th></th></tr>${(o.pseudonymize || []).map((r, i) => `<tr><td><input type="text" data-ps="find" data-i="${i}" value="${esc(r.find)}" aria-label="te vervangen"></td><td><input type="text" data-ps="replace" data-i="${i}" value="${esc(r.replace)}" aria-label="vervanging"></td><td><button class="btn small" data-psdel="${i}" aria-label="rij verwijderen">✕</button></td></tr>`).join('')}</table>
          <button class="btn small" id="psAdd">+ rij</button>
          <div class="note">Geldt voor transcripttekst, sprekernamen, opmerkingen, alternatieve woorden, de titel en de bestandsnaam. Hoofdletters en woordgrenzen worden gerespecteerd; alle vervangingen gebeuren in één keer, dus een vervanging kan geen andere vervanging activeren. Dit is pseudonimiseren, geen gegarandeerde anonimisering: plaatsen, organisaties en beschrijvingen kunnen iemand nog herkenbaar maken. De oorspronkelijke opname en het transcript veranderen niet.</div>` : `<div class="note">Dit formaat ondersteunt geen vervangingen van namen.</div>`}
        <div class="actions" style="margin-top:12px"><button class="btn primary" id="eGo">Downloaden</button><span class="sub" id="eFile" style="margin:0"></span></div>
      </div>
      <div>
        <div class="card"><h5>Wat gaat mee in dit bestand</h5><ul style="margin:0;padding-left:18px">${c.includes.map(x => `<li>${esc(x)}</li>`).join('')}</ul>${c.excludes?.length ? `<div class="sub" style="margin:6px 0 0">Niet: ${esc(c.excludes.join(', '))}.</div>` : ''}<div id="eHits" class="sub" style="margin:6px 0 0"></div></div>
        <div class="card"><h5>Voorbeeld</h5><div class="preview" id="ePreview" aria-live="polite">…</div></div>
      </div>
    </div>
    <h3 style="margin-top:22px">Versies</h3><div class="sub">Elke versie is een volledige kopie van het transcript. Herstellen bewaart eerst automatisch de huidige toestand.</div><div class="vlist" id="vlist">laden…</div>
    <h3 style="margin-top:22px">Volledige back-up</h3><div class="sub">Een zip met de <b>oorspronkelijke opname</b>, transcript, sprekers, opmerkingen, versies, modeluitvoer en instellingen (en het onderzoek). Dit is géén gepseudonimiseerde export: deel een back-up niet. Afgeleide audiobestanden worden niet meegenomen; die maakt Sift bij een volgende verwerking opnieuw.</div><a class="btn" id="bkDown" href="/api/projects/${esc(S.pid)}/backup" download>Back-up downloaden (.zip)</a>`;
  $$('#exp [data-p]').forEach(b => b.onclick = () => { readOpts(); EX.purpose = b.dataset.p; pref.set('ex.purpose', EX.purpose); EX.fmt = null; renderExport(); });
  $$('#exp [data-f]').forEach(b => b.onclick = () => { readOpts(); EX.fmt = b.dataset.f; renderExport(); });
  $('#exp .form').oninput = () => { readOpts(); schedulePreview(); };
  if ($('#psAdd')) $('#psAdd').onclick = () => { readOpts(); EX.opts.pseudonymize.push({ find: '', replace: `[persoon${EX.opts.pseudonymize.length + 1}]` }); renderExport(); };
  $$('#exp [data-psdel]').forEach(b => b.onclick = () => { readOpts(); EX.opts.pseudonymize.splice(+b.dataset.psdel, 1); renderExport(); });
  $('#eGo').onclick = doExport;
  schedulePreview(0); loadVersions();
}
function readOpts() {
  const o = EX.opts; const g = id => $(id); const v = (id, k, bool) => { const el = g(id); if (el) o[k] = bool ? el.checked : el.value; };
  v('#eStyle', 'style'); v('#eTs', 'timestamps'); v('#eFmt', 'ts_format'); v('#eSpk', 'speakers', true); v('#eQ', 'quotes_only', true); v('#eNotes', 'notes', true); v('#eOff', 'source_timecodes', true); v('#eTitle', 'title'); v('#eLn', 'line_numbers', true); v('#eCtl', 'control_overview', true); v('#ePsOn', 'pseudonymize_on', true);
  if ($('#psTable')) { const rows = {}; $$('#psTable input[data-ps]').forEach(i => { (rows[i.dataset.i] = rows[i.dataset.i] || {})[i.dataset.ps] = i.value; }); o.pseudonymize = Object.keys(rows).sort((a, b) => a - b).map(k => rows[k]); }
  pref.set('ex.opts', o);
}
function serverOpts() {
  const o = EX.opts;
  return { style: o.style, timestamps: o.timestamps, ts_format: o.ts_format, speakers: o.speakers, quotes_only: o.quotes_only, notes: o.notes, title: o.title, line_numbers: o.line_numbers, control_overview: o.control_overview,
    source_timecodes: !!o.source_timecodes, pseudonymize: o.pseudonymize_on ? o.pseudonymize.filter(r => r.find.trim()) : [], threshold: S.threshold };
}
function schedulePreview(ms = 400) { clearTimeout(EX.timer); EX.timer = setTimeout(async () => { try { const r = await post(`/projects/${S.pid}/export/${EX.fmt}/preview`, serverOpts()); $('#ePreview').textContent = r.preview; $('#eFile').textContent = 'Bestandsnaam: ' + r.filename; const hits = Object.entries(r.replacements || {}); $('#eHits').innerHTML = EX.opts.pseudonymize_on ? (hits.length ? 'Vervangingen in deze export: ' + hits.map(([k, n]) => `${esc(k)} → ${n}×`).join(', ') : 'Geen vervangingen ingevuld.') : ''; } catch (e) { $('#ePreview').textContent = 'Voorbeeld niet beschikbaar: ' + e.message; } }, ms); }
async function doExport() {
  readOpts();
  if (!(await Saver.flush())) return toast('Opslaan mislukt; export afgebroken zodat niets verloren gaat');
  const r = await fetch(`/api/projects/${S.pid}/export/${EX.fmt}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(serverOpts()) });
  if (!r.ok) return toast('Export mislukt');
  const blob = await r.blob(); const cd = r.headers.get('content-disposition') || ''; const fn = decodeURIComponent((cd.match(/filename="([^"]+)"/) || [])[1] || 'export');
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = fn; a.click(); URL.revokeObjectURL(a.href);
  put(`/projects/${S.pid}/export_prefs`, { ...EX.opts }).catch(() => {});
  toast('Gedownload: ' + fn);
}

/* ---------- versies ---------- */
async function loadVersions() {
  const vs = await api(`/projects/${S.pid}/versions`);
  $('#vlist').innerHTML = vs.length ? vs.map(v => `<div class="v"><div style="width:150px;flex:none"><b>${esc(v.label || (v.version != null ? 'versie ' + v.version : 'versie'))}</b><div class="sub" style="margin:0">${esc((v.created || '').replace('T', ' ').slice(0, 16))}</div></div><div class="pv">${v.segments ?? '?'} segmenten · ${esc(v.preview || '')}</div><div style="flex:none"><button class="btn small" data-vp="${esc(v.file)}">Bekijken</button> <button class="btn small" data-vr="${esc(v.file)}">Herstellen</button></div></div>`).join('') : '<div class="sub">Nog geen versies. Gebruik "Versie bewaren" in het transcript.</div>';
  $$('#vlist [data-vp]').forEach(b => b.onclick = async () => { const t = await api(`/projects/${S.pid}/versions/${b.dataset.vp}`); modal(`<h3>Versie ${esc(b.dataset.vp)}</h3><div class="preview" style="max-height:60vh">${esc(t.segments.map(s => `${fmtHMS(s.start)} ${(t.speakers?.[s.speaker]?.name) || ''}: ${s.text}`).join('\n\n'))}</div>`, { wide: true, label: 'Versie bekijken' }); });
  $$('#vlist [data-vr]').forEach(b => b.onclick = async () => { if (!(await confirmBox('Deze versie herstellen? De huidige toestand wordt eerst automatisch bewaard als versie "voor herstel".', 'Herstellen'))) return; if (!(await Saver.flush())) return toast('Opslaan mislukt; herstel afgebroken'); await post(`/projects/${S.pid}/versions/${b.dataset.vr}/restore`, { transcript: S.tr }); await loadTranscript(); History.clear(); await refreshMeta(); toast('Versie hersteld'); renderExport(); });
}
