import PageError from "../../components/shared/PageError";
import EmptyState from "../../components/shared/EmptyState";

import { useState, useEffect, useRef, useMemo } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import api from "../../lib/api";
import Header from "../../components/layout/Header";
import { Spinner } from "../../components/shared/Loading";

import { ScheduleSkeleton } from "../../components/shared/skeletons";
import { haptic } from "../../lib/telegram";
import { useUIStore } from "../../stores/uiStore";
import { faNum, faDate } from "../../lib/format";

function mergeScheduleBlocks(list) {
  const _p = (v) => {
    const m = String(v || "").match(/(\d{1,2}):(\d{2})/);
    return m ? Number(m[1]) * 60 + Number(m[2]) : null;
  };
  const _f = (min) => `${String(Math.floor(min / 60)).padStart(2, "0")}:${String(min % 60).padStart(2, "0")}`;
  const sorted = [...(list || [])].sort((a, b) => (a.date || "").localeCompare(b.date || "") || String(a.time || "").localeCompare(String(b.time || "")));
  const out = [];
  for (const cur of sorted) {
    const prev = out[out.length - 1];
    if (prev && prev.date === cur.date && prev.lesson === cur.lesson && (prev.group || "") === (cur.group || "") && (prev.type || "class") === (cur.type || "class") && (prev.location || "") === (cur.location || "") && (prev.teacher || "") === (cur.teacher || "")) {
      const prevEnd = _p(prev.end_time || prev.time_end || "") ?? (_p(prev.time) !== null ? _p(prev.time) + 60 : null);
      const prevStart = _p(prev.time);
      const prevDur = prevEnd !== null && prevStart !== null ? prevEnd - prevStart : null;
      const curStart = _p(cur.time);
      const curEnd = _p(cur.end_time || cur.time_end || "") ?? (curStart !== null ? curStart + 60 : null);
      const curDur = curEnd !== null && curStart !== null ? curEnd - curStart : null;
      if (prevEnd !== null && curStart !== null && prevEnd === curStart && curEnd !== null && prevDur === 60 && curDur === 60) {
        prev.end_time = _f(curEnd);
        prev._merged = (prev._merged || 1) + 1;
        continue;
      }
    }
    out.push({ ...cur });
  }
  return out;
}

import { useAuthStore } from "../../stores/authStore";

const TYPES = {
  class: {
    icon: "🏫",
    label: "کلاس‌ها",
    color: "var(--t-acc)",
    soft: "var(--soft-acc)",
  },

  exam: {
    icon: "📝",
    label: "امتحانات",
    color: "var(--t-err)",
    soft: "var(--soft-err)",
  },

  makeup: {
    icon: "🔄",
    label: "جبرانی",
    color: "var(--t-warn)",
    soft: "var(--soft-warn)",
  },
};

const days = (value) => {
  if (value === null || value === undefined || value === "") {
    return null;
  }

  const parsed = Number(value);

  return Number.isFinite(parsed) ? Math.max(0, Math.floor(parsed)) : null;
};

const groupName = (value) => {
  if (!value || value === "0") {
    return "";
  }

  if (value === "هر دو") {
    return "هر دو گروه";
  }

  return `گروه ${value}`;
};

