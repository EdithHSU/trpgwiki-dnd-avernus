/**
 * 墜入阿弗納斯 Wiki：待確認名詞的共用答案表（Google Apps Script）
 *
 * 網站上的表單頁（docs/confirm/index.html）把答案送到這裡，存進這份 Google 試算表。
 * 團員不用登入，只要知道通關密語；名字相同（不分大小寫、全半形、前後空白）視為同一人，
 * 同一人對同一題只留一列，新答案覆蓋舊答案。
 *
 * 安裝（只要做一次）：
 *   1. 在 Google 雲端硬碟新增一份試算表（名稱隨意，例如「阿弗納斯 待確認名詞」）。
 *   2. 試算表選單「擴充功能 → Apps Script」，把編輯器裡原本的內容全部刪掉，貼上本檔全文，按儲存。
 *   3. 左側「專案設定（齒輪）」→ 最下方「指令碼屬性」→ 新增屬性：
 *        屬性 PASSPHRASE，值填通關密語（之後要換密語，改這裡就好，不用重新部署）。
 *   4. 右上角「部署 → 新增部署作業」→ 類型選「網頁應用程式」：
 *        執行身分：我；誰可以存取：所有人。按「部署」，依提示授權。
 *   5. 複製「網頁應用程式」網址（https://script.google.com/macros/s/…/exec），
 *      填進 docs/confirm/index.html 的 API_URL。
 *   之後若修改了本檔，要用「部署 → 管理部署作業 → 編輯（鉛筆）→ 版本：新版本」更新，網址不變。
 *
 * 試算表會自動建立「答案」工作表；可以直接在試算表裡看、改或刪答案，也可以「檔案 → 下載」。
 */

const SHEET_NAME = '答案';
const HEADERS = ['name_key', 'name', 'id', 'answer', 'who', 'note', 'status', 'updated'];
const MAX = { name: 30, answer: 200, who: 10, note: 1000, items: 300 };

function doGet() {
  return ContentService.createTextOutput('墜入阿弗納斯 Wiki 待確認名詞：請從表單頁面填寫。');
}

function doPost(e) {
  let req;
  try { req = JSON.parse(e.postData.contents); } catch (err) { return json_({ ok: false, error: 'bad_request' }); }
  const pass = PropertiesService.getScriptProperties().getProperty('PASSPHRASE');
  if (!pass) return json_({ ok: false, error: 'not_configured' });
  if (String(req.key || '') !== pass) return json_({ ok: false, error: 'bad_key' });

  const lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    const sheet = sheet_();
    if (req.action === 'save') {
      const err = save_(sheet, req);
      if (err) return json_({ ok: false, error: err });
    }
    return json_({ ok: true, rows: read_(sheet) });
  } finally {
    lock.releaseLock();
  }
}

// 名字相同就算同一人：統一全半形、空白與大小寫（表單頁用一樣的規則）
function cleanName_(s) { return String(s == null ? '' : s).normalize('NFKC').trim().replace(/\s+/g, ' ').slice(0, MAX.name); }
function nameKey_(s) { return cleanName_(s).toLowerCase(); }
function clean_(v, max) { return String(v == null ? '' : v).replace(/[\u0000-\u0008\u000b-\u001f]/g, ' ').trim().slice(0, max); }
// 開頭是 = + - @ 的字串加上 ' ，避免被試算表當成公式
function safe_(v) { return /^[=+\-@]/.test(v) ? "'" + v : v; }

function sheet_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName(SHEET_NAME);
  if (!sheet) {
    sheet = ss.insertSheet(SHEET_NAME);
    sheet.getRange(1, 1, 1, HEADERS.length).setValues([HEADERS]).setFontWeight('bold');
    sheet.setFrozenRows(1);
    sheet.getRange('A:H').setNumberFormat('@');   // 全部當文字，避免「0039」變成數字
  }
  return sheet;
}

function save_(sheet, req) {
  const name = cleanName_(req.name);
  const key = nameKey_(name);
  if (!key) return 'bad_name';
  const items = Array.isArray(req.items) ? req.items.slice(0, MAX.items) : [];

  const data = sheet.getDataRange().getDisplayValues();
  const rowOf = {};   // name_key|id → 試算表列號
  for (let r = 1; r < data.length; r++) rowOf[data[r][0] + '|' + data[r][2]] = r + 1;

  const now = new Date().toISOString();
  const toDelete = [];
  items.forEach(function (it) {
    const id = String(it && it.id || '');
    if (!/^[a-z0-9-]{1,60}$/.test(id)) return;
    const answer = clean_(it.answer, MAX.answer);
    const who = (Array.isArray(it.who) ? it.who : []).map(function (w) { return clean_(w, MAX.who); })
      .filter(String).slice(0, 8).join('、');
    const note = clean_(it.note, MAX.note);
    const status = it.status === 'confirmed' || it.status === 'unsure' ? it.status : '';
    const row = rowOf[key + '|' + id];
    if (!answer && !who && !note && !status) {   // 清除：刪掉這一列
      if (row) toDelete.push(row);
      return;
    }
    const values = [key, name, id, answer, who, note, status, now].map(safe_);
    if (row) sheet.getRange(row, 1, 1, HEADERS.length).setValues([values]);
    else { sheet.appendRow(values); rowOf[key + '|' + id] = sheet.getLastRow(); }
  });
  toDelete.sort(function (a, b) { return b - a; }).forEach(function (r) { sheet.deleteRow(r); });

  // 同一人的名字統一成最新的寫法（例如這次用全形、上次用半形）
  const all = sheet.getDataRange().getDisplayValues();
  for (let r = 1; r < all.length; r++) {
    if (all[r][0] === key && all[r][1] !== name) sheet.getRange(r + 1, 2).setValue(safe_(name));
  }
  return '';
}

function read_(sheet) {
  const data = sheet.getDataRange().getDisplayValues();
  const rows = [];
  for (let r = 1; r < data.length; r++) {
    const d = data[r];
    if (!d[0] || !d[2]) continue;
    rows.push({
      key: d[0], name: d[1], id: d[2], answer: d[3],
      who: d[4] ? d[4].split('、') : [], note: d[5], status: d[6], updated: d[7],
    });
  }
  return rows;
}

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
