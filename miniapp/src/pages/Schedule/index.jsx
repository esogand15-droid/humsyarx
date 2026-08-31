import PageError from '../../components/shared/PageError';
import EmptyState from '../../components/shared/EmptyState';

import { useState, useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import api from '../../lib/api';
import Header from '../../components/layout/Header';
import {
  Spinner,
} from '../../components/shared/Loading';

import {
  ScheduleSkeleton,
} from '../../components/shared/skeletons';
import { haptic } from '../../lib/telegram';
import { useAuthStore } from '../../stores/authStore';

const TYPES = {
  class: {
    icon: '🏫',
    label: 'کلاس‌ها',
    color: 'var(--t-acc)',
    soft: 'var(--soft-acc)',
  },

  exam: {
    icon: '📝',
    label: 'امتحانات',
    color: 'var(--t-err)',
    soft: 'var(--soft-err)',
  },

  makeup: {
    icon: '🔄',
    label: 'جبرانی',
    color: 'var(--t-warn)',
    soft: 'var(--soft-warn)',
  },
};

const days = (value) => {
  if (
    value === null ||
    value === undefined ||
    value === ''
  ) {
    return null;
  }

  const parsed = Number(value);

  return Number.isFinite(parsed)
    ? Math.max(
        0,
        Math.floor(parsed)
      )
    : null;
};

const groupName = (value) => {
  if (
    !value ||
    value === '0'
  ) {
    return '';
  }

  if (value === 'هر دو') {
    return 'هر دو گروه';
  }

  return `گروه ${value}`;
};


export default function Schedule() {
  const [
    tab,
    setTab,
  ] = useState('class');

  const userGroup = useAuthStore(
    (state) =>
      state.user?.group || ''
  );

  const {
    data,
    isLoading,
    isError,
    refetch,
    isRefetching,
  } = useQuery({
    queryKey: [
      'schedule',
      userGroup,
    ],

    queryFn: () =>
      api
        .get('/api/schedule')
        .then(
          (response) =>
            response.data
        ),

    staleTime:
      5 * 60 * 1000,

    refetchOnMount:
      'always',
  });

  const schedule =
    Array.isArray(
      data?.schedule
    )
      ? data.schedule
      : [];

  const items =
    schedule.filter(
      (item) =>
        item?.type === tab
    );

  /* 🧠 موج N3 — Deep Link: /schedule?hl=<درس>
     اولین کارت هم‌نام درس، اسکرول + فلش می‌خورد */
  const [flashIdx, setFlashIdx] = useState(-1);
  const [searchParams] = useSearchParams();
  const hlDone = useRef(false);

  useEffect(() => {
    if (hlDone.current || !items.length) return;

    const hl = searchParams.get('hl');
    if (!hl) return;

    const match = items.findIndex(
      (it) =>
        it.id === hl ||
        (it.lesson || '') === hl ||
        (it.lesson || '').includes(hl)
    );

    if (match < 0) return;

    hlDone.current = true;
    setFlashIdx(match);

    const el = document.querySelector(
      `[data-lidx="${match}"]`
    );

    if (el) {
      setTimeout(() => {
        el.scrollIntoView({
          behavior: 'smooth',
          block: 'center',
        });
      }, 60);

      setTimeout(() => setFlashIdx(-1), 3200);
    }
  }, [items, searchParams]);

  const config =
    TYPES[tab];

  const counts =
    Object.fromEntries(
      Object.keys(TYPES).map(
        (type) => [
          type,

          schedule.filter(
            (item) =>
              item?.type === type
          ).length,
        ]
      )
    );

  const nearestExam =
    schedule.find(
      (item) =>
        item?.type === 'exam'
    );

  const nearestDays =
    days(
      nearestExam?.days_left
    );

  return (
    <>
      <Header
        title="برنامه درسی"
        subtitle={`برنامه شخصی ${
          groupName(
            data?.group ||
            userGroup
          ) || 'شما'
        }`}
        back={false}
        onRefresh={refetch}
        refreshing={isRefetching}
      />

      <main className="page fade-up">
        <section
          className={
            'card card-glow hero-card'
          }
          style={{
            marginBottom: 'var(--sp-4)',
          }}
        >
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 13,
            }}
          >
            <div
              style={{
                width: 52,
                height: 52,

                display: 'grid',
                placeItems: 'center',

                borderRadius: 'var(--r-lg)',

                background:
                  'var(--grad-brand)',

                boxShadow:
                  'var(--shd-glow)',

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
                  color:
                    'var(--txm)',

                  fontSize: 'var(--fs-cap)',
                }}
              >
                برنامه ترم جاری
              </div>

              <div
                style={{
                  fontSize: 'var(--fs-xl)',

                  fontWeight:
                    900,

                  marginTop:
                    2,
                }}
              >
                {groupName(
                  data?.group ||
                  userGroup
                ) ||
                  'گروه نامشخص'}
              </div>

              <div
                style={{
                  display: 'flex',

                  gap: 5,

                  marginTop: 'var(--sp-2)',
                }}
              >
                <span className="badge b-acc">
                  {counts.class ||
                    0}{' '}
                  کلاس
                </span>

                <span className="badge b-red">
                  {counts.exam ||
                    0}{' '}
                  امتحان
                </span>
              </div>
            </div>

            {nearestExam &&
              nearestDays !==
                null && (
                <div
                  style={{
                    minWidth:
                      58,

                    textAlign:
                      'center',

                    padding:
                      '8px 7px',

                    borderRadius: 'var(--r-md)',

                    background:
                      nearestDays <=
                      3
                        ? 'var(--soft-err)'
                        : 'var(--acc-soft)',

                    border:
                      `1px solid ${
                        nearestDays <=
                        3
                          ? 'var(--bd-err)'
                          : 'var(--bdg)'
                      }`,
                  }}
                >
                  <div
                    style={{
                      color:
                        nearestDays <=
                        3
                          ? 'var(--err)'
                          : 'var(--acc2)',

                      fontSize: 'var(--fs-xl)',

                      fontWeight:
                        900,
                    }}
                  >
                    {nearestDays}
                  </div>

                  <div
                    style={{
                      color:
                        'var(--txm)',

                      fontSize: 'var(--fs-cap)',
                    }}
                  >
                    {nearestDays ===
                    0
                      ? 'امروز'
                      : 'روز تا امتحان'}
                  </div>
                </div>
              )}
          </div>
        </section>

        <div
          className="tab-bar"
          role="tablist"
        >
          {Object.entries(
            TYPES
          ).map(
            ([key, item]) => (
              <button
                type="button"
                role="tab"
                aria-selected={
                  tab === key
                }
                key={key}
                className={`tab-btn ${
                  tab === key
                    ? 'tab-btn--on'
                    : ''
                }`}
                onClick={() => {
                  haptic();
                  setTab(key);
                }}
              >
                {item.icon}{' '}
                {item.label}{' '}

                {counts[key]
                  ? `(${counts[key]})`
                  : ''}
              </button>
            )
          )}
        </div>

        {isLoading ? (
          <ScheduleSkeleton />
        ) : isError ? (
          <PageError
            text={
              'دریافت برنامه انجام نشد.'
            }
            onRetry={() => refetch()}
            pending={isRefetching}
          />
        ) : items.length === 0 ? (
          <EmptyState
            icon={TYPES[tab].icon}
          >
            موردی در بخش{' '}
            {TYPES[tab].label}{' '}
            ثبت نشده است.
          </EmptyState>
        ) : (
          <section
            style={{
              display: 'grid',
              gap: 9,
            }}
          >
            {items.map(
              (item, index) => {
                const remaining =
                  days(
                    item.days_left
                  );

                const urgent =
                  item.type ===
                    'exam' &&
                  remaining !==
                    null &&
                  remaining <= 3;

                const note =
                  item.note ||
                  item.flex_note ||
                  '';

                return (
                  <article
                    key={
                      item.id ||
                      `${item.lesson}-${index}`
                    }
                    data-lidx={index}
                    className={
                      flashIdx === index
                        ? 'card hl-flash'
                        : 'card'
                    }
                    style={{
                      padding: 13,

                      borderColor:
                        urgent
                          ? 'var(--bd-err)'
                          : 'var(--bd)',
                    }}
                  >
                    <div
                      style={{
                        display:
                          'flex',

                        alignItems:
                          'flex-start',

                        gap: 11,
                      }}
                    >
                      <div
                        style={{
                          display:
                            'grid',

                          flex:
                            '0 0 46px',

                          height:
                            46,

                          placeItems:
                            'center',

                          borderRadius: 'var(--r-md)',

                          background:
                            urgent
                              ? 'var(--soft-err)'
                              : config.soft,

                          fontSize:
                            21,
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
                            display:
                              'flex',

                            alignItems:
                              'center',

                            gap: 6,
                          }}
                        >
                          <h3
                            style={{
                              overflow:
                                'hidden',

                              fontSize: 'var(--fs-md)',

                              fontWeight:
                                850,

                              textOverflow:
                                'ellipsis',

                              whiteSpace:
                                'nowrap',
                            }}
                          >
                            {item.lesson ||
                              'بدون عنوان'}
                          </h3>

                          {item.flex_type ===
                            'flexible' && (
                            <span className="badge b-yel">
                              منعطف
                            </span>
                          )}
                        </div>

                        {item.teacher && (
                          <div
                            style={{
                              color:
                                'var(--tx2)',

                              fontSize: 'var(--fs-cap)',

                              marginTop:
                                3,
                            }}
                          >
                            👨‍🏫{' '}
                            {item.teacher}
                          </div>
                        )}

                        <div
                          style={{
                            display:
                              'flex',

                            flexWrap:
                              'wrap',

                            gap: 5,

                            marginTop: 'var(--sp-2)',
                          }}
                        >
                          <span className="badge b-acc">
                            📆{' '}
                            {item.date ||
                              'تاریخ نامشخص'}
                          </span>

                          {item.time && (
                            <span className="badge b-gray">
                              ⏰{' '}
                              {item.time}
                            </span>
                          )}

                          {item.location && (
                            <span className="badge b-gray">
                              📍{' '}
                              {
                                item.location
                              }
                            </span>
                          )}

                          {groupName(
                            item.group
                          ) && (
                            <span className="badge b-gray">
                              {groupName(
                                item.group
                              )}
                            </span>
                          )}
                        </div>
                      </div>

                      {item.type ===
                        'exam' &&
                        remaining !==
                          null && (
                          <span
                            className={`badge ${
                              urgent
                                ? 'b-red'
                                : 'b-grn'
                            }`}
                          >
                            {remaining ===
                            0
                              ? 'امروز'
                              : remaining ===
                                  1
                                ? 'فردا'
                                : `${remaining} روز`}
                          </span>
                        )}
                    </div>

                    {note && (
                      <div
                        style={{
                          marginTop: 'var(--sp-3)',

                          padding:
                            '8px 10px',

                          color:
                            'var(--tx2)',

                          background:
                            'var(--soft-mut)',

                          borderRadius: 'var(--r-md)',

                          fontSize: 'var(--fs-cap)',

                          lineHeight:
                            1.7,
                        }}
                      >
                        📝 {note}
                      </div>
                    )}
                  </article>
                );
              }
            )}
          </section>
        )}
      </main>
    </>
  );
}
