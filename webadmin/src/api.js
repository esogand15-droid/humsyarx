// 🖥️ کلاینت API وب‌ادمین — same-origin با کوکی HttpOnly (wa_session)
// هیچ توکن در localStorage ذخیره نمی‌شود.

async function req(path, { method = 'GET', body, form } = {}) {
  const opt = { method, credentials: 'include', headers: {} };
  if (form) opt.body = form;
  else if (body !== undefined) {
    opt.headers['Content-Type'] = 'application/json';
    opt.body = JSON.stringify(body);
  }
  const r = await fetch(path, opt);
  if (r.status === 401 && !path.includes('/auth/')) {
    window.dispatchEvent(new Event('wa:unauthorized'));
  }
  let data = null;
  try { data = await r.json(); } catch { /* پاسخ خالی */ }
  if (!r.ok) {
    const e = new Error((data && data.detail) || `خطا (${r.status})`);
    e.status = r.status;
    throw e;
  }
  return data;
}

export const api = {
  // ── auth ──
  requestCode: (identifier) => req('/api/web-admin/auth/request-code', { method: 'POST', body: { identifier } }),
  verify: (identifier, code) => req('/api/web-admin/auth/verify', { method: 'POST', body: { identifier, code } }),
  logout: () => req('/api/web-admin/auth/logout', { method: 'POST' }),
  me: () => req('/api/web-admin/me'),
  overview: () => req('/api/web-admin/overview'),
  // ── users (WA سرورساید) ──
  users: (p) => req('/api/web-admin/users?' + new URLSearchParams(Object.entries(p).filter(([, v]) => v))),
  // 🌊 موج Export — صفحه‌بندی خودکار برای خروجی کامل (سقف ۶۰ صفحه × ۱۰۰ = ۶هزار)
  usersAll: async (p = {}) => {
    const out = [];
    for (let pg = 1; pg <= 60; pg++) {
      const r = await api.users({ ...p, page: pg, per_page: 100 });
      const us = r.users || [];
      out.push(...us);
      if (pg >= (r.pages || 1) || !us.length) break;
    }
    return out;
  },
  usersBulk: (action, ids, value) => req('/api/web-admin/users/bulk', { method: 'POST', body: { action, ids, value } }),
  userDetail: (uid) => req(`/api/admin/users/${uid}`),
  userPatch: (uid, body) => req(`/api/admin/users/${uid}`, { method: 'PATCH', body }),
  userAction: (uid, act) => req(`/api/admin/users/${uid}/${act}`, { method: 'POST' }),
  // ── 🌊 WA2 core ──
  attention: () => req('/api/web-admin/attention'),
  activity: (limit = 40) => req(`/api/web-admin/activity?limit=${limit}`),
  waSearch: (q) => req('/api/web-admin/search?q=' + encodeURIComponent(q)),
  savedFilters: (scope) => req('/api/web-admin/saved-filters' + (scope ? `?scope=${scope}` : '')),
  saveFilter: (body) => req('/api/web-admin/saved-filters', { method: 'POST', body }),
  delFilter: (id) => req(`/api/web-admin/saved-filters/${id}`, { method: 'DELETE' }),
  user360: (uid) => req(`/api/web-admin/users/${uid}/360`),
  ticketsBulk: (action, ids) => req('/api/web-admin/tickets/bulk', { method: 'POST', body: { action, ids } }),
  questionsBulk: (action, ids) => req('/api/web-admin/questions/bulk', { method: 'POST', body: { action, ids } }),
  settingsCenter: () => req('/api/web-admin/settings/center'),
  patchSetting: (key, value) => req(`/api/web-admin/settings/center/${encodeURIComponent(key)}`, { method: 'PATCH', body: { value } }),
  exams: (status) => req('/api/web-admin/exams' + (status ? `?status=${status}` : '')),
  examCreate: (body) => req('/api/web-admin/exams', { method: 'POST', body }),
  examUpdate: (id, body) => req(`/api/web-admin/exams/${id}`, { method: 'PATCH', body }),
  examDelete: (id) => req(`/api/web-admin/exams/${id}`, { method: 'DELETE' }),
  examStats: () => req('/api/web-admin/exams/stats'),
  // 🌊 موج Analytics-Filters — بازه‌ی روزانه (۷ تا ۹۰)
  waAnalytics: (days) => req('/api/web-admin/wa-analytics' + (days ? `?days=${days}` : '')),
  notifRuns: (job) => req('/api/web-admin/notif/runs' + (job ? `?job_name=${job}` : '')),
  notifRetry: (id) => req(`/api/web-admin/notif/runs/${id}/retry`, { method: 'POST' }),
  // ── 🌊 WA2.1 Content Command Center ──
  contentTree: (intake) => req('/api/web-admin/content/tree' + (intake ? `?intake=${encodeURIComponent(intake)}` : '')),
  dupSession: (sid) => req(`/api/web-admin/content/sessions/${sid}/duplicate`, { method: 'POST' }),
  sessionsBulk: (body) => req('/api/web-admin/content/sessions/bulk', { method: 'POST', body }),
  itemsBulk: (body) => req('/api/web-admin/content/items/bulk', { method: 'POST', body }),
  caSessionContent: (sid) => req(`/api/content/basic-science/sessions/${sid}/content`),
  caAddContent: (sid, form) => req(`/api/content/basic-science/sessions/${sid}/content`, { method: 'POST', form }),
  caDelContent: (cid) => req(`/api/content/basic-science/content/${cid}`, { method: 'DELETE' }),
  caAddSession: (lid, body) => req(`/api/content/basic-science/lessons/${lid}/sessions`, { method: 'POST', body }),
  caDelSession: (sid) => req(`/api/content/basic-science/sessions/${sid}`, { method: 'DELETE' }),
  caForkSession: (sid, intake) => req(`/api/content/basic-science/sessions/${sid}/fork?intake=${encodeURIComponent(intake)}`, { method: 'POST' }),
  caUnforkSession: (sid) => req(`/api/content/basic-science/sessions/${sid}/fork`, { method: 'DELETE' }),
  caAddLesson: (body) => req('/api/content/basic-science/lessons', { method: 'POST', body }),
  caDelLesson: (lid) => req(`/api/content/basic-science/lessons/${lid}`, { method: 'DELETE' }),
  caReports: (status) => req('/api/content/reports' + (status ? `?status=${status}` : '')),
  caReportStatus: (rid, status) => req(`/api/content/reports/${rid}/status`, { method: 'POST', body: { status } }),
  // ── admin panel (owner) ──
  stats: () => req('/api/admin/stats'),
  botStatus: () => req('/api/admin/bot-status'),
  analytics: (days) => req('/api/admin/analytics' + (days ? `?days=${days}` : '')),
  tickets: (status) => req('/api/admin/tickets' + (status ? `?status=${status}` : '')),
  ticket: (tid) => req(`/api/admin/tickets/${tid}`),
  ticketReply: (tid, text) => req(`/api/admin/tickets/${tid}/reply`, { method: 'POST', body: { message: text } }),
  ticketClose: (tid) => req(`/api/admin/tickets/${tid}/close`, { method: 'POST' }),
  ticketReopen: (tid) => req(`/api/admin/tickets/${tid}/reopen`, { method: 'POST' }),
  broadcast: (body) => req('/api/admin/broadcast', { method: 'POST', body }),
  broadcastPreview: (body) => req('/api/admin/broadcast/preview', { method: 'POST', body }),
  broadcastHistory: () => req('/api/admin/broadcast/history'),
  // 🌊 موج Notif-Scheduled — مدیریت ارسال‌های زمان‌دارِ در انتظار (سطح مالک)
  broadcastScheduled: () => req('/api/admin/broadcast/scheduled'),
  broadcastCancel: (text, created_at) =>
    req('/api/admin/broadcast/cancel', { method: 'POST', body: { text, created_at } }),
  auditLogs: (p) => req('/api/admin/audit-logs?' + new URLSearchParams(Object.entries(p).filter(([, v]) => v))),
  settings: () => req('/api/admin/settings'),
  patchSettings: (body) => req('/api/admin/settings', { method: 'PATCH', body }),
  backup: () => req('/api/admin/backup', { method: 'POST' }),
  // 🌊 موج Export — درخواست خروجی اکسل کامل (ربات فایل را در گفت‌وگوی ادمین می‌فرستد)
  exportExcel: () => req('/api/admin/export/excel', { method: 'POST' }),
  intakes: () => req('/api/admin/intakes'),
  pendingUsers: () => req('/api/admin/users/pending'),
  // ── rbAC ──
  roles: () => req('/api/admin/rbac/roles'),
  perms: () => req('/api/admin/rbac/permissions'),
  createRole: (body) => req('/api/admin/rbac/roles', { method: 'POST', body }),
  patchRole: (k, body) => req(`/api/admin/rbac/roles/${k}`, { method: 'PATCH', body }),
  deleteRole: (k) => req(`/api/admin/rbac/roles/${k}`, { method: 'DELETE' }),
  roleOf: (uid) => req(`/api/admin/rbac/users/${uid}`),
  // ── subscription admin ──
  subOverview: () => req('/api/subscription-admin/overview'),
  subPayments: (p) => req('/api/subscription-admin/payments?' + new URLSearchParams(p || {})),
  subPaymentDecision: (pid, approved, note = '') =>
    req(`/api/subscription-admin/payments/${pid}/decision`, { method: 'POST', body: { approved, note } }),
  // 🌊 W-Design — منبع تصویر رسید (سشن HttpOnly خودش ضمیمه‌ی درخواست img می‌شود)
  subReceiptSrc: (pid) => `/api/subscription-admin/payments/${pid}/receipt`,
  discounts: () => req('/api/subscription-admin/discounts'),
  // ── content (scope-aware) ──
  caIntakes: () => req('/api/content/intakes'),
  caOverview: (intake) => req('/api/content/overview' + (intake ? `?intake=${intake}` : '')),
  caQuestionsPending: () => req('/api/content/questions/pending'),
  caQuestionApprove: (qid) => req(`/api/content/questions/${qid}/approve`, { method: 'POST' }),
  caQuestionReject: (qid) => req(`/api/content/questions/${qid}/reject`, { method: 'POST' }),
  // ── 🌊 WA3 — مدیریت کامل کاربر (permission-based، آینه‌ی دقیق ربات) ──
  waUserMessage: (uid, text) => req(`/api/web-admin/users/${uid}/message`, { method: 'POST', body: { text } }),
  waUserAction: (uid, action, reason = '') => req(`/api/web-admin/users/${uid}/action`, { method: 'POST', body: { action, reason } }),
  waUserPatch: (uid, body) => req(`/api/web-admin/users/${uid}`, { method: 'PATCH', body }),
  blacklist: () => req('/api/web-admin/blacklist'),
  // ── 🌊 WA3 — reorder محتوا ──
  waReorderLesson: (lid, direction) => req(`/api/web-admin/content/lessons/${lid}/reorder`, { method: 'POST', body: { direction } }),
  waReorderSession: (sid, direction) => req(`/api/web-admin/content/sessions/${sid}/reorder`, { method: 'POST', body: { direction } }),
  waReorderItem: (cid, direction) => req(`/api/web-admin/content/items/${cid}/reorder`, { method: 'POST', body: { direction } }),
  // ── 🌊 WA3 — تب‌های پریتی محتوا (همان API موجود content_admin) ──
  caSchedule: (stype) => req('/api/content/schedule' + (stype ? `?stype=${stype}` : '')),
  caScheduleCreate: (body) => req('/api/content/schedule', { method: 'POST', body }),
  caScheduleEdit: (sid, body) => req(`/api/content/schedule/${sid}`, { method: 'PATCH', body }),
  caScheduleDel: (sid) => req(`/api/content/schedule/${sid}`, { method: 'DELETE' }),
  caFlexChange: (sid, body) => req(`/api/content/schedule/${sid}/flex-change`, { method: 'POST', body }),
  caFaq: () => req('/api/content/faq'),
  caFaqAdd: (body) => req('/api/content/faq', { method: 'POST', body }),
  caFaqDel: (fid) => req(`/api/content/faq/${fid}`, { method: 'DELETE' }),
  caQbank: (p) => req('/api/content/qbank/files?' + new URLSearchParams(Object.entries(p || {}).filter(([, v]) => v))),
  caQbankAdd: (form) => req('/api/content/qbank/files', { method: 'POST', form }),
  caQbankDel: (fid) => req(`/api/content/qbank/files/${fid}`, { method: 'DELETE' }),
  refSubjects: (intake) => req('/api/content/references/subjects' + (intake ? `?intake=${encodeURIComponent(intake)}` : '')),
  refSubjectAdd: (body) => req('/api/content/references/subjects', { method: 'POST', body }),
  refSubjectDel: (sid) => req(`/api/content/references/subjects/${sid}`, { method: 'DELETE' }),
  refBooks: (sid) => req(`/api/content/references/subjects/${sid}/books`),
  refBookAdd: (sid, name) => req(`/api/content/references/subjects/${sid}/books`, { method: 'POST', body: { name } }),
  refBookDel: (bid) => req(`/api/content/references/books/${bid}`, { method: 'DELETE' }),
  refBookFork: (bid, intake) => req(`/api/content/references/books/${bid}/fork?intake=${encodeURIComponent(intake)}`, { method: 'POST' }),
  refBookUnfork: (bid) => req(`/api/content/references/books/${bid}/fork`, { method: 'DELETE' }),
  refFiles: (bid) => req(`/api/content/references/books/${bid}/files`),
  refFileAdd: (bid, form) => req(`/api/content/references/books/${bid}/files`, { method: 'POST', form }),
  refFileDel: (fid) => req(`/api/content/references/files/${fid}`, { method: 'DELETE' }),
  // ── 🌊 WA3 — نمرات (grades/recent + find-student + bulk) — همان ادمین ربات ──
  gradesRecent: (skip = 0, limit = 30) => req(`/api/content/grades/recent?skip=${skip}&limit=${limit}`),
  gradesFind: (name) => req(`/api/content/grades/find-student?name=${encodeURIComponent(name)}`),
  gradesBulk: (body) => req('/api/content/grades/bulk', { method: 'POST', body }),
  // ── ai admin ──
  aiStats: () => req('/api/ai-admin/stats'),
  aiConfig: () => req('/api/ai-admin/config'),
  // 🌊 W-Admin — صفحه‌ی کامل هوشیار
  aiConfigUpdate: (body) => req('/api/ai-admin/config', { method: 'PUT', body }),
  aiReports: () => req('/api/ai-admin/reports'),
  aiBanned: () => req('/api/ai-admin/banned'),
  aiUsers: (q) => req('/api/ai-admin/users?q=' + encodeURIComponent(q)),
  aiBan: (uid) => req('/api/ai-admin/users/ban', { method: 'POST', body: { user_id: uid } }),
  aiResetQuota: (uid) => req('/api/ai-admin/users/reset-quota', { method: 'POST', body: { user_id: uid } }),
};

export function errText(e) {
  const d = e && e.message;
  const map = {
    forbidden: 'دسترسی ندارید (مجوز لازم نیست)',
    admin_only: 'این بخش فقط برای مالک سامانه است',
    not_registered: 'حساب یافت نشد',
    missing_init_data: 'نشست منقضی شده — دوباره وارد شوید',
    intake_out_of_scope: 'این مورد خارج از scope ورودی شماست',
    content_admin_only: 'این بخش فقط برای مدیر محتواست',
  };
  return map[d] || d || 'خطای ناشناخته';
}

// 📥 خروجی CSV سمت کلاینت (بدون رفت‌وبرگشت سرور)
export function exportCSV(filename, columns, rows) {
  const esc = v => '"' + String(v ?? '').replaceAll('"', '""') + '"';
  const lines = [columns.map(c => esc(c.label)).join(',')];
  for (const r of rows) lines.push(columns.map(c => esc(typeof c.v === 'function' ? c.v(r) : r[c.v])).join(','));
  const blob = new Blob(['﻿' + lines.join('\n')], { type: 'text/csv;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}