export default function Schedule() {
  const [tab, setTab] = useState("class");
  const toast = useUIStore((s) => s.toast);
  const queryClient = useQueryClient();
  const [calBusy, setCalBusy] = useState(false);
  const [selectOpen, setSelectOpen] = useState(false);
  const [selDraft, setSelDraft] = useState({});
  const [savingSel, setSavingSel] = useState(false);

  /* 🌊 W8/UX-05 — دانلود iCal (blob با احراز initData) */
  const downloadCal = async () => {
    if (calBusy) return;
    setCalBusy(true);
    try {
      const r = await api.get("/api/schedule/ical", { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([r.data], { type: "text/calendar" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = "humsyar-schedule.ics";
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 4000);
      toast("📅 فایل تقویم دانلود شد");
    } catch {
      toast("دانلود تقویم ناموفق بود", "err");
    }
    setCalBusy(false);
  };

  const userGroup = useAuthStore((state) => state.user?.group || "");

  const { data, isLoading, isError, refetch, isRefetching } = useQuery({
    queryKey: ["schedule", userGroup],

    queryFn: () => api.get("/api/schedule").then((response) => response.data),

    staleTime: 5 * 60 * 1000,

    refetchOnMount: "always",
  });

  const {
    data: selData,
    isLoading: selLoading,
    refetch: refetchSel,
  } = useQuery({
    queryKey: ["course-selections"],
    queryFn: () => api.get("/api/schedule/course-selections").then((r) => r.data),
    staleTime: 2 * 60 * 1000,
    refetchOnMount: "always",
  });

  useEffect(() => {
    if (!selData) return;
    const map = { ...(selData.selections_map || {}) };
    for (const off of selData.offerings || []) {
      if (off.single_group && off.auto_selected_group && !map[off.lesson]) {
        map[off.lesson] = off.auto_selected_group;
      }
    }
    setSelDraft(map);
  }, [selData]);

  const schedule = Array.isArray(data?.schedule) ? data.schedule : [];

  const items = schedule.filter((item) => item?.type === tab);

  /* 🧠 موج N3 — Deep Link: /schedule?hl=<درس> یا /schedule?select=1 */
  const [flashIdx, setFlashIdx] = useState(-1);
  const [searchParams, setSearchParams] = useSearchParams();
  const hlDone = useRef(false);

  useEffect(() => {
    if (searchParams.get("select") === "1") {
      setSelectOpen(true);
    }
  }, [searchParams]);

  useEffect(() => {
    if (hlDone.current || !items.length) return;

    const hl = searchParams.get("hl");
    if (!hl) return;

    const match = items.findIndex(
      (it) =>
        it.id === hl ||
        (it.lesson || "") === hl ||
        (it.lesson || "").includes(hl),
    );

    if (match < 0) return;

    hlDone.current = true;
    setFlashIdx(match);

    const el = document.querySelector(`[data-lidx="${match}"]`);

    if (el) {
      setTimeout(() => {
        el.scrollIntoView({
          behavior: "smooth",
          block: "center",
        });
      }, 60);

      setTimeout(() => setFlashIdx(-1), 3200);
    }
  }, [items, searchParams]);

  const config = TYPES[tab];

  const counts = Object.fromEntries(
    Object.keys(TYPES).map((type) => [
      type,

      schedule.filter((item) => item?.type === type).length,
    ]),
  );

  const nearestExam = schedule.find((item) => item?.type === "exam");

  const nearestDays = days(nearestExam?.days_left);

  const offerings = selData?.offerings || [];
  const conflicts = data?.conflicts || [];
  const hasCustomSelection = Boolean(data?.has_custom_selection || selData?.has_selections);
  const unselectedLessons = data?.unselected_lessons || [];

  // محاسبه زنده‌ی گروه اکثریت در شیت انتخاب واحد
  const liveMajority = useMemo(() => {
    const fallback = selData?.registered_group || data?.registered_group || userGroup || "1";
    let c1 = 0, c2 = 0, u1 = 0, u2 = 0;
    for (const off of offerings) {
      const g = selDraft[off.lesson];
      const cred = Number(off.credit || 1) || 1;
      if (g === "1") { c1 += 1; u1 += cred; }
      else if (g === "2") { c2 += 1; u2 += cred; }
    }
    let grp = fallback;
    if (c1 > c2) grp = "1";
    else if (c2 > c1) grp = "2";
    else if (c1 > 0 || c2 > 0) {
      if (u1 > u2) grp = "1";
      else if (u2 > u1) grp = "2";
      else grp = fallback;
    }
    return { group: grp, c1, c2, total: c1 + c2 };
  }, [offerings, selDraft, selData, data, userGroup]);

  const setAllGroup = (targetGroup) => {
    haptic();
    const next = {};
    for (const off of offerings) {
      if (off.single_group && off.auto_selected_group) {
        next[off.lesson] = off.auto_selected_group;
      } else {
        next[off.lesson] = targetGroup;
      }
    }
    setSelDraft(next);
  };

  const toggleCourseGroup = (lesson, group, isSingle) => {
    if (isSingle) return;
    haptic();
    setSelDraft((prev) => {
      const next = { ...prev };
      if (next[lesson] === group) {
        delete next[lesson];
      } else {
        next[lesson] = group;
      }
      return next;
    });
  };

  const saveSelections = async () => {
    setSavingSel(true);
    try {
      const payload = Object.entries(selDraft)
        .filter(([, g]) => g === "1" || g === "2")
        .map(([lesson, group]) => ({ lesson, group }));
      const r = await api.post("/api/schedule/course-selections", {
        selections: payload,
        term: selData?.term,
      });
      await Promise.all([
        refetch(),
        refetchSel(),
        queryClient.invalidateQueries({ queryKey: ["profile"] }),
      ]);
      setSelectOpen(false);
      if (searchParams.get("select")) {
        searchParams.delete("select");
        setSearchParams(searchParams, { replace: true });
      }
      toast(
        `✅ برنامه شخصی شما ذخیره شد · گروه اکثریت: گروه ${faNum(r.data?.computed_group || liveMajority.group)}`,
      );
    } catch {
      toast("ذخیره انتخاب واحد ناموفق بود", "err");
    }
    setSavingSel(false);
  };

  return (
    <>
      <Header
        title="برنامه درسی"
        subtitle={`برنامه شخصی ${groupName(data?.computed_group || data?.group || userGroup) || "شما"}`}
        back={false}
        onRefresh={refetch}
        refreshing={isRefetching}
      />

      <main className="page fade-up">
        <section
          className={"card card-glow hero-card"}
          style={{
            marginBottom: "var(--sp-3)",
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 13,
            }}
          >
            <div
              style={{
                width: 52,
                height: 52,

                display: "grid",
                placeItems: "center",

                borderRadius: "var(--r-lg)",

                background: "var(--grad-brand)",

                boxShadow: "var(--shd-glow)",

                fontSize: 24,
              }}
            >
              📅
            </div>

            <div
              style={{
                flex: 1,
              }}
            >
              <div
                style={{
                  color: "var(--txm)",

                  fontSize: "var(--fs-cap)",
                }}
              >
                {hasCustomSelection ? "برنامه شخصی‌سازی‌شده ترم جاری" : "برنامه ترم جاری"}
              </div>

              <div
                style={{
                  fontSize: "var(--fs-xl)",

                  fontWeight: 900,

                  marginTop: 2,
                }}
              >
                {groupName(data?.computed_group || data?.group || userGroup) || "گروه نامشخص"}
              </div>

              <div
                style={{
                  display: "flex",
                  flexWrap: "wrap",
                  gap: 5,

                  marginTop: "var(--sp-2)",
                }}
              >
                <span className="badge b-acc">{faNum(counts.class || 0)} کلاس</span>

                <span className="badge b-red">{faNum(counts.exam || 0)} امتحان</span>

                {hasCustomSelection && (
                  <span className="badge b-grn">
                    🎓 {faNum(data?.selected_count || 0)} درس انتخابی
                  </span>
                )}
              </div>
            </div>

            {nearestExam && nearestDays !== null && (
              <div
                style={{
                  minWidth: 58,

                  textAlign: "center",

                  padding: "8px 7px",

                  borderRadius: "var(--r-md)",

                  background:
                    nearestDays <= 3 ? "var(--soft-err)" : "var(--acc-soft)",

                  border: `1px solid ${
                    nearestDays <= 3 ? "var(--bd-err)" : "var(--bdg)"
                  }`,
                }}
              >
                <div
                  style={{
                    color: nearestDays <= 3 ? "var(--err)" : "var(--acc2)",

                    fontSize: "var(--fs-xl)",

                    fontWeight: 900,
                  }}
                >
                  {nearestDays}
                </div>

                <div
                  style={{
                    color: "var(--txm)",

                    fontSize: "var(--fs-cap)",
                  }}
                >
                  {nearestDays === 0 ? "امروز" : "روز تا امتحان"}
                </div>
              </div>
            )}
          </div>
        </section>

        {/* 🎓 کارت شیشه‌ای (Glassmorphism) انتخاب واحد درس‌به‌درس */}
        <section
          className="glass"
          style={{
            marginBottom: "var(--sp-3)",
            padding: "14px 15px",
            borderRadius: "var(--r-lg)",
            background: "linear-gradient(135deg, rgba(99, 102, 241, 0.14), rgba(14, 165, 233, 0.10))",
            backdropFilter: "blur(18px)",
            WebkitBackdropFilter: "blur(18px)",
            border: "1px solid rgba(255, 255, 255, 0.18)",
            boxShadow: "0 8px 28px rgba(0, 0, 0, 0.12)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
            <div style={{ flex: 1, minWidth: 180 }}>
              <div style={{ fontWeight: 850, fontSize: "var(--fs-md)", display: "flex", alignItems: "center", gap: 6 }}>
                <span>🎓</span>
                <span>{hasCustomSelection ? "انتخاب واحد شخصی شما ثبت شده" : "برنامه کلاسی‌ات رو شخصی‌سازی کن!"}</span>
              </div>
              <div style={{ color: "var(--tx2)", fontSize: "var(--fs-cap)", marginTop: 4, lineHeight: 1.65 }}>
                {hasCustomSelection
                  ? `${faNum(data?.selected_count || 0)} درس انتخاب شده · گروه اکثریت در پروفایل: ${groupName(data?.computed_group || data?.group)}`
                  : "برای هر درس مشخص کن با گروه ۱ برداشتیش یا گروه ۲ تا برنامه کلاسی دقیق خودت رو ببینی."}
              </div>
              {hasCustomSelection && unselectedLessons.length > 0 && (
                <div style={{ color: "var(--warn)", fontSize: "var(--fs-cap)", marginTop: 4 }}>
                  ℹ️ {faNum(unselectedLessons.length)} درس ارائه‌شده را انتخاب نکرده‌اید ({unselectedLessons.slice(0, 3).join("، ")}{unselectedLessons.length > 3 ? " و…" : ""})
                </div>
              )}
            </div>
            <button
              type="button"
              className="btn btn-p sm"
              style={{
                borderRadius: 12,
                padding: "9px 14px",
                fontWeight: 800,
                boxShadow: "0 4px 16px rgba(99, 102, 241, 0.32)",
              }}
              onClick={() => {
                haptic();
                setSelectOpen(true);
              }}
            >
              {hasCustomSelection ? "✏️ ویرایش انتخاب واحد" : "✨ انتخاب واحدم رو وارد می‌کنم"}
            </button>
          </div>
        </section>

        {/* ⚠️ هشدار تداخل زمانی در صورت تداخل دو درس انتخابی */}
        {conflicts.length > 0 && (
          <section
            className="card"
            style={{
              marginBottom: "var(--sp-3)",
              padding: "11px 13px",
              borderColor: "var(--bd-err)",
              background: "var(--soft-err)",
              borderInlineStart: "3px solid var(--err)",
            }}
          >
            <div style={{ fontWeight: 850, fontSize: "var(--fs-sm)", color: "var(--err)", marginBottom: 4 }}>
              ⚠️ هشدار تداخل زمانی در برنامه انتخابی شما ({faNum(conflicts.length)} مورد)
            </div>
            {conflicts.slice(0, 3).map((c, idx) => (
              <div key={idx} style={{ fontSize: "var(--fs-cap)", color: "var(--tx2)", lineHeight: 1.6 }}>
                • {c.message}
              </div>
            ))}
          </section>
        )}

        <div className="row" style={{ marginBottom: 8, gap: 8, flexWrap: "wrap" }}>
          <button type="button" className="btn sm" disabled={calBusy} onClick={downloadCal}>
            {calBusy ? "⏳ …" : "📅 افزودن به تقویم (.ics)"}
          </button>
        </div>

        <div className="tab-bar" role="tablist">
          {Object.entries(TYPES).map(([key, item]) => (
            <button
              type="button"
              role="tab"
              aria-selected={tab === key}
              key={key}
              className={`tab-btn ${tab === key ? "tab-btn--on" : ""}`}
              onClick={() => {
                haptic();
                setTab(key);
              }}
            >
              {item.icon} {item.label} {counts[key] ? `(${counts[key]})` : ""}
            </button>
          ))}
        </div>

        {isLoading ? (
          <ScheduleSkeleton />
        ) : isError ? (
          <PageError
            text={"دریافت برنامه انجام نشد."}
            onRetry={() => refetch()}
            pending={isRefetching}
          />
        ) : items.length === 0 ? (
          <EmptyState icon={TYPES[tab].icon}>
            موردی در بخش {TYPES[tab].label} ثبت نشده است.
          </EmptyState>
        ) : (
          (() => {
            const _merged = mergeScheduleBlocks(items);
            const _grouped2 = {};
            for (const it of _merged) {
              const k = it.date || "بدون تاریخ";
              (_grouped2[k] ||= []).push(it);
            }
            const _dates = Object.keys(_grouped2).sort((a, b) =>
              a.localeCompare(b),
            );
            return (
              <section style={{ display: "grid", gap: 14 }}>
                {_dates.map((day) => {
                  const dayItems = _grouped2[day].sort((a, b) =>
                    String(a.time || "").localeCompare(String(b.time || "")),
                  );
                  return (
                    <div key={day} style={{ display: "grid", gap: 9 }}>
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 8,
                          padding: "6px 2px",
                        }}
                      >
                        <span
                          style={{
                            display: "grid",
                            width: 36,
                            height: 36,
                            placeItems: "center",
                            borderRadius: 10,
                            background: "var(--acc-soft)",
                            fontSize: 16,
                          }}
                        >
                          📅
                        </span>
                        <div>
                          <b style={{ fontSize: "var(--fs-sm)" }}>
                            {faDate(day, "—")}
                          </b>
                          <div
                            className="muted"
                            style={{ fontSize: "var(--fs-cap)" }}
                          >
                            {faNum(dayItems.length)} جلسه · {faDate(day)}
                          </div>
                        </div>
                        <span className="spacer" />
                        <span className="badge b-acc">
                          {faNum(dayItems.length)}
                        </span>
                      </div>
                      {dayItems.map((item, index) => {
                        const remaining = days(item.days_left);

                        const urgent =
                          item.type === "exam" &&
                          remaining !== null &&
                          remaining <= 3;

                        const note = item.note || item.flex_note || "";

                        return (
                          <article
                            key={item.id || `${item.lesson}-${index}-${day}`}
                            data-lidx={index}
                            className={
                              flashIdx === index ? "card hl-flash" : "card"
                            }
                            style={{
                              padding: 13,

                              borderColor: urgent
                                ? "var(--bd-err)"
                                : "var(--bd)",
                              borderInlineStart: urgent
                                ? "3px solid var(--err)"
                                : item.type === "makeup"
                                  ? "3px solid var(--warn)"
                                  : "3px solid var(--acc)",
                            }}
                          >
                            <div
                              style={{
                                display: "flex",

                                alignItems: "flex-start",

                                gap: 11,
                              }}
                            >
                              <div
                                style={{
                                  display: "grid",

                                  flex: "0 0 46px",

                                  height: 46,

                                  placeItems: "center",

                                  borderRadius: "var(--r-md)",

                                  background: urgent
                                    ? "var(--soft-err)"
                                    : config.soft,

                                  fontSize: 21,
                                }}
                              >
                                {config.icon}
                              </div>

                              <div
                                style={{
                                  flex: 1,
                                  minWidth: 0,
                                }}
                              >
                                <div
                                  style={{
                                    display: "flex",

                                    alignItems: "center",

                                    gap: 6,
                                  }}
                                >
                                  <h3
                                    style={{
                                      overflow: "hidden",

                                      fontSize: "var(--fs-md)",

                                      fontWeight: 850,

                                      textOverflow: "ellipsis",

                                      whiteSpace: "nowrap",
                                    }}
                                  >
                                    {item.lesson || "بدون عنوان"}
                                  </h3>

                                  {item.flex_type === "flexible" && (
                                    <span className="badge b-yel">منعطف</span>
                                  )}
                                  {item._merged && (
                                    <span
                                      className="badge b-acc"
                                      style={{ fontSize: 10 }}
                                    >
                                      🔗 {faNum(item._merged)} ادغام
                                    </span>
                                  )}
                                </div>

                                {item.teacher && (
                                  <div
                                    style={{
                                      color: "var(--tx2)",

                                      fontSize: "var(--fs-cap)",

                                      marginTop: 3,
                                    }}
                                  >
                                    👨‍🏫 {item.teacher}
                                  </div>
                                )}

                                <div
                                  style={{
                                    display: "flex",

                                    flexWrap: "wrap",

                                    gap: 5,

                                    marginTop: "var(--sp-2)",
                                  }}
                                >
                                  <span className="badge b-acc">
                                    📆 {faDate(item.date, "تاریخ نامشخص")}
                                  </span>

                                  {item.time && (
                                    <span className="badge b-gray">
                                      ⏰ {faNum(item.time)}
                                      {item.end_time || item.time_end
                                        ? ` تا ${faNum(item.end_time || item.time_end)}`
                                        : ""}
                                    </span>
                                  )}

                                  {item.location && (
                                    <span className="badge b-gray">
                                      📍 {item.location}
                                    </span>
                                  )}

                                  {groupName(item.group) && (
                                    <span className="badge b-gray">
                                      {groupName(item.group)}
                                    </span>
                                  )}
                                </div>
                              </div>

                              {item.type === "exam" && remaining !== null && (
                                <span
                                  className={`badge ${
                                    urgent ? "b-red" : "b-grn"
                                  }`}
                                >
                                  {remaining === 0
                                    ? "امروز"
                                    : remaining === 1
                                      ? "فردا"
                                      : `${remaining} روز`}
                                </span>
                              )}
                            </div>

                            {note && (
                              <div
                                style={{
                                  marginTop: "var(--sp-3)",

                                  padding: "8px 10px",

                                  color: "var(--tx2)",

                                  background: "var(--soft-mut)",

                                  borderRadius: "var(--r-md)",

                                  fontSize: "var(--fs-cap)",

                                  lineHeight: 1.7,
                                }}
                              >
                                📝 {note}
                              </div>
                            )}
                          </article>
                        );
                      })}
                    </div>
                  );
                })}
              </section>
            );
          })()
        )}

        {/* 🎓 شیت شیشه‌ای (Glassmorphism) انتخاب واحد درس‌به‌درس */}
        {selectOpen && (
          <div
            className="more-sheet"
            role="dialog"
            aria-modal="true"
            onClick={() => setSelectOpen(false)}
            style={{
              position: "fixed",
              inset: 0,
              zIndex: 999,
              background: "rgba(9, 13, 28, 0.56)",
              backdropFilter: "blur(14px)",
              WebkitBackdropFilter: "blur(14px)",
              display: "flex",
              alignItems: "flex-end",
              justifyContent: "center",
            }}
          >
            <div
              className="glass sheet-in"
              onClick={(e) => e.stopPropagation()}
              style={{
                width: "100%",
                maxWidth: 540,
                maxHeight: "88vh",
                display: "flex",
                flexDirection: "column",
                borderRadius: "24px 24px 0 0",
                background: "linear-gradient(165deg, rgba(28, 34, 62, 0.88), rgba(16, 20, 40, 0.94))",
                backdropFilter: "blur(24px)",
                WebkitBackdropFilter: "blur(24px)",
                border: "1px solid rgba(255, 255, 255, 0.18)",
                boxShadow: "0 -12px 42px rgba(0, 0, 0, 0.45)",
                padding: "16px 16px 20px",
                color: "var(--tx)",
              }}
            >
              <div className="more-sheet__handle" style={{ marginBottom: 10 }} />

              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
                <div>
                  <div style={{ fontWeight: 900, fontSize: "var(--fs-lg)" }}>
                    🎓 انتخاب گروه درس‌های این ترم
                  </div>
                  <div style={{ fontSize: "var(--fs-cap)", color: "var(--tx2)", marginTop: 2 }}>
                    هر درس را با کدام گروه و استاد برداشته‌ای؟ هر زمان خواستی می‌توانی ویرایشش کنی.
                  </div>
                </div>
                <button
                  type="button"
                  className="btn sm"
                  onClick={() => setSelectOpen(false)}
                  style={{ borderRadius: 10 }}
                >
                  ✕
                </button>
              </div>

              {/* میانبرهای سریع بالای لیست */}
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr",
                  gap: 8,
                  marginTop: 12,
                  marginBottom: 12,
                }}
              >
                <button
                  type="button"
                  className="btn sm"
                  onClick={() => setAllGroup("1")}
                  style={{
                    padding: "9px 10px",
                    borderRadius: 12,
                    fontWeight: 800,
                    background: "rgba(99, 102, 241, 0.18)",
                    border: "1px solid rgba(99, 102, 241, 0.4)",
                  }}
                >
                  ⚡ همه رو گروه ۱ بزن
                </button>
                <button
                  type="button"
                  className="btn sm"
                  onClick={() => setAllGroup("2")}
                  style={{
                    padding: "9px 10px",
                    borderRadius: 12,
                    fontWeight: 800,
                    background: "rgba(14, 165, 233, 0.18)",
                    border: "1px solid rgba(14, 165, 233, 0.4)",
                  }}
                >
                  ⚡ همه رو گروه ۲ بزن
                </button>
              </div>

              {/* لیست درس‌های ترم جاری */}
              <div
                style={{
                  flex: 1,
                  overflowY: "auto",
                  display: "grid",
                  gap: 10,
                  paddingInlineEnd: 2,
                }}
              >
                {selLoading ? (
                  <div style={{ display: "grid", placeItems: "center", padding: 32 }}>
                    <Spinner />
                  </div>
                ) : offerings.length === 0 ? (
                  <div className="empty" style={{ padding: 24, textAlign: "center" }}>
                    هنوز درس‌های این ترم در برنامه ثبت نشده است.
                  </div>
                ) : (
                  offerings.map((course) => {
                    const chosen = selDraft[course.lesson] || "";
                    const isSingle = Boolean(course.single_group);
                    return (
                      <div
                        key={course.lesson}
                        style={{
                          padding: "12px 13px",
                          borderRadius: 16,
                          background: "rgba(255, 255, 255, 0.06)",
                          backdropFilter: "blur(12px)",
                          border: chosen
                            ? "1px solid rgba(99, 102, 241, 0.55)"
                            : "1px solid rgba(255, 255, 255, 0.12)",
                        }}
                      >
                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, marginBottom: 8 }}>
                          <b style={{ fontSize: "var(--fs-md)" }}>📚 {course.lesson}</b>
                          <div style={{ display: "flex", gap: 5, alignItems: "center" }}>
                            {course.credit ? (
                              <span className="badge b-gray" style={{ fontSize: 10 }}>
                                {faNum(course.credit)} واحد
                              </span>
                            ) : null}
                            {isSingle ? (
                              <span className="badge b-acc" style={{ fontSize: 10 }}>
                                تک‌گروهی (انتخاب خودکار)
                              </span>
                            ) : chosen ? (
                              <span className="badge b-grn" style={{ fontSize: 10 }}>
                                گروه {faNum(chosen)}
                              </span>
                            ) : (
                              <span className="badge b-yel" style={{ fontSize: 10 }}>
                                انتخاب نشده
                              </span>
                            )}
                          </div>
                        </div>

                        <div
                          style={{
                            display: "grid",
                            gridTemplateColumns: course.groups?.length === 1 ? "1fr" : "1fr 1fr",
                            gap: 8,
                          }}
                        >
                          {(course.groups || []).map((gObj) => {
                            const active = chosen === gObj.group;
                            return (
                              <button
                                type="button"
                                key={gObj.group}
                                disabled={isSingle}
                                onClick={() => toggleCourseGroup(course.lesson, gObj.group, isSingle)}
                                style={{
                                  textAlign: "right",
                                  padding: "9px 11px",
                                  borderRadius: 12,
                                  cursor: isSingle ? "default" : "pointer",
                                  background: active
                                    ? "linear-gradient(135deg, rgba(99, 102, 241, 0.35), rgba(59, 130, 246, 0.25))"
                                    : "rgba(255, 255, 255, 0.04)",
                                  border: active
                                    ? "1.5px solid rgba(129, 140, 248, 0.9)"
                                    : "1px solid rgba(255, 255, 255, 0.12)",
                                  color: "var(--tx)",
                                  transition: "all 0.15s ease",
                                }}
                              >
                                <div style={{ fontWeight: 850, fontSize: "var(--fs-sm)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                                  <span>👥 گروه {faNum(gObj.group)}</span>
                                  {active && <span>✅</span>}
                                </div>
                                <div style={{ fontSize: "var(--fs-cap)", color: "var(--tx2)", marginTop: 3 }}>
                                  👨‍🏫 {gObj.teacher || "استاد ثبت نشده"}
                                </div>
                                {gObj.schedule_summary && (
                                  <div style={{ fontSize: 11, color: "var(--txm)", marginTop: 2 }}>
                                    ⏰ {faNum(gObj.schedule_summary)}
                                  </div>
                                )}
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    );
                  })
                )}
              </div>

              {/* خلاصه زنده گروه اکثریت + دکمه ذخیره */}
              <div
                style={{
                  marginTop: 12,
                  paddingTop: 12,
                  borderTop: "1px solid rgba(255, 255, 255, 0.12)",
                  display: "grid",
                  gap: 10,
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: "var(--fs-cap)", color: "var(--tx2)" }}>
                  <span>
                    انتخاب‌شده: <b>{faNum(liveMajority.total)}</b> از <b>{faNum(offerings.length)}</b> درس
                    {" "}({faNum(liveMajority.c1)} گروه ۱ · {faNum(liveMajority.c2)} گروه ۲)
                  </span>
                  <span className="badge b-acc">
                    گروه اکثریت: گروه {faNum(liveMajority.group)}
                  </span>
                </div>

                <button
                  type="button"
                  className="btn btn-p"
                  disabled={savingSel}
                  onClick={saveSelections}
                  style={{
                    width: "100%",
                    padding: "12px",
                    borderRadius: 14,
                    fontWeight: 900,
                    fontSize: "var(--fs-md)",
                  }}
                >
                  {savingSel ? "⏳ در حال ذخیره برنامه شخصی…" : "💾 ذخیره و مشاهده برنامه کلاسی من"}
                </button>
              </div>
            </div>
          </div>
        )}
      </main>
    </>
  );
}
