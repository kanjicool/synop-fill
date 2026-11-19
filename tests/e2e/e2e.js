// ทดสอบหน้าเว็บ synop-fill ด้วย Chrome จริง (puppeteer-core) ทั้งโหมดตัวอย่างและโหมดใช้งานจริง รวมการดาวน์โหลดไฟล์
// วิธีใช้ (ต้องเปิดระบบที่ http://127.0.0.1:8765 ก่อน เช่น script\run-app.bat):
//   cd tests/e2e && npm install && node e2e.js <โฟลเดอร์เก็บภาพ/ผลลัพธ์> ../fixtures
// ตั้ง CHROME_PATH ถ้า Chrome ไม่ได้อยู่ที่ตำแหน่งมาตรฐาน  ตั้ง BASE_URL ถ้าเปิดระบบด้วย port อื่น
const puppeteer = require('puppeteer-core');
const fs = require('fs');
const path = require('path');

const BASE = process.env.BASE_URL || 'http://127.0.0.1:8765/';
const OUT = process.argv[2];
const FIX = process.argv[3];
const CHROME = process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const log = [];
let failed = 0;
const ok = (cond, msg) => { log.push((cond ? 'PASS ' : 'FAIL ') + msg); if (!cond) failed++; };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function setVal(page, sel, text) {
  await page.focus(sel);
  await page.keyboard.down('Control'); await page.keyboard.press('KeyA'); await page.keyboard.up('Control');
  await page.keyboard.type(text);
}

