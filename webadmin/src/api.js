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
  usersBulk: (action, ids) => req('/api/web-admin/users/bulk', { method: 'POST', body: { action, ids } }),
  userDetail: (uid) => req(`/api/admin/users/${uid}`),
  userPatch: (uid, body) => req(`/api/admin/users/${uid}`, { method: 'PATCH', body }),
  userAction: (uid, act) => req(`/api/admin/users/${uid}/${act}`, { method: 'POST' }),
  // ── admin panel (owner) ──
  stats: () => req('/api/admin/stats'),
  botStatus: () => req('/api/admin/bot-status'),
  analytics: () => req('/api/admin/analytics'),
  tickets: (status) => req('/api/admin/tickets' + (status ? `?status=${status}` : '')),
  ticket: (tid) => req(`/api/admin/tickets/${tid}`),
  ticketReply: (tid, text) => req(`/api/admin/tickets/${tid}/reply`, { method: 'POST', body: { text } }),
  ticketClose: (tid) => req(`/api/admin/tickets/${tid}/close`, { method: 'POST' }),
  ticketReopen: (tid) => req(`/api/admin/tickets/${tid}/reopen`, { method: 'POST' }),
  broadcast: (body) => req('/api/admin/broadcast', { method: 'POST', body }),
  broadcastPreview: (body) => req('/api/admin/broadcast/preview', { method: 'POST', body }),
  broadcastHistory: () => req('/api/admin/broadcast/history'),
  auditLogs: (p) => req('/api/admin/audit-logs?' + new URLSearchParams(Object.entries(p).filter(([, v]) => v))),
  settings: () => req('/api/admin/settings'),
  patchSettings: (body) => req('/api/admin/settings', { method: 'PATCH', body }),
  backup: () => req('/api/admin/backup', { method: 'POST' }),
  intakes: () => req('/api/admin/intakes'),
  pendingUsers: () => req('/api/admin/users/pending'),
  // ── rbAC ──
  roles: () => req('/api/admin/rbac/roles'),
  perms: () => req('/api/admin/rbac/permissions'),
  createRole: (body) => req('/api/admin/rbac/roles', { method: 'POST', body }),
  patchRole: (k, body) => req(`/api/admin/rbac/roles/${k}`, { method: 'PATCH', body }),
  deleteRole: (k) => req(`/api/admin/rbac/roles/${k}`, { method: 'DELETE' }),
  // ── subscription admin ──
  subOverview: () => req('/api/subscription-admin/overview'),
  subPayments: (p) => req('/api/subscription-admin/payments?' + new URLSearchParams(p || {})),
  subPaymentDecision: (pid, approved, note = '') =>
    req(`/api/subscription-admin/payments/${pid}/decision`, { method: 'POST', body: { approved, note } }),
  discounts: () => req('/api/subscription-admin/discounts'),
  // ── content (scope-aware) ──
  caIntakes: () => req('/api/content/intakes'),
  caOverview: (intake) => req('/api/content/overview' + (intake ? `?intake=${intake}` : '')),
  caQuestionsPending: () => req('/api/content/questions/pending'),
  caQuestionApprove: (qid) => req(`/api/content/questions/${qid}/approve`, { method: 'POST' }),
  caQuestionReject: (qid) => req(`/api/content/questions/${qid}/reject`, { method: 'POST' }),
  // ── ai admin ──
  aiStats: () => req('/api/ai-admin/stats'),
  aiConfig: () => req('/api/ai-admin/config'),
};

export function errText(e) {
  const d = e && e.message;
  const map = {
    forbidden: 'دسترسی ندارید (مجوز لازم نیست)',
    admin_only: 'این بخش فقط برای مالک سامانه است',
    not_registered: 'حساب یافت نشد',
    missing_init_data: 'نشست منقضی شده — دوباره وارد شوید',
  };
  return map[d] || d || 'خطای ناشناخته';
}
