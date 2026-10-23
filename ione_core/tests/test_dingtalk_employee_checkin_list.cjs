// Run in an isolated JS context, without a browser or Frappe writes.
const fs = require("node:fs");
const vm = require("node:vm");
const assert = require("node:assert/strict");
let nativeOnload = 0, nativeRefresh = 0, nativeRender = 0, dataRefresh = 0;
let calls = [], buttons = [], indicators = [];
let timers = [], selected = false;
let failNextContext = false;
function deferred(promise) {
  return { then(...handlers) { return deferred(promise.then(...handlers)); },
    catch(handler) { return deferred(promise.catch(handler)); } };
}
const settings = {
  add_fields: ["offshift"],
  onload() { nativeOnload++; }, refresh() { nativeRefresh++; },
  get_indicator(doc) { if (doc.offshift) return ["Off-Shift", "yellow", "offshift,=,1"]; },
};
const listview = {
  data: [{ name: "visible-checkin", modified: "2026-10-22 16:00:00" }],
  render_list() { nativeRender++; }, refresh() { dataRefresh++; },
  checked_docnames: new Set(), get_checked_items() { return selected ? [{name: "visible-checkin"}] : []; },
  page: { add_inner_button(label, fn) { buttons.push([label, fn]); },
    set_indicator(...args) { indicators.push(args); } },
};
const frappe = {
  listview_settings: { "Employee Checkin": settings },
  get_route: () => ["List", "Employee Checkin"],
  user: { has_role: (role) => role === "HR User" },
  utils: { escape_html: (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;") },
  call(options) {
    calls.push(options);
    if (options.method.endsWith("get_checkin_context") && failNextContext) {
      failNextContext = false;
      return deferred(Promise.reject(new Error("Temporary context lookup failure")));
    }
    return deferred(Promise.resolve({ message: options.method.endsWith("get_checkin_context")
      ? { "visible-checkin": { department: "测试教学部", shift: "上午班" } }
      : { state: "connected", pending: 0, reconcile_failed: false, settlement_failed: false } }));
  },
  msgprint() {},
};
const context = { frappe, cur_list: listview, document: { hidden: false }, __: (s) => s,
  setTimeout: (fn) => { timers.push(fn); return timers.length; }, console, Map, Date, Number, JSON, Set };
vm.runInNewContext(fs.readFileSync(require("node:path").join(__dirname, "..", "public", "js", "dingtalk_employee_checkin_list.js"), "utf8"), context);
(async () => {
  settings.onload(listview);
  listview.render_list();
  await new Promise(setImmediate);
  assert.equal(nativeOnload, 1);
  assert.equal(nativeRender, 2); // original render plus context-only redraw
  assert.equal(dataRefresh, 0);
  assert.equal(buttons.length, 1);
  assert.deepEqual(Array.from(settings.get_indicator({ offshift: true })), ["Off-Shift", "yellow", "offshift,=,1"]);
  assert.equal(settings.get_indicator({ attendance: "ATT-1" })[0], "已生成考勤");
  assert.equal(settings.get_indicator({ shift: "上午班" })[0], "已记录，待考勤");
  assert.equal(settings.formatters.employee_name("教师甲", {}, { name: "visible-checkin" }), "教师甲 · 测试教学部 · 上午班");
  settings.refresh(listview);
  assert.equal(nativeRefresh, 1);
  assert.equal(calls.length, 2); // context cache avoids repeated requests
  assert.equal(indicators.length, 1);
  assert(settings.add_fields.includes("shift"));
  assert(!calls.some((c) => c.method.includes("get_all")));
  selected = true;
  await timers.shift()();
  assert.equal(dataRefresh, 0); // never disturb selected native list rows
  selected = false;
  await timers.shift()();
  assert.equal(dataRefresh, 1); // socket-recovery fallback still uses native list refresh
  assert.equal(listview._dingtalk_context_loading, false);
  failNextContext = true;
  listview.data[0].modified = "2026-10-22 17:59:00";
  listview.render_list();
  await new Promise(setImmediate);
  assert.equal(listview._dingtalk_context_loading, false);
  listview.render_list();
  await new Promise(setImmediate);
  assert.equal(listview._dingtalk_context_loading, false);
  assert.equal(settings.formatters.employee_name("教师甲", {}, { name: "visible-checkin" }), "教师甲 · 测试教学部 · 上午班");
  console.log("PASS: native actions, off-shift indicator, permission-query context, status, throttling and selected rows preserved");
})().catch((error) => { console.error(error); process.exitCode = 1; });