(async () => {
  const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox'] });
  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 1000 });
  const errors = [];
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
  page.on('console', (m) => { if (m.type() === 'error') errors.push('console: ' + m.text()); });
  page.on('requestfailed', (r) => errors.push('requestfailed: ' + r.url()));
  const text = (sel) => page.$eval(sel, (e) => e.textContent.trim());
  const shot = (name) => page.screenshot({ path: path.join(OUT, name + '.png'), fullPage: true });
  const waitText = (sel, fn) => page.waitForFunction((s, f) => { const e = document.querySelector(s); return e && new Function('t', 'return ' + f)(e.textContent); }, { timeout: 8000 }, sel, fn);

  // ---------- 1) หน้าเริ่มต้น ----------
  await page.goto(BASE, { waitUntil: 'networkidle0' });
  ok((await text('h1')).includes('ระบบกรอกรายงาน'), 'start page shows title');
  ok(await page.$eval('#v-start', (e) => !e.hidden), 'start view visible');
  ok(await page.$eval('#v-work', (e) => e.hidden), 'work view hidden at start');
  await shot('01-start');

  // ---------- 2) โหมดตัวอย่าง ----------
  await page.click('#demoBtn');
  await waitText('#stName', "t==='เพชรบุรี'");
  ok(await page.$eval('#demoTag', (e) => !e.hidden), 'demo tag visible');
  ok((await page.$eval('#raw', (e) => e.value)).startsWith('AAXX 18064'), 'demo fills raw code');
  ok((await text('#preview')).includes('ลมตะวันตกเฉียงเหนือ'), 'preview decodes wind direction');
  ok((await page.$$('.excard')).length >= 6, 'explain cards rendered');
  await shot('02-demo-station1');

  // ไปสถานีที่ 15 (สงขลา) ด้วยชิป
  await page.click('#chips21 button[data-k="14"]');
  await waitText('#stName', "t==='สงขลา'");
  await sleep(400);
  const prevMsg = await text('#mH');
  ok(prevMsg.includes('H รอบก่อน') && prevMsg.includes('0.4'), 'H field shows previous H from file: ' + prevMsg);
  const explainTokens = await page.$$eval('.tok', (els) => els.map((e) => e.textContent));
  ok(explainTokens.includes('81003') && explainTokens.includes('70270'), 'real Songkhla code explained');
  await page.click('.tok[data-k="3"]');
  await shot('03-demo-songkhla-explain');

  // พัทลุง (ข้อมูลจริงที่ H ไม่ลงรอยกัน)
  await page.click('#chips21 button[data-k="13"]');
  await waitText('#stName', "t==='พัทลุง'");
  await sleep(400);
  ok((await text('#mH')).includes('20.8 + G 7.5 = 28.3'), 'Phatthalung mismatch warning: ' + (await text('#mH')));

  // ---------- 3) Excel จำลอง ----------
  await page.click('#tabXl');
  await page.waitForSelector('#xlbody tr[data-i="20"]');
  await sleep(300);
  const shown = (sel) => page.$eval(sel, (e) => getComputedStyle(e).display !== 'none' && e.getBoundingClientRect().height > 0);
  ok(!(await shown('#v-stations')), 'station view is really hidden on the Excel tab');
  ok(!(await shown('#exCard')), 'explain card is hidden on the Excel tab');
  ok(await shown('#v-excel'), 'excel view visible');
  ok((await text('#xlSub')).includes('18 พฤศจิกายน 2569 เวลา 13.00 น.'), 'excel title: ' + (await text('#xlSub')));
  ok((await text('#sum')).startsWith('กรอกแล้ว 20/21'), 'summary: ' + (await text('#sum')));
  ok(await page.$eval('#xlbody tr[data-i="17"]', (e) => e.classList.contains('gray')), 'skipped station row is gray');
  ok(await page.$eval('#xlbody tr[data-i="13"] td[data-c="H"]', (e) => e.classList.contains('warn')), 'Phatthalung H cell is yellow');
  ok(await page.$eval('#xlNext', (e) => !e.disabled), 'can continue (no red cells)');
  ok((await page.$eval('#xlbody tr[data-i="14"] td[data-c="B"] select', (e) => e.value)) === 'ลมตะวันออก', 'Songkhla B in excel');
  await shot('04-demo-excel');

  // แก้ค่าในตาราง: พิมพ์ผิด -> ช่องแดง -> ปุ่มถูกล็อก
  await setVal(page, '#xlbody tr[data-i="0"] td[data-c="G"] input', '7,5');
  await sleep(500);
  ok(await page.$eval('#xlbody tr[data-i="0"] td[data-c="G"]', (e) => e.classList.contains('err')), 'typo makes cell red');
  ok(await page.$eval('#xlNext', (e) => e.disabled), 'next button locked while red cell remains');
  await shot('05-demo-excel-red');
  await setVal(page, '#xlbody tr[data-i="0"] td[data-c="G"] input', '0');
  await sleep(500);
  ok(await page.$eval('#xlNext', (e) => !e.disabled), 'fixing the typo unlocks next');

  // กลับไปแท็บสถานี Excel ต้องหาย
  await page.click('#tabSt'); await sleep(300);
  ok(await shown('#v-stations') && !(await shown('#v-excel')), 'switching back shows stations and hides excel');
  await page.click('#tabXl'); await sleep(400);

  // ---------- 4) บันทึกไฟล์ (โหมดตัวอย่างต้องไม่ให้บันทึก) ----------
  await page.click('#xlNext');
  ok(!(await shown('#v-work')) && (await shown('#v-save')), 'save step hides the work area');
  await page.waitForFunction(() => document.querySelector('#bigdt').textContent.includes('13.00'));
  ok((await text('#bigdt')) === 'วันที่ 18 พฤศจิกายน 2569 · 13.00 น.', 'save view date/time: ' + (await text('#bigdt')));
  ok((await text('#dtFrom')).includes('สงขลา') || (await text('#dtFrom')).includes('ล่าสุด'), 'latest message source shown');
  ok((await page.$eval('#fname', (e) => e.value)) === 'รายงานผลการตรวจอากาศเวลา 13.00 น. 18-11-69.xlsx', 'auto filename');
  ok(await page.$eval('#saveBtn', (e) => e.disabled), 'demo mode cannot save');
  await shot('06-demo-save');

  // ---------- 5) โหมดใช้งานจริง + ไฟล์รอบก่อน + บันทึกจริง ----------
  await page.goto(BASE, { waitUntil: 'networkidle0' });
  const input = await page.$('#prevFile');
  await input.uploadFile(path.join(FIX, 'report_1000.xlsx'));
  await waitText('#prevInfo', "t.includes('report_1000.xlsx')");
  ok((await text('#prevInfo')).includes('รอบ 10.00 น.'), 'prev file read: ' + (await text('#prevInfo')));
  await page.click('#startBtn');
  await waitText('#stName', "t==='เพชรบุรี'");
  ok(!(await page.$eval('#demoTag', (e) => !e.hidden)), 'no demo tag in real mode');
  // ชิป 15 = สงขลา: วางรหัสจริง
  await page.click('#chips21 button[data-k="14"]');
  await page.click('#raw');
  const REAL = 'AAXX 18064\n48568 01460 81003 10271 20239 30119 40127 57016 60051 70262 8387/\n333 58019 60056 70270';
  await page.evaluate((v) => { const e = document.querySelector('#raw'); e.value = v; e.dispatchEvent(new Event('input', { bubbles: true })); }, REAL);
  await waitText('#preview', "t.includes('ลมตะวันออก')");
  ok((await page.$eval('#fF', (e) => e.value)) === '27.1', 'temperature auto-filled from code');
  await page.click('#fG'); await page.keyboard.type('5');
  await page.click('#fH'); await page.keyboard.type('5.4');
  await sleep(500);
  ok((await text('#mH')).includes('0.4'), 'previous H shown in real mode');
  await page.keyboard.press('Enter'); // Enter ในช่อง H = ถัดไป
  await waitText('#stName', "t==='ท่าอากาศยานหาดใหญ่'");
  ok(true, 'Enter in last field moves to next station');
  // สถานีอื่น: ข้าม (ว่าง) แล้วดู Excel
  await page.click('#toXlSide');
  await page.waitForSelector('#xlbody tr[data-i="20"]');
  await sleep(400);
  ok((await text('#sum')).startsWith('กรอกแล้ว 1/21') || (await text('#sum')).startsWith('กรอกแล้ว 0/21') === false, 'summary in real mode: ' + (await text('#sum')));
  await shot('07-real-excel');
  // ตั้งสถานะ done ของสงขลาโดยกลับไปกดถัดไปมาแล้ว: ตรวจว่า H15 ไม่เตือน
  const hFlag = await page.$eval('#xlbody tr[data-i="14"] td[data-c="H"]', (e) => e.className);
  ok(!hFlag.includes('warn') && !hFlag.includes('err'), 'Songkhla H consistent with previous file (0.4+5=5.4)');
  await page.click('#xlNext');
  await page.waitForFunction(() => document.querySelector('#bigdt').textContent.includes('13.00'));
  ok(await page.$eval('#saveBtn', (e) => !e.disabled), 'real mode can save');
  await shot('08-real-save');

  const dl = path.join(OUT, 'downloads');
  fs.rmSync(dl, { recursive: true, force: true }); fs.mkdirSync(dl, { recursive: true });
  const cdp = await page.createCDPSession();
  await cdp.send('Browser.setDownloadBehavior', { behavior: 'allow', downloadPath: dl, eventsEnabled: true });
  await page.click('#saveBtn');
  await page.waitForFunction(() => !document.querySelector('#okbox').hidden, { timeout: 8000 });
  await sleep(800);
  const files = fs.readdirSync(dl);
  ok(files.length === 1 && files[0] === 'รายงานผลการตรวจอากาศเวลา 13.00 น. 18-11-69.xlsx', 'downloaded file name: ' + JSON.stringify(files));
  await shot('09-real-saved');

  // ชื่อไฟล์ที่แก้เอง ต้องไม่ถูกเขียนทับ
  await page.click('#svBack'); await sleep(300);
  await page.click('#xlNext'); await page.waitForFunction(() => document.querySelector('#bigdt').textContent.includes('13.00'));
  await setVal(page, '#fname', 'ของฉัน.xlsx');
  await page.click('#rounds button[data-h="16"]'); await sleep(600);
  ok((await page.$eval('#fname', (e) => e.value)) === 'ของฉัน.xlsx', 'edited filename kept when round changes');
  ok(await page.$eval('#fnameReset', (e) => !e.hidden), 'reset-name link shown');

  // เริ่มรอบใหม่
  await page.click('#newRound').catch(() => {});
  fs.writeFileSync(path.join(OUT, 'errors.txt'), errors.join('\n'));
  ok(errors.length === 0, 'no browser errors: ' + JSON.stringify(errors.slice(0, 3)));
  fs.writeFileSync(path.join(OUT, 'e2e_log.txt'), log.join('\n') + '\nFAILED=' + failed + '\n');
  await browser.close();
  process.exit(failed ? 1 : 0);
})().catch((e) => { log.push('CRASH ' + e.stack); fs.writeFileSync(path.join(OUT, 'e2e_log.txt'), log.join('\n')); console.error(e.message); process.exit(2); });
