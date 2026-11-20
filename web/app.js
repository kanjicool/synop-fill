/* synop-fill: หน้าเว็บ (vanilla JS ไม่ใช้ module เพราะบางเครื่องเปิดผ่าน file:// ไม่ได้)
 * ตรรกะทั้งหมด (ถอดรหัส ตรวจค่า อธิบายรหัส สร้างไฟล์) อยู่ฝั่ง Python ที่นี่ทำแค่แสดงผลและเก็บสถานะหน้าจอ */
(function () {
  'use strict';
  const $ = (s) => document.querySelector(s);
  const pad = (n) => String(n).padStart(2, '0');
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const COLS = [['B', 'ทิศลม'], ['C', 'กำลังลม'], ['D', 'ท้องฟ้า'], ['E', 'ลักษณะอากาศ'], ['F', 'อุณหภูมิ'], ['G', 'ฝน 3 ชม.'], ['H', 'ฝนสะสม']];
  const LV = { err: 'ต้องแก้', warn: 'เตือน', note: 'แจ้ง' };

  let cfg = null;
  const today = () => { const n = new Date(); return { y: n.getFullYear(), m: n.getMonth() + 1, d: n.getDate() }; };
  const blankRow = (s) => ({
    code: s.code, name: s.name, raw: '', status: 'pending', B: '', C: '', D: '', E: '', F: '', G: '', H: '',
    fAuto: true, has_code: false, nil: false, problem: '', touched: false, msg_time: null, f_syn: null, dew: null, explain: null,
  });
  const st = {
    view: 'start', tab: 'st', cur: 0, ref: today(), dateOverride: null, roundOverride: null, filenameEdited: false,
    prev: null, prevFile: null, demo: false, rows: [], report: null,
  };
  const cur = () => st.rows[st.cur];

  /* ---------- เรียก API ---------- */
  async function api(path, opts) {
    let res;
    try { res = await fetch(path, opts); }
    catch (e) { throw new Error('เชื่อมต่อระบบไม่ได้ ตรวจว่าระบบยังทำงานอยู่ แล้วลองใหม่'); }
    if (!res.ok) {
      let msg = 'เกิดข้อผิดพลาด (' + res.status + ')';
      try { const j = await res.json(); if (typeof j.detail === 'string') msg = j.detail; } catch (_) { /* ไม่มีรายละเอียด */ }
      throw new Error(msg);
    }
    return res;
  }
  const getJson = async (p, o) => (await api(p, o)).json();
  const postJson = (p, body) => getJson(p, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });

  function toast(msg) {
    const t = $('#toast'); t.textContent = msg; t.hidden = false;
    clearTimeout(toast._t); toast._t = setTimeout(() => { t.hidden = true; }, 4500);
  }
  const thaiDate = (iso) => { const [y, m, d] = iso.split('-').map(Number); return d + ' ' + cfg.months[m - 1] + ' ' + (y + 543); };

  /* ---------- ตรวจทั้งรายงาน (เรียกหลังข้อมูลเปลี่ยน) ---------- */
  function checkPayload() {
    return {
      rows: st.rows.map((r) => ({
        code: r.code, status: r.status, B: r.B, C: r.C, D: r.D, E: r.E, F: r.F, G: r.G, H: r.H,
        has_code: r.has_code, nil: r.nil, problem: r.problem, touched: r.touched, msg_time: r.msg_time, f_syn: r.f_syn, dew: r.dew,
      })),
      ref: st.ref, date_override: st.dateOverride, round_override: st.roundOverride,
      prev: st.prev ? { h: st.prev.h, round: st.prev.round, date: st.prev.date } : null,
    };
  }
  let checkSeq = 0, checkTimer = null;
  async function runCheck() {
    const my = ++checkSeq;
    try {
      const rep = await postJson('/api/check', checkPayload());
      if (my !== checkSeq) return false;
      st.report = rep; return true;
    } catch (e) { toast(e.message); return false; }
  }
  function scheduleCheck(after) {
    clearTimeout(checkTimer);
    checkTimer = setTimeout(async () => { if (await runCheck()) after(); }, 150);
  }
  const flagsOf = (i) => (st.report && st.report.flags[i]) || {};
  const hLabel = () => (st.report ? st.report.h_label : cfg.h_label_today);

  /* ---------- ขั้นตอนหน้าจอ ---------- */
  function go(view) {
    st.view = view;
    $('#v-start').hidden = view !== 'start'; $('#v-work').hidden = view !== 'work'; $('#v-save').hidden = view !== 'save';
    const s = view === 'start' ? 1 : view === 'work' ? 2 : 3;
    document.querySelectorAll('#stepper li').forEach((li) => { const n = +li.dataset.s; li.className = n === s ? 'cur' : n < s ? 'done' : ''; });
    $('#demoTag').hidden = !st.demo;
    window.scrollTo({ top: 0, behavior: 'auto' });
  }
  async function showTab(tab) {
    st.tab = tab;
    $('#v-stations').hidden = tab !== 'st'; $('#v-excel').hidden = tab !== 'xl';
    $('#tabSt').setAttribute('aria-selected', tab === 'st'); $('#tabXl').setAttribute('aria-selected', tab === 'xl');
    if (tab === 'st') { renderStation(); }
    else { await runCheck(); buildXl(); }
  }

  /* ---------- หน้ากรอกทีละสถานี ---------- */
  function renderStation() {
    const r = cur();
    $('#stNo').textContent = 'สถานีที่ ' + (st.cur + 1) + ' จาก 21';
    $('#stName').textContent = r.name;
    $('#stMeta').textContent = r.code + ' · แถว ' + (st.cur + 4) + ' ในไฟล์';
    $('#raw').value = r.raw; $('#fF').value = r.F; $('#fG').value = r.G; $('#fH').value = r.H;
    renderStationLive();
  }
  function renderPreview(r) {
    const pv = $('#preview');
    if (r.problem) { pv.innerHTML = '<div class="pverr">' + esc(r.problem) + '</div>'; return; }
    if (r.has_code || r.nil) {
      const t = r.msg_time ? 'วันที่ ' + r.msg_time.day + ' · ' + pad(r.msg_time.hour) + '.00 น.' : '—';
      const item = (k, v) => '<div><small>' + k + '</small>' + (v ? '<b>' + esc(v) + '</b>' : '<b class="na">(ว่าง)</b>') + '</div>';
      pv.innerHTML = '<div class="pvt">ระบบถอดรหัสได้ดังนี้ (ตรวจกับหน้า METNET ได้ ก่อนกดถัดไป)</div><div class="pvgrid">'
        + item('เวลาของข้อความ', t)
        + (r.nil ? '<div><small>สถานะ</small><b>NIL ไม่มีข้อมูล</b></div>' : item('ทิศลม', r.B) + item('กำลังลม', r.C) + item('ท้องฟ้า', r.D) + item('ลักษณะอากาศ', r.E))
        + '</div>';
      return;
    }
    pv.innerHTML = '<div class="pvt">วางรหัสข่าวแล้วระบบจะถอดทิศลม กำลังลม ท้องฟ้า และลักษณะอากาศให้ตรงนี้</div>';
  }
  function renderExplain() {
    const r = cur(), box = $('#exBody');
    if (!r.explain) { box.innerHTML = '<p class="hint" style="margin:0">วางรหัสข่าวด้านบนแล้วระบบจะอธิบายทีละกลุ่ม พร้อมบอกว่ากลุ่มไหนลงช่องไหนของ Excel</p>'; return; }
    box.innerHTML = '<div class="tokstrip" aria-label="กลุ่มรหัสทั้งหมด">'
      + r.explain.map((x, k) => '<button type="button" class="tok ' + x.cls + '" data-k="' + k + '">' + esc(x.token) + '</button>').join('') + '</div>'
      + '<div class="exlist">' + r.explain.map((x, k) =>
        '<div class="excard ' + x.cls + '" id="exc' + k + '"><div class="tk">' + esc(x.token) + '</div><div><h4>' + esc(x.title)
        + '<span class="badge ' + x.cls + '">' + esc(x.badge) + '</span></h4><ul>' + x.lines.map((l) => '<li>' + esc(l) + '</li>').join('') + '</ul></div></div>').join('') + '</div>';
  }
  function renderStationLive() {
    const i = st.cur, r = cur(), f = flagsOf(i);
    ['F', 'G', 'H'].forEach((c) => { const el = $('#f' + c); if (document.activeElement !== el) el.value = r[c]; });
    $('#lH').textContent = hLabel();
    renderPreview(r); renderExplain();
    const show = (col) => {
      const x = f[col], el = $('#f' + col), m = $('#m' + col);
      el.classList.remove('err', 'warn', 'note'); if (x) el.classList.add(x.lvl);
      let html = x ? '<span class="' + x.lvl + '">' + esc(x.msg) + '</span>' : '';
      if (col === 'F' && !x && r.has_code && r.fAuto && r.F) html = '<span>ดึงจากรหัสข่าวให้แล้ว แก้ได้</span>';
      if (col === 'H' && st.report && st.report.prev_list) {
        const old = st.report.prev_list[i];
        html = '<span>H รอบก่อนในไฟล์ต้นแบบ = ' + esc(old === 'T' ? 'T' : (isNaN(parseFloat(old)) ? '-' : parseFloat(old).toFixed(1))) + '</span>' + (x ? ' · ' + html : '');
      }
      m.innerHTML = html;
    };
    show('F'); show('G'); show('H');
    $('#backBtn').disabled = i === 0;
    $('#nextBtn').textContent = i === 20 ? 'ยืนยัน ดู Excel จำลอง' : 'ถัดไป';
    const done = st.rows.filter((x) => x.status !== 'pending').length;
    $('#barFill').style.width = (done / 21 * 100) + '%'; $('#progTxt').textContent = 'จัดการแล้ว ' + done + '/21 สถานี';
    $('#chips21').innerHTML = st.rows.map((x, k) => {
      let c = x.status === 'done' ? 'done' : x.status === 'skipped' ? 'skipped' : '';
      const lv = Object.values(flagsOf(k)).map((z) => z.lvl);
      if (x.status === 'done') { if (lv.includes('err')) c += ' bad'; else if (lv.includes('warn')) c += ' warn'; }
      if (k === st.cur) c += ' curr';
      return '<button type="button" data-k="' + k + '" class="' + c + '" title="' + esc(x.name) + '" aria-label="สถานีที่ ' + (k + 1) + ' ' + esc(x.name) + '"' + (k === st.cur ? ' aria-current="step"' : '') + '>' + (k + 1) + '</button>';
    }).join('');
  }
  function syncFields() {
    const r = cur();
    ['F', 'G', 'H'].forEach((c) => { const el = $('#f' + c); if (document.activeElement !== el) el.value = r[c]; });
  }
  function applyDecoded(r, d) {
    r.problem = d.problem; r.nil = d.nil; r.has_code = d.has_code; r.msg_time = d.msg_time;
    r.f_syn = d.f_syn; r.dew = d.dew; r.explain = d.explain;
    r.B = d.B; r.C = d.C; r.D = d.D; r.E = d.E;
    if (r.fAuto) r.F = d.F;
    if (d.nil) { if (r.G === '') r.G = '-'; if (r.H === '') r.H = '-'; }
  }
  let decodeSeq = 0, rawTimer = null;
  function onRawInput() {
    const r = cur(); r.raw = $('#raw').value;
    clearTimeout(rawTimer);
    rawTimer = setTimeout(async () => {
      const my = ++decodeSeq, row = cur();
      try {
        const d = await postJson('/api/decode', { code: row.code, raw: row.raw });
        if (my !== decodeSeq || row !== cur()) return;
        applyDecoded(row, d); renderPreview(row); renderExplain(); syncFields();
        scheduleCheck(renderStationLive);
      } catch (e) { toast(e.message); }
    }, 120);
  }
  const hasContent = (r) => r.raw.trim() || r.F.trim() || r.G.trim() || r.H.trim();
  function goStation(k) { st.cur = Math.max(0, Math.min(20, k)); renderStation(); $('#raw').focus({ preventScroll: true }); }
  async function nextStation() {
    const r = cur();
    if (hasContent(r)) r.status = 'done';
    else { r.status = 'skipped'; toast('สถานี' + r.name + ' ไม่ได้กรอกอะไร ถือว่าข้ามไว้ แก้ใน Excel จำลองได้ภายหลัง'); }
    if (st.cur === 20) { await showTab('xl'); return; }
    await runCheck(); goStation(st.cur + 1);
  }
  async function skipStation() {
    const r = cur();
    Object.assign(r, { raw: '', F: '', G: '', H: '', fAuto: true, status: 'skipped', touched: false, B: '', C: '', D: '', E: '', has_code: false, nil: false, problem: '', msg_time: null, f_syn: null, dew: null, explain: null });
    if (st.cur === 20) { await showTab('xl'); return; }
    await runCheck(); goStation(st.cur + 1);
  }

  /* ---------- Excel จำลอง ---------- */
  function selHtml(col, val) {
    const list = cfg.options[col], opts = [''].concat(list); if (val && !list.includes(val)) opts.push(val);
    return '<select data-col="' + col + '" aria-label="' + col + '">' + opts.map((o) => '<option value="' + esc(o) + '"' + (o === val ? ' selected' : '') + '>' + esc(o) + '</option>').join('') + '</select>';
  }
  const inHtml = (col, val) => '<input type="text" inputmode="decimal" data-col="' + col + '" value="' + esc(val) + '" autocomplete="off" spellcheck="false">';
  function buildXl() {
    let h = '<tr><th class="rn">1</th><td class="title" colspan="8"><div class="t1">รายงานผลการตรวจอากาศ บริเวณภาคใต้ฝั่งตะวันออก</div><div class="t2" id="xlSub"></div></td></tr>';
    h += '<tr><th class="rn">2</th><td colspan="8" style="height:14px;border-left:0;border-right:0"></td></tr>';
    h += '<tr><th class="rn">3</th><td class="hd">สถานี</td><td class="hd" colspan="2">ทิศทาง / กำลังลม</td><td class="hd" colspan="2">ท้องฟ้า / ลักษณะอากาศ</td><td class="hd">อุณหภูมิ (°C)</td><td class="hd">ฝน 3 ชม. (มม.)</td><td class="hd" id="xlH"></td></tr>';
    st.rows.forEach((r, i) => {
      h += '<tr data-i="' + i + '"><th class="rn">' + (i + 4) + '</th><td class="sta" data-c="S">' + esc(r.name) + '</td>'
        + '<td data-c="B">' + selHtml('B', r.B) + '</td><td data-c="C">' + selHtml('C', r.C) + '</td><td data-c="D">' + selHtml('D', r.D) + '</td><td data-c="E">' + selHtml('E', r.E) + '</td>'
        + '<td class="num" data-c="F">' + inHtml('F', r.F) + '</td><td class="num" data-c="G">' + inHtml('G', r.G) + '</td><td class="num" data-c="H">' + inHtml('H', r.H) + '</td></tr>';
    });
    h += '<tr><th class="rn">25</th><td class="foot" colspan="8" id="xlFoot"></td></tr>';
    $('#xlbody').innerHTML = h;
    refreshXl();
  }
  function refreshXl() {
    const rep = st.report; if (!rep) return;
    $('#xlSub').textContent = rep.title_text; $('#xlH').textContent = rep.h_label; $('#xlFoot').textContent = rep.footnote;
    const trs = [...$('#xlbody').querySelectorAll('tr[data-i]')];
    st.rows.forEach((r, i) => {
      const tr = trs[i], f = rep.flags[i];
      tr.classList.toggle('gray', r.status !== 'done' && !r.touched);
      ['S'].concat(COLS.map((c) => c[0])).forEach((c) => {
        const td = tr.querySelector('td[data-c="' + c + '"]'), x = f[c];
        td.classList.remove('err', 'warn', 'note'); td.removeAttribute('title');
        if (x) { td.classList.add(x.lvl); td.title = x.msg; }
      });
    });
    $('#issues').innerHTML = rep.issues.map((x) => '<li><button type="button" data-i="' + x.row + '"><span class="lv ' + x.lvl + '">' + LV[x.lvl] + '</span><span>' + esc(x.text) + '</span></button></li>').join('');
    const miss = rep.missing;
    $('#sum').textContent = 'กรอกแล้ว ' + rep.filled + '/21 สถานี' + (miss.length ? ' — ยังขาด: ' + miss.slice(0, 4).join(', ') + (miss.length > 4 ? ' และอีก ' + (miss.length - 4) + ' สถานี' : '') : ' — ครบทุกสถานี');
    const c = rep.counts, w = c.warn + rep.global_warn;
    $('#chips').innerHTML = (c.err ? '<span class="chip err">ต้องแก้ ' + c.err + '</span>' : '') + (w ? '<span class="chip warn">เตือน ' + w + '</span>' : '') + (c.note ? '<span class="chip note">แจ้ง ' + c.note + '</span>' : '');
    $('#xlNext').disabled = c.err > 0;
    $('#xlWhy').textContent = c.err > 0 ? 'ยังมีช่องสีแดง ' + c.err + ' ช่อง แก้แล้วจึงไปบันทึกไฟล์ได้' : miss.length ? 'ไปต่อได้ แต่ยังขาด ' + miss.length + ' สถานี (แถวในไฟล์จะว่างไว้)' : 'พร้อมบันทึกไฟล์';
  }
  function editCell(el) {
    const r = st.rows[+el.closest('tr').dataset.i], c = el.dataset.col;
    r[c] = el.value; r.touched = true; if (c === 'F') r.fAuto = false;
    scheduleCheck(refreshXl);
  }

  /* ---------- ขั้น 3 บันทึกไฟล์ ---------- */
  async function renderSave() {
    await runCheck();
    const rep = st.report; if (!rep) return;
    $('#okbox').hidden = true; $('#saveErr').hidden = true;
    $('#sdate').value = rep.date;
    $('#bigdt').textContent = 'วันที่ ' + thaiDate(rep.date) + ' · ' + (rep.round != null ? pad(rep.round) + '.00 น.' : 'ยังไม่ทราบเวลา');
    $('#dtFrom').textContent = rep.latest
      ? 'ล่าสุดจากรหัสข่าว' + (rep.latest.count > 1 ? ' ' + rep.latest.count + ' สถานี' : 'ของ ' + rep.latest.from) + ' (' + rep.latest_text + ')'
      : 'ยังไม่มีรหัสข่าวที่บอกวัน/เวลา เลือกรอบเอง';
    $('#stime').value = rep.round != null ? pad(rep.round) + ':00' : '';
    $('#stimeHint').textContent = rep.round != null
      ? 'ตรงกับ ' + pad((rep.round - cfg.utc_offset + 24) % 24) + '.00 UTC · เลือกชั่วโมง ระบบใช้เฉพาะชั่วโมง (นาทีเป็น 00 เสมอ)'
      : 'เลือกชั่วโมง ระบบใช้เฉพาะชั่วโมง (นาทีเป็น 00 เสมอ)';
    if (!st.filenameEdited) $('#fname').value = rep.filename;
    $('#fnameReset').hidden = !st.filenameEdited;
    $('#saveSum').innerHTML = 'กรอกแล้ว ' + rep.filled + '/21 สถานี'
      + (rep.missing.length ? '<br><span class="hint">ยังขาด: ' + esc(rep.missing.join(', ')) + '</span>' : '')
      + '<br><span class="hint">คอลัมน์ H ในไฟล์: ' + esc(rep.h_label) + '</span>'
      + (rep.counts.warn ? '<br><span class="hint">คำเตือนที่ยังเหลือ ' + rep.counts.warn + ' รายการ (ตรวจได้ใน Excel จำลอง)</span>' : '');
    const blocked = rep.counts.err > 0 || rep.round == null || st.demo;
    $('#saveBtn').disabled = blocked;
    $('#saveWhy').textContent = st.demo ? 'โหมดตัวอย่างไม่บันทึกไฟล์ เพื่อไม่ให้ข้อมูลสมมติถูกนำไปใช้เป็นรายงานจริง'
      : rep.counts.err > 0 ? 'ยังมีช่องสีแดง ' + rep.counts.err + ' ช่อง กลับไปแก้ใน Excel จำลองก่อน'
      : rep.round == null ? 'เลือกรอบก่อนจึงจะบันทึกได้' : '';
  }
  async function saveFile() {
    const err = $('#saveErr'); err.hidden = true;
    let name = $('#fname').value.trim() || (st.report && st.report.filename) || 'รายงาน.xlsx';
    if (!/\.xlsx$/i.test(name)) name += '.xlsx';
    const fd = new FormData();
    fd.append('payload', JSON.stringify(checkPayload())); fd.append('filename', name);
    if (st.prevFile) fd.append('template', st.prevFile, st.prevFile.name);
    $('#saveBtn').disabled = true;
    try {
      const res = await api('/api/export', { method: 'POST', body: fd });
      const blob = await res.blob();
      const url = URL.createObjectURL(blob), a = document.createElement('a');
      a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10000);
      $('#okTxt').textContent = 'ไฟล์ «' + name + '» อยู่ในโฟลเดอร์ดาวน์โหลดของเบราว์เซอร์ ถ้าไม่เห็น ให้ดูที่ปุ่มดาวน์โหลดด้านบนของเบราว์เซอร์';
      $('#okbox').hidden = false; $('#okbox').scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    } catch (e) { err.textContent = e.message; err.hidden = false; }
    $('#saveBtn').disabled = false;
  }

  /* ---------- เริ่มข้อมูล ---------- */
  function fresh() {
    st.rows = cfg.stations.map(blankRow); st.cur = 0; st.dateOverride = null; st.roundOverride = null; st.filenameEdited = false;
    st.tab = 'st'; st.report = null; st.demo = false; st.prev = null; st.prevFile = null; st.ref = today();
    $('#prevFile').value = ''; renderPrevInfo();
  }
  function renderPrevInfo() {
    const info = $('#prevInfo'), clear = $('#clearPrev'); $('#prevErr').hidden = true;
    if (st.prev && st.prevFile) {
      const when = st.prev.date && st.prev.round != null ? ' · รอบ ' + pad(st.prev.round) + '.00 น. วันที่ ' + thaiDate(st.prev.date) : '';
      info.textContent = 'ใช้ไฟล์ «' + st.prevFile.name + '» เป็นต้นแบบ' + when;
      clear.hidden = false;
    } else {
      info.textContent = 'ไม่ได้เลือก ระบบจะใช้ไฟล์เปล่าที่มากับระบบ (เหมาะกับรอบแรกของวัน) รอบถัดไปเลือกไฟล์รอบก่อน เพื่อให้แสดงค่าฝนสะสมเดิมและเตือนเมื่อตัวเลขไม่ลงรอยกัน';
      clear.hidden = true;
    }
  }
  async function onPrevChosen() {
    const file = $('#prevFile').files[0]; if (!file) return;
    const fd = new FormData(); fd.append('file', file, file.name);
    const err = $('#prevErr'); err.hidden = true;
    try {
      const info = await getJson('/api/prev-file', { method: 'POST', body: fd });
      st.prev = info; st.prevFile = file; renderPrevInfo();
    } catch (e) { st.prev = null; st.prevFile = null; $('#prevFile').value = ''; renderPrevInfo(); err.textContent = e.message; err.hidden = false; }
  }
  async function startReal() {
    const keepPrev = st.prev, keepFile = st.prevFile;
    fresh(); st.prev = keepPrev; st.prevFile = keepFile; renderPrevInfo();
    go('work'); await showTab('st'); $('#raw').focus({ preventScroll: true });
  }
  async function startDemo() {
    try {
      const demo = await getJson('/api/demo');
      fresh(); st.demo = true; st.ref = demo.ref; st.prev = demo.prev; st.prevFile = null;
      await Promise.all(demo.stations.map(async (d) => {
        const r = st.rows.find((x) => x.code === d.code);
        if (d.skip) { r.status = 'skipped'; return; }
        r.raw = d.raw; r.G = d.G; r.H = d.H; r.status = 'done';
        applyDecoded(r, await postJson('/api/decode', { code: r.code, raw: r.raw }));
      }));
      go('work'); await runCheck(); await showTab('st');
    } catch (e) { toast(e.message); }
  }

  /* ---------- เหตุการณ์ ---------- */
  function wire() {
    $('#startBtn').addEventListener('click', startReal);
    $('#demoBtn').addEventListener('click', startDemo);
    $('#pickPrev').addEventListener('click', () => $('#prevFile').click());
    $('#prevFile').addEventListener('change', onPrevChosen);
    $('#clearPrev').addEventListener('click', () => { st.prev = null; st.prevFile = null; $('#prevFile').value = ''; renderPrevInfo(); });
    $('#tabSt').addEventListener('click', () => showTab('st'));
    $('#tabXl').addEventListener('click', () => showTab('xl'));
    $('#toXlSide').addEventListener('click', () => showTab('xl'));
    $('#backBtn').addEventListener('click', () => goStation(st.cur - 1));
    $('#skipBtn').addEventListener('click', skipStation);
    $('#nextBtn').addEventListener('click', nextStation);
    $('#chips21').addEventListener('click', (e) => { const b = e.target.closest('button'); if (b) goStation(+b.dataset.k); });
    $('#raw').addEventListener('input', onRawInput);
    ['F', 'G', 'H'].forEach((c) => {
      const el = $('#f' + c);
      el.addEventListener('input', () => { const r = cur(); r[c] = el.value; if (c === 'F') r.fAuto = false; scheduleCheck(renderStationLive); });
      el.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); if (c === 'H') nextStation(); else $(c === 'F' ? '#fG' : '#fH').focus(); } });
    });
    $('#exBody').addEventListener('click', (e) => {
      const b = e.target.closest('.tok'); if (!b) return;
      const c = document.getElementById('exc' + b.dataset.k); if (!c) return;
      c.scrollIntoView({ block: 'center', behavior: 'smooth' }); c.classList.remove('flash'); void c.offsetWidth; c.classList.add('flash');
    });
    $('#xlbody').addEventListener('input', (e) => { const el = e.target.closest('[data-col]'); if (el && el.tagName !== 'SELECT') editCell(el); });
    $('#xlbody').addEventListener('change', (e) => { const el = e.target.closest('select[data-col]'); if (el) editCell(el); });
    $('#issues').addEventListener('click', (e) => {
      const b = e.target.closest('button'); if (!b) return; const i = +b.dataset.i; if (i < 0) return;
      const tr = $('#xlbody').querySelector('tr[data-i="' + i + '"]');
      tr.scrollIntoView({ block: 'center', behavior: 'smooth' }); tr.classList.remove('flash'); void tr.offsetWidth; tr.classList.add('flash');
    });
    $('#xlBack').addEventListener('click', () => showTab('st'));
    $('#xlNext').addEventListener('click', async () => { go('save'); await renderSave(); });
    $('#svBack').addEventListener('click', async () => { go('work'); await showTab('xl'); });
    $('#sdate').addEventListener('change', async (e) => { if (!e.target.value) return; st.dateOverride = e.target.value; await renderSave(); });
    $('#stime').addEventListener('change', async (e) => {
      const m = /^(\d{1,2}):/.exec(e.target.value); if (!m) return;
      st.roundOverride = +m[1]; await renderSave();
    });
    $('#fname').addEventListener('input', () => { st.filenameEdited = true; $('#fnameReset').hidden = false; });
    $('#fnameReset').addEventListener('click', async () => { st.filenameEdited = false; await renderSave(); });
    $('#saveBtn').addEventListener('click', saveFile);
    $('#newRound').addEventListener('click', () => { fresh(); go('start'); });
  }
  function renderReference() {
    const t = (cap, rows) => '<table class="reftbl"><caption>' + cap + '</caption>' + rows.map((r) => '<tr><td>' + esc(r[0]) + '</td><td>' + esc(r[1]) + '</td></tr>').join('') + '</table>';
    const ref = cfg.reference;
    $('#refBody').innerHTML = t('ทิศลม (dd ×10 = องศา)', ref.dir) + t('กำลังลม (นอต)', ref.spd) + t('ท้องฟ้า (N)', ref.sky) + t('ลักษณะอากาศ (ww ตั้งแต่ 04 ขึ้นไป)', ref.ww);
  }

  async function init() {
    try { cfg = await getJson('/api/config'); }
    catch (e) { toast(e.message); $('#startBtn').disabled = true; $('#demoBtn').disabled = true; return; }
    st.rows = cfg.stations.map(blankRow);
    renderReference(); wire(); go('start');
    if (location.hash === '#demo') startDemo();
  }
  init();
})();
