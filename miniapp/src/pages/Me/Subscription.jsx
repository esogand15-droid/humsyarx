import { number } from '../../lib/format';

import { confirmAction } from '../../lib/confirm';
import {
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

import {
  useSearchParams,
} from 'react-router-dom';

import {
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query';

import api from '../../lib/api';
import Header from '../../components/layout/Header';

import {
  Spinner,
} from '../../components/shared/Loading';

import {
  SubscriptionSkeleton,
} from '../../components/shared/skeletons';

import {
  haptic,
  hapticNotif,
} from '../../lib/telegram';

import {
  useUIStore,
} from '../../stores/uiStore';





const money = (value) => {
  const formatted =
    new Intl.NumberFormat(
      'fa-IR'
    ).format(
      number(value)
    );

  return `${formatted} تومان`;
};


const PAYMENT_STATUS = {
  pending: [
    'در انتظار بررسی',
    'b-yel',
    '⏳',
  ],

  approved: [
    'تأییدشده',
    'b-grn',
    '✅',
  ],

  rejected: [
    'ردشده',
    'b-red',
    '❌',
  ],
};


// 🌊 GIFT — نتایج جست‌وجوی گیرنده (حریم‌محور: فقط نام/یوزرنیم)
function RecipientResults({ q, onPick }) {
  const { data, isFetching } = useQuery({
    queryKey: ['gift-recipients', q.trim()],
    queryFn: () =>
      api.get('/api/subscription/gift/recipients', {
        params: { q: q.trim() },
      }),
    enabled: q.trim().length >= 2,
  });

  if (q.trim().length < 2) {
    return (
      <div style={{ color: 'var(--txm)', fontSize: 'var(--fs-cap)' }}>
        حداقل ۲ نویسه بنویس تا جست‌وجو شروع شود…
      </div>
    );
  }

  if (isFetching) return <Spinner />;

  const items = data?.data?.items || [];

  if (items.length === 0) {
    return (
      <div style={{ color: 'var(--txm)', fontSize: 'var(--fs-cap)' }}>
        کسی با این مشخصات پیدا نشد.
      </div>
    );
  }

  return (
    <div style={{ display: 'grid', gap: 6 }}>
      {items.map((u) => (
        <button
          type="button"
          key={u.user_id}
          className="card card-tap"
          onClick={() => onPick(u)}
          style={{
            textAlign: 'right',
            fontSize: 'var(--fs-sm)',
            color: 'var(--tx1)',
          }}
        >
          {u.name}
          {u.username ? ` (@${u.username})` : ''}
        </button>
      ))}
    </div>
  );
}


export default function Subscription() {
  const [
    selectedId,
    setSelectedId,
  ] = useState(null);

  const [
    discountCode,
    setDiscountCode,
  ] = useState('');

  const [
    discount,
    setDiscount,
  ] = useState(null);

  const [
    receipt,
    setReceipt,
  ] = useState(null);

  const [
    accepted,
    setAccepted,
  ] = useState(false);

  const [
    result,
    setResult,
  ] = useState(null);

  // 🌊 GIFT — حالت هدیه: گیرنده، پیام و توکن idempotency
  const [
    giftMode,
    setGiftMode,
  ] = useState(false);

  const [
    giftTo,
    setGiftTo,
  ] = useState(null);

  const [
    giftQuery,
    setGiftQuery,
  ] = useState('');

  const [
    giftMessage,
    setGiftMessage,
  ] = useState('');

  // توکن یکتا برای هر تلاش خرید — double-submit یک رسید می‌سازد نه دو تا
  const idemRef = useRef(
    `mp-${Date.now()}-${Math.random()
      .toString(36)
      .slice(2, 10)}`
  );

  const toast = useUIStore(
    (state) => state.toast
  );

  const queryClient =
    useQueryClient();

  // 🎟 موج D1 — Deep Link از پیام کمپین:
  // ?discount=CODE → کد پیش‌پُر و پس از انتخاب پلن Auto-Validate
  const [
    searchParams,
    setSearchParams,
  ] = useSearchParams();


  const {
    data,
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: [
      'sub-status',
    ],

    queryFn: () =>
      api
        .get(
          '/api/subscription/status'
        )
        .then(
          (response) =>
            response.data
        ),

    staleTime:
      2 * 60 * 1000,
  });


  const plans =
    Array.isArray(
      data?.plans
    )
      ? data.plans
      : [];


  const payments =
    Array.isArray(
      data?.payments
    )
      ? data.payments
      : [];


  const selectedPlan =
    plans.find(
      (item) =>
        item.id === selectedId
    ) || null;


  const finalPrice =
    discount?.final_price ??
    selectedPlan?.price ??
    0;


  const free =
    Boolean(selectedPlan) &&
    number(finalPrice) === 0;


  const pending =
    Boolean(
      data
        ?.has_pending_payment
    );


  // 🌊 GIFT — تاریخچه‌ی هدیه‌ها (داده‌شده / دریافت‌شده)
  const giftsQuery =
    useQuery({
      queryKey: [
        'gifts-history',
      ],
      queryFn: () =>
        api.get(
          '/api/subscription/gifts'
        ),
    });


  const discountMutation =
    useMutation({
      // موج D1 — کد را می‌توان مستقیم به mutate داد (Deep-Link)
      mutationFn: (explicitCode) =>
        api.post(
          '/api/subscription/discount',

          {
            plan_id:
              selectedId,

            code:
              (
                explicitCode ??
                discountCode
              ).trim(),
          }
        ),

      onSuccess: (
        response
      ) => {
        hapticNotif(
          'success'
        );

        setDiscount(
          response.data
        );

        setDiscountCode(
          response.data.code ||
          discountCode
            .trim()
            .toUpperCase()
        );

        toast(
          `${
            response.data.percent
          }٪ تخفیف اعمال شد ✅`,

          'success'
        );
      },

      onError: (error) => {
        setDiscount(null);

        toast(
          error?.response
            ?.data
            ?.detail ||
            'کد تخفیف معتبر نیست',

          'error'
        );
      },
    });


  // 🎟 موج D1 — Deep Link ?discount=CODE
  // کد پیش‌پُر می‌شود و بعد از انتخاب پلن،
  // اعتبارسنجی خودکار انجام می‌گیرد (سرور re-validate می‌کند)
  const deepLinkCode = useMemo(
    () =>
      (
        searchParams.get('discount') || ''
      )
        .trim()
        .toUpperCase(),
    [searchParams]
  );

  useEffect(() => {
    if (deepLinkCode) {
      setDiscountCode(deepLinkCode);
    }
  }, [deepLinkCode]);

  useEffect(() => {
    if (!deepLinkCode || !selectedId || discount) return;
    let alive = true;
    const t = setTimeout(() => {
      if (!alive) return;
      discountMutation.mutate(deepLinkCode);
      setSearchParams({}, { replace: true });
    }, 0);
    return () => { alive = false; clearTimeout(t); };
  }, [deepLinkCode, selectedId, discount]);


  const buyMutation =
    useMutation({
      mutationFn: () => {
        const body =
          new FormData();

        body.append(
          'plan_id',
          selectedId
        );

        body.append(
          'discount_code',
          discount?.code ||
          ''
        );

        // 🌊 GIFT — فیلدهای هدیه؛ قیمت/گیرنده سرور-ساید
        // اعتبارسنجی می‌شوند و idem جلوی double-submit را می‌گیرد
        body.append(
          'gift_to',
          giftMode && giftTo
            ? String(giftTo.user_id)
            : '0'
        );

        body.append(
          'gift_message',
          giftMode ? giftMessage : ''
        );

        body.append(
          'idem',
          idemRef.current
        );

        if (receipt) {
          body.append(
            'receipt',
            receipt
          );
        }

        return api.post(
          '/api/subscription/buy',

          body,

          {
            timeout:
              120_000,
          }
        );
      },

      onSuccess: async (
        response
      ) => {
        hapticNotif(
          'success'
        );

        setResult(
          response.data
        );

        setSelectedId(null);
        setDiscountCode('');
        setDiscount(null);
        setReceipt(null);
        setAccepted(false);

        // 🌊 GIFT — پاک‌سازی حالت هدیه و تولید توکن تازه برای
        // خرید بعدی (توکن مصرف‌شده دیگر استفاده نمی‌شود)
        setGiftMode(false);
        setGiftTo(null);
        setGiftQuery('');
        setGiftMessage('');
        idemRef.current = `mp-${Date.now()}-${Math
          .random()
          .toString(36)
          .slice(2, 10)}`;

        toast(
          response.data
            ?.message ||
            'درخواست ثبت شد ✅',

          'success'
        );

        await queryClient
          .invalidateQueries({
            queryKey:
              ['sub-status'],
          });

        queryClient
          .invalidateQueries({
            queryKey:
              ['gifts-history'],
          });
      },

      onError: (error) =>
        toast(
          error?.response
            ?.data
            ?.detail ||
            'ثبت رسید انجام نشد',

          'error'
        ),
    });


  const selectPlan = (plan) => {
    haptic('light');

    setSelectedId(
      plan.id
    );

    setDiscountCode('');
    setDiscount(null);
    setReceipt(null);
    setAccepted(false);
    setResult(null);
  };


  const receiptPreview =
    useMemo(
      () =>
        receipt
          ? URL.createObjectURL(
              receipt
            )
          : null,

      [receipt]
    );


  const canSubmit =
    Boolean(selectedPlan) &&
    accepted &&
    !pending &&
    (
      free ||
      Boolean(receipt)
    );


  if (isLoading) {
    return (
      <>
        <Header title="اشتراک ویژه" />

        <main className="page">
          <SubscriptionSkeleton />
        </main>
      </>
    );
  }


  return (
    <>
      <Header
        title="اشتراک ویژه"
        subtitle={
          'پلن، پرداخت و تاریخچه رسیدها'
        }
      />

      <main className="page fade-up">
        {isError ? (
          <div className="empty card">
            دریافت اطلاعات اشتراک انجام
            نشد.

            <button
              className="btn btn-p"
              style={{
                marginTop:
                  12,
              }}
              onClick={() =>
                refetch()
              }
            >
              تلاش دوباره
            </button>
          </div>
        ) : (
          <div
            style={{
              display:
                'grid',

              gap: 'var(--sp-4)',
            }}
          >
            <section
              className={
                'card card-glow'
              }
              style={{
                padding:
                  18,

                background:
                  data?.active
                    ? 'linear-gradient(145deg,var(--soft-ok),var(--surf-card))'
                    : 'linear-gradient(145deg,var(--soft-acc-deep),var(--surf-card) 55%,var(--soft-pur))',
              }}
            >
              <div
                style={{
                  display:
                    'flex',

                  alignItems:
                    'center',

                  gap:
                    13,
                }}
              >
                <span
                  style={{
                    display:
                      'grid',

                    width:
                      58,

                    height:
                      58,

                    placeItems:
                      'center',

                    borderRadius: 'var(--r-lg)',

                    background:
                      data?.active
                        ? 'var(--soft-ok)'
                        : 'var(--grad-brand)',

                    fontSize:
                      28,
                  }}
                >
                  {data?.active
                    ? '💎'
                    : '🚀'}
                </span>

                <div
                  style={{
                    flex:
                      1,
                  }}
                >
                  <div
                    style={{
                      color:
                        'var(--txm)',

                      fontSize: 'var(--fs-cap)',
                    }}
                  >
                    {data?.active
                      ? 'اشتراک فعال شما'
                      : 'ارتقای حساب هامزیار'}
                  </div>

                  <b
                    style={{
                      display:
                        'block',

                      color:
                        data?.active
                          ? 'var(--ok)'
                          : 'var(--tx)',

                      fontSize: 'var(--fs-xl)',

                      marginTop:
                        2,
                    }}
                  >
                    {data?.active
                      ? data.plan_name ||
                        'اشتراک ویژه'

                      : 'دسترسی کامل به امکانات'}
                  </b>

                  <div
                    style={{
                      color:
                        'var(--tx2)',

                      fontSize: 'var(--fs-cap)',

                      marginTop:
                        3,
                    }}
                  >
                    {data?.active
                      ? `${
                          number(
                            data.days_left
                          )
                        } روز باقی‌مانده • تا ${
                          data.expires ||
                          '—'
                        }`

                      : 'پلن مناسب را انتخاب و رسید پرداخت را ارسال کنید.'}
                  </div>
                </div>

                {data?.active && (
                  <span className="badge b-grn">
                    فعال
                  </span>
                )}
              </div>
            </section>


            {pending && (
              <section
                className="card"
                style={{
                  display:
                    'flex',

                  gap: 'var(--sp-3)',

                  borderColor:
                    'var(--bd-warn)',

                  background:
                    'var(--soft-warn)',
                }}
              >
                <span
                  style={{
                    fontSize:
                      24,
                  }}
                >
                  ⏳
                </span>

                <div>
                  <b
                    style={{
                      color:
                        'var(--warn)',
                    }}
                  >
                    یک رسید در انتظار بررسی
                    دارید
                  </b>

                  <div
                    style={{
                      color:
                        'var(--txm)',

                      fontSize: 'var(--fs-cap)',

                      marginTop:
                        3,
                    }}
                  >
                    تا تعیین وضعیت این رسید،
                    امکان ارسال رسید جدید
                    وجود ندارد.
                  </div>
                </div>
              </section>
            )}


            {result && (
              <section
                className="card"
                style={{
                  borderColor:
                    'var(--bd-ok)',
                }}
              >
                <div className="sec-title">
                  ✅ عملیات موفق
                </div>

                <div
                  style={{
                    color:
                      'var(--tx2)',

                    fontSize: 'var(--fs-cap)',

                    lineHeight:
                      1.8,
                  }}
                >
                  {result.message}
                </div>

                {result.payment_id && (
                  <span
                    className="badge b-gray"
                    style={{
                      marginTop: 'var(--sp-2)',
                    }}
                  >
                    شناسه{' '}

                    {result.payment_id}
                  </span>
                )}
              </section>
            )}


            {/* 🌊 GIFT — پنل خرید هدیه */}
            <section className="card">
              <div className="sec-title">
                🎁 اشتراک هدیه
              </div>

              <div
                style={{
                  color: 'var(--tx2)',
                  fontSize: 'var(--fs-cap)',
                  lineHeight: 1.8,
                }}
              >
                می‌خواهی اشتراک را برای دانشجوی
                دیگری بخری؟ حالت هدیه را روشن کن،
                گیرنده را انتخاب کن و مثل خرید عادی
                رسید بفرست. اشتراک فقط بعد از تأیید
                مدیریت و برای گیرنده فعال می‌شود.
              </div>

              <button
                type="button"
                className={
                  giftMode ? 'btn btn-pri' : 'btn'
                }
                style={{ marginTop: 8 }}
                onClick={() => {
                  haptic('light');
                  setGiftMode(!giftMode);
                  setGiftTo(null);
                  setGiftQuery('');
                  setGiftMessage('');
                }}
              >
                {giftMode
                  ? '✅ حالت هدیه روشن است (خاموش کردن)'
                  : '🎁 خرید هدیه برای یک دوست'}
              </button>

              {giftMode && (
                <div
                  style={{
                    marginTop: 10,
                    display: 'grid',
                    gap: 8,
                  }}
                >
                  {giftTo ? (
                    <div
                      className="card"
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent:
                          'space-between',
                        gap: 8,
                      }}
                    >
                      <span
                        style={{
                          color: 'var(--tx1)',
                          fontSize: 'var(--fs-sm)',
                        }}
                      >
                        🎯 {giftTo.name}
                        {giftTo.username
                          ? ` (@${giftTo.username})`
                          : ''}
                      </span>

                      <button
                        type="button"
                        className="btn btn-xs"
                        onClick={() => setGiftTo(null)}
                      >
                        تغییر
                      </button>
                    </div>
                  ) : (
                    <>
                      <input
                        className="inp"
                        placeholder={
                          'جست‌وجوی گیرنده با نام یا @یوزرنیم…'
                        }
                        value={giftQuery}
                        onChange={(event) =>
                          setGiftQuery(event.target.value)
                        }
                      />

                      <RecipientResults
                        q={giftQuery}
                        onPick={(u) => {
                          setGiftTo(u);
                          setGiftQuery('');
                        }}
                      />
                    </>
                  )}

                  {giftTo && (
                    <textarea
                      className="inp"
                      rows={2}
                      maxLength={300}
                      placeholder={
                        'پیام دلخواه همراه هدیه (اختیاری، حداکثر ۳۰۰ نویسه)'
                      }
                      value={giftMessage}
                      onChange={(event) =>
                        setGiftMessage(event.target.value)
                      }
                    />
                  )}
                </div>
              )}
            </section>


            <section>
              <div className="sec-title">
                💳 انتخاب پلن
              </div>

              <div
                style={{
                  display:
                    'grid',

                  gap:
                    9,
                }}
              >
                {plans.length ===
                0 ? (
                  <div className="empty card">
                    پلن فعالی وجود ندارد.
                  </div>
                ) : (
                  plans.map(
                    (plan) => {
                      const chosen =
                        selectedId ===
                        plan.id;

                      return (
                        <button
                          type="button"
                          key={plan.id}
                          className={
                            'card card-tap'
                          }
                          disabled={
                            pending
                          }
                          onClick={() =>
                            selectPlan(
                              plan
                            )
                          }
                          style={{
                            display:
                              'flex',

                            alignItems:
                              'center',

                            width:
                              '100%',

                            gap:
                              11,

                            textAlign:
                              'right',

                            borderColor:
                              chosen
                                ? 'var(--acc)'
                                : 'var(--bd)',

                            boxShadow:
                              chosen
                                ? 'var(--shd-glow)'
                                : 'var(--shd-1)',

                            background:
                              chosen
                                ? 'linear-gradient(145deg,var(--soft-acc),var(--surf-card))'
                                : undefined,
                          }}
                        >
                          <span
                            style={{
                              display:
                                'grid',

                              width:
                                47,

                              height:
                                47,

                              placeItems:
                                'center',

                              borderRadius:
                                15,

                              background:
                                chosen
                                  ? 'var(--grad-brand)'
                                  : 'var(--elev)',

                              fontSize:
                                21,
                            }}
                          >
                            {chosen
                              ? '✓'
                              : '💠'}
                          </span>

                          <span
                            style={{
                              flex:
                                1,
                            }}
                          >
                            <b>
                              {plan.name ||
                                'پلن اشتراک'}
                            </b>

                            <span
                              style={{
                                display:
                                  'block',

                                color:
                                  'var(--txm)',

                                fontSize: 'var(--fs-cap)',

                                marginTop:
                                  3,
                              }}
                            >
                              {number(
                                plan.days
                              )}{' '}

                              روز دسترسی
                            </span>
                          </span>

                          <b
                            style={{
                              color:
                                chosen
                                  ? 'var(--acc2)'
                                  : 'var(--tx)',

                              fontSize: 'var(--fs-sm)',
                            }}
                          >
                            {money(
                              plan.price
                            )}
                          </b>
                        </button>
                      );
                    }
                  )
                )}
              </div>
            </section>


            {selectedPlan &&
              !pending && (
              <section
                className={
                  'card card-glow'
                }
                style={{
                  display:
                    'grid',

                  gap: 'var(--sp-3)',
                }}
              >
                <div className="sec-title">
                  🧾 تکمیل پرداخت
                </div>

                <div
                  style={{
                    padding:
                      '10px 11px',

                    background:
                      'var(--soft-mut)',

                    borderRadius: 'var(--r-md)',
                  }}
                >
                  <div
                    style={{
                      display:
                        'flex',

                      justifyContent:
                        'space-between',

                      fontSize: 'var(--fs-cap)',
                    }}
                  >
                    <span>
                      پلن
                    </span>

                    <b>
                      {selectedPlan.name}
                    </b>
                  </div>

                  <div
                    style={{
                      display:
                        'flex',

                      justifyContent:
                        'space-between',

                      marginTop: 'var(--sp-2)',

                      fontSize: 'var(--fs-cap)',
                    }}
                  >
                    <span>
                      مبلغ
                    </span>

                    <b>
                      {discount ? (
                        <>
                          <s
                            style={{
                              color:
                                'var(--txm)',
                            }}
                          >
                            {money(
                              selectedPlan
                                .price
                            )}
                          </s>

                          {' '}

                          <span
                            style={{
                              color:
                                'var(--ok)',
                            }}
                          >
                            {money(
                              finalPrice
                            )}
                          </span>
                        </>
                      ) : (
                        money(
                          selectedPlan
                            .price
                        )
                      )}
                    </b>
                  </div>
                </div>


                <div
                  style={{
                    display:
                      'flex',

                    gap: 'var(--sp-2)',
                  }}
                >
                  <input
                    className="inp"
                    value={
                      discountCode
                    }
                    maxLength={40}
                    onChange={(event) => {
                      setDiscountCode(
                        event.target
                          .value
                          .toUpperCase()
                      );

                      setDiscount(null);
                    }}
                    placeholder={
                      'کد تخفیف (اختیاری)'
                    }
                  />

                  <button
                    className={
                      'btn btn-dark'
                    }
                    disabled={
                      !discountCode
                        .trim() ||
                      discountMutation
                        .isPending
                    }
                    onClick={() =>
                      discountMutation
                        .mutate()
                    }
                  >
                    {discountMutation
                      .isPending ? (
                      <Spinner
                        size={14}
                      />
                    ) : (
                      'اعمال'
                    )}
                  </button>
                </div>


                {discount && (
                  <div
                    className="badge b-grn"
                    style={{
                      justifyContent:
                        'center',

                      padding: 'var(--sp-2)',
                    }}
                  >
                    {discount.percent}٪
                    تخفیف؛ مبلغ نهایی{' '}

                    {money(
                      discount.final_price
                    )}
                  </div>
                )}


                {!free && (
                  <>
                    <div
                      style={{
                        padding:
                          '11px',

                        textAlign:
                          'center',

                        background:
                          'var(--soft-acc)',

                        border:
                          '1px dashed var(--bdg)',

                        borderRadius: 'var(--r-md)',
                      }}
                    >
                      <div
                        style={{
                          color:
                            'var(--txm)',

                          fontSize: 'var(--fs-cap)',
                        }}
                      >
                        واریز به شماره کارت
                      </div>

                      <div
                        style={{
                          direction:
                            'ltr',

                          color:
                            'var(--acc2)',

                          fontSize: 'var(--fs-lg)',

                          fontWeight:
                            900,

                          letterSpacing:
                            1.5,

                          marginTop: 'var(--sp-1)',
                        }}
                      >
                        {data?.payment
                          ?.card_number ||
                          '—'}
                      </div>

                      <div
                        style={{
                          color:
                            'var(--tx2)',

                          fontSize: 'var(--fs-cap)',

                          marginTop:
                            3,
                        }}
                      >
                        به نام{' '}

                        {data?.payment
                          ?.card_owner ||
                          '—'}
                      </div>
                    </div>

                    <label
                      style={{
                        color:
                          'var(--txm)',

                        fontSize: 'var(--fs-cap)',
                      }}
                    >
                      تصویر رسید؛ حداکثر
                      ۱۰ مگابایت
                    </label>

                    <input
                      className="inp"
                      type="file"
                      accept="image/*"
                      onChange={(event) => {
                        const file =
                          event.target
                            .files?.[0] ||
                          null;

                        if (
                          file &&
                          file.size >
                            10 *
                            1024 *
                            1024
                        ) {
                          toast(
                            'حجم رسید بیشتر از ۱۰ مگابایت است',
                            'error'
                          );

                          event.target.value =
                            '';

                          return;
                        }

                        setReceipt(file);
                      }}
                    />

                    {receiptPreview && (
                      <img
                        src={
                          receiptPreview
                        }
                        alt={
                          'پیش‌نمایش رسید'
                        }
                        style={{
                          width:
                            '100%',

                          maxHeight:
                            230,

                          objectFit:
                            'contain',

                          background:
                            'var(--elev)',

                          border:
                            '1px solid var(--bd)',

                          borderRadius: 'var(--r-md)',
                        }}
                      />
                    )}
                  </>
                )}


                {free && (
                  <div
                    style={{
                      padding:
                        12,

                      color:
                        'var(--ok)',

                      textAlign:
                        'center',

                      background:
                        'var(--soft-ok)',

                      borderRadius: 'var(--r-md)',
                    }}
                  >
                    🎁 این پلن با کد تخفیف
                    رایگان است و نیازی به
                    رسید ندارد.
                  </div>
                )}


                <label className="menu-row">
                  <span
                    style={{
                      flex:
                        1,
                    }}
                  >
                    <b>
                      قوانین استفاده را
                      خواندم و قبول دارم
                    </b>

                    <span
                      style={{
                        display:
                          'block',

                        color:
                          'var(--txm)',

                        fontSize: 'var(--fs-cap)',
                      }}
                    >
                      محتوا فقط برای استفاده
                      شخصی است.
                    </span>
                  </span>

                  <span className="toggle-wrap">
                    <input
                      type="checkbox"
                      checked={
                        accepted
                      }
                      onChange={(
                        event
                      ) =>
                        setAccepted(
                          event.target
                            .checked
                        )
                      }
                    />

                    <span className="toggle-sl" />
                  </span>
                </label>


                <button
                  className={
                    'btn btn-p btn-full'
                  }
                  disabled={
                    !canSubmit ||
                    buyMutation
                      .isPending
                  }
                  onClick={async () => {
                    const acceptedBuy =
                      await confirmAction(
                        free
                          ? 'اشتراک رایگان فعال شود؟'
                          : 'رسید برای بررسی ارسال شود؟'
                      );

                    if (
                      acceptedBuy
                    ) {
                      buyMutation
                        .mutate();
                    }
                  }}
                >
                  {buyMutation
                    .isPending ? (
                    <Spinner size={16} />
                  ) : free ? (
                    '🎁 فعال‌سازی رایگان'
                  ) : (
                    '📤 ارسال رسید'
                  )}
                </button>
              </section>
            )}


            {/* 🌊 GIFT — تاریخچه‌ی هدیه‌ها */}
            {(giftsQuery.data?.data?.as_payer?.length ||
              giftsQuery.data?.data?.as_recipient
                ?.length) && (
              <section>
                <div className="sec-title">
                  🎁 هدیه‌های من
                </div>

                <div
                  style={{ display: 'grid', gap: 8 }}
                >
                  {(
                    giftsQuery.data?.data?.as_payer ||
                    []
                  ).map((item) => {
                    const [label, badge, icon] =
                      PAYMENT_STATUS[item.status] || [
                        item.status,
                        'b-gray',
                        '🎁',
                      ];

                    return (
                      <article
                        key={`p-${item.id}`}
                        className="card"
                      >
                        <div
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: 'var(--sp-3)',
                          }}
                        >
                          <span
                            style={{
                              display: 'grid',
                              width: 42,
                              height: 42,
                              placeItems: 'center',
                              borderRadius:
                                'var(--r-md)',
                              background:
                                'var(--soft-mut)',
                              fontSize: 'var(--fs-xl)',
                            }}
                          >
                            {icon}
                          </span>

                          <div style={{ flex: 1 }}>
                            <b>
                              هدیه به کاربر{' '}
                              {item.to}
                            </b>

                            <div
                              style={{
                                color: 'var(--txm)',
                                fontSize:
                                  'var(--fs-cap)',
                                marginTop: 3,
                              }}
                            >
                              {item.plan_name ||
                                'اشتراک'}{' '}
                              • {money(item.final_price)}
                            </div>
                          </div>

                          <span
                            className={`badge ${badge}`}
                          >
                            {label}
                          </span>
                        </div>

                        {item.message && (
                          <div
                            style={{
                              marginTop: 8,
                              padding: '8px 9px',
                              color: 'var(--tx2)',
                              background:
                                'var(--soft-mut)',
                              borderRadius:
                                'var(--r-sm)',
                              fontSize:
                                'var(--fs-cap)',
                            }}
                          >
                            💬 {item.message}
                          </div>
                        )}
                      </article>
                    );
                  })}

                  {(
                    giftsQuery.data?.data
                      ?.as_recipient || []
                  ).map((item) => (
                    <article
                      key={`r-${item.id}`}
                      className="card"
                    >
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 'var(--sp-3)',
                        }}
                      >
                        <span
                          style={{
                            display: 'grid',
                            width: 42,
                            height: 42,
                            placeItems: 'center',
                            borderRadius:
                              'var(--r-md)',
                            background:
                              'var(--soft-mut)',
                            fontSize: 'var(--fs-xl)',
                          }}
                        >
                          🎁
                        </span>

                        <div style={{ flex: 1 }}>
                          <b>
                            هدیه از کاربر{' '}
                            {item.from}
                          </b>

                          <div
                            style={{
                              color: 'var(--txm)',
                              fontSize:
                                'var(--fs-cap)',
                              marginTop: 3,
                            }}
                          >
                            {item.plan_name ||
                              'اشتراک'}
                            {item.activated_at
                              ? ' • فعال شد ✅'
                              : ''}
                          </div>
                        </div>

                        <span
                          className={`badge ${
                            item.status === 'approved'
                              ? 'b-grn'
                              : 'b-gray'
                          }`}
                        >
                          {item.status === 'approved'
                            ? 'فعال'
                            : '—'}
                        </span>
                      </div>

                      {item.message && (
                        <div
                          style={{
                            marginTop: 8,
                            padding: '8px 9px',
                            color: 'var(--tx2)',
                            background:
                              'var(--soft-mut)',
                            borderRadius:
                              'var(--r-sm)',
                            fontSize: 'var(--fs-cap)',
                          }}
                        >
                          💬 {item.message}
                        </div>
                      )}
                    </article>
                  ))}
                </div>
              </section>
            )}


            <section>
              <div className="sec-title">
                🕘 تاریخچه پرداخت‌ها
              </div>

              {payments.length ===
                0 ? (
                <div className="empty card">
                  هنوز پرداختی ثبت نشده است.
                </div>
              ) : (
                <div
                  style={{
                    display:
                      'grid',

                    gap:
                      8,
                  }}
                >
                  {payments.map(
                    (item) => {
                      const [
                        label,
                        badge,
                        icon,
                      ] = (
                        PAYMENT_STATUS[
                          item.status
                        ] || [
                          item
                            .status_label,

                          'b-gray',

                          '📌',
                        ]
                      );

                      return (
                        <article
                          key={item.id}
                          className="card"
                        >
                          <div
                            style={{
                              display:
                                'flex',

                              alignItems:
                                'center',

                              gap: 'var(--sp-3)',
                            }}
                          >
                            <span
                              style={{
                                display:
                                  'grid',

                                width:
                                  42,

                                height:
                                  42,

                                placeItems:
                                  'center',

                                borderRadius: 'var(--r-md)',

                                background:
                                  'var(--soft-mut)',

                                fontSize: 'var(--fs-xl)',
                              }}
                            >
                              {icon}
                            </span>

                            <div
                              style={{
                                flex:
                                  1,
                              }}
                            >
                              <b>
                                {item
                                  .plan_name ||
                                  'اشتراک'}
                              </b>

                              <div
                                style={{
                                  color:
                                    'var(--txm)',

                                  fontSize: 'var(--fs-cap)',

                                  marginTop:
                                    3,
                                }}
                              >
                                {money(
                                  item
                                    .final_price
                                )}

                                {' • '}

                                {item
                                  .submitted_at ||
                                  '—'}
                              </div>
                            </div>

                            <span
                              className={`badge ${badge}`}
                            >
                              {label}
                            </span>
                          </div>

                          {item.review_note && (
                            <div
                              style={{
                                marginTop:
                                  8,

                                padding:
                                  '8px 9px',

                                color:
                                  item.status ===
                                  'rejected'
                                    ? 'var(--err)'
                                    : 'var(--tx2)',

                                background:
                                  'var(--soft-mut)',

                                borderRadius: 'var(--r-sm)',

                                fontSize: 'var(--fs-cap)',
                              }}
                            >
                              یادداشت مدیریت:{' '}

                              {
                                item.review_note
                              }
                            </div>
                          )}
                        </article>
                      );
                    }
                  )}
                </div>
              )}
            </section>
          </div>
        )}
      </main>
    </>
  );
}
