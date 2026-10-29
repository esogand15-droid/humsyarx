# HamsYar Unified Design System

## Overview

This document defines the unified design system for the entire HamsYar ecosystem. All visual properties across the Student Web App, Admin Panel, and Telegram Mini App are derived from this single source of truth.

**Core Principle:** Consistency in token naming and semantic meaning, with environment-appropriate values.

---

## Architecture

```
┌─────────────────────────────────────────┐
│   Unified Design Tokens (hym-*)         │
│   Same names, environment values        │
├─────────────────────────────────────────┤
│  Student App  │  Mini App  │  Admin     │
│  Light/Dark   │  Dark-first│  Dark navy │
│  Warm paper   │  Deep navy │  Midnight  │
├─────────────────────────────────────────┤
│   Legacy Aliases (backward compat)      │
│   --paper, --brand, --ink, etc.         │
└─────────────────────────────────────────┘
```

---

## Token Categories

### 1. Primitives (`--hym-*`)

| Category | Tokens | Usage |
|----------|--------|-------|
| **Brand** | `--hym-brand-50` to `900` | Royal blue scale |
| **Accent** | `--hym-teal-50` to `900` | Cyan/teal scale |
| **Warmth** | `--hym-amber-50` to `900` | Amber/gold scale |
| **Success** | `--hym-success-50` to `900` | Emerald green |
| **Warning** | `--hym-warning-50` to `900` | Amber/yellow |
| **Danger** | `--hym-danger-50` to `900` | Rose/red |
| **Neutral** | `--hym-neutral-0` to `950` | Grey scale |

### 2. Semantic Tokens

#### Surfaces
| Token | Light | Dark (Student) | Mini App | Admin |
|-------|-------|----------------|----------|-------|
| `--hym-bg-page` | `#F7F3EA` | `#14110C` | `#070B14` | `#090f1f` |
| `--hym-bg-surface` | `#FFFDF7` | `#1B1711` | `#0A1020` | `#0c1527` |
| `--hym-bg-surface-raised` | `#FFFFFF` | `#241F17` | `#101827` | `#111c34` |
| `--hym-bg-surface-inset` | `#EFE8DA` | `#0C0A09` | `#05080F` | `#070b14` |

#### Text
| Token | Light | Dark (Student) | Mini App | Admin |
|-------|-------|----------------|----------|-------|
| `--hym-text-primary` | `#1B1712` | `#F0EADE` | `#F8FAFC` | `#eaf0fe` |
| `--hym-text-secondary` | `#4A4339` | `#BCB2A1` | `#B4C0D4` | `#a3b4d8` |
| `--hym-text-muted` | `#7A7264` | `#8A8071` | `#8296B3` | `#7184ac` |

#### Brand Semantic
| Token | Light | Dark | Mini App | Admin |
|-------|-------|------|----------|-------|
| `--hym-brand-default` | `#1740B8` | `#6E93FF` | `#3B82F6` | `#4db8ff` |
| `--hym-brand-hover` | `#10308F` | `#4C74E8` | `#2563EB` | `#38a8f5` |
| `--hym-brand-subtle` | `#E7EBFA` | `rgba(110,147,255,.16)` | `rgba(59,130,246,.12)` | `rgba(77,184,255,.12)` |

### 3. Spacing Scale

```
--hym-space-1:  4px
--hym-space-2:  8px
--hym-space-3:  12px
--hym-space-4:  16px
--hym-space-5:  20px
--hym-space-6:  24px
--hym-space-8:  32px
--hym-space-10: 40px
--hym-space-12: 48px
--hym-space-16: 64px
--hym-space-20: 80px
--hym-space-24: 96px
```

### 4. Border Radius

```
--hym-radius-sm:   6px   (controls, chips)
--hym-radius-md:   10px  (buttons, inputs)
--hym-radius-lg:   14px  (cards)
--hym-radius-xl:   20px  (panels, sheets)
--hym-radius-2xl:  28px  (modals)
--hym-radius-pill: 999px (badges, pills)
```

### 5. Shadows

| Token | Light | Dark |
|-------|-------|------|
| `--hym-shadow-sm` | `0 1px 2px rgba(27,23,18,.06)` | `0 1px 2px rgba(0,0,0,.40)` |
| `--hym-shadow-md` | `0 1px 2px ... + 0 12px 28px ...` | `0 1px 3px ... + 0 14px 30px ...` |
| `--hym-shadow-lg` | `0 4px 6px ... + 0 20px 40px ...` | `0 4px 8px ... + 0 24px 48px ...` |

### 6. Typography

**Font Family:** `Vazirmatn`, system-ui, Tahoma, sans-serif

**Scale:**
- Display: 26px / weight 800
- Page Title: 19px / weight 800
- Section Title: 15.5px / weight 700
- Body: 15px / weight 400 / line-height 1.85
- Small: 12.5px / weight 400
- Caption: 11px / weight 400

### 7. Motion

```
--hym-ease-default: cubic-bezier(.32, .72, 0, 1)
--hym-ease-spring:  cubic-bezier(.34, 1.56, .64, 1)
--hym-ease-out:     cubic-bezier(.22, 1, .36, 1)

--hym-duration-fast:   150ms
--hym-duration-normal: 220ms
--hym-duration-slow:   340ms
```

### 8. Z-Index Scale

```
--hym-z-base:    0
--hym-z-sticky:  10
--hym-z-nav:     20
--hym-z-sheet:   30
--hym-z-toast:   40
--hym-z-overlay: 50
--hym-z-modal:   60
```

---

## Environment Adapters

### Student Web App (blue, unified — `/app`)
- **File:** `miniapp/src/styles/tokens.css`
- **Default:** Dark navy (`#060B16`) — همان هویت مینی‌اپ
- **Light mode:** `html[data-theme="light"]`
- **Density:** Comfortable
- **Max width:** 720px on wide screens (`--content-w`, centered)
- **Note:** نسخهٔ «کروم» (`apps/student`) در موج v3 حذف شد؛ این تنها
  رابط دانشجو است — چه داخل تلگرام، چه در مرورگر (PWA).

### Telegram Mini App
- **File:** `miniapp/src/styles/tokens.css`
- **Default:** Dark (Telegram WebView optimized)
- **Density:** Comfortable (touch-optimized)
- **Max width:** 500px
- **Safe areas:** Respects `env(safe-area-inset-*)`

### Admin Panel
- **File:** `webadmin/src/tokens.css`
- **Default:** Dark navy (data-dense)
- **Density:** Compact (smaller padding, tighter radius)
- **Max width:** 1680px

---

## Legacy Compatibility

All environments maintain legacy aliases for backward compatibility:

```css
--paper  → --hym-bg-page
--ink    → --hym-text-primary
--brand  → --hym-brand-default
--sh-1   → --hym-shadow-sm
--r-lg   → --hym-radius-xl
/* etc. */
```

Existing components using legacy tokens continue to work. New components should use `--hym-*` tokens.

---

## Component Patterns

### Button
```css
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--hym-space-2);
  height: var(--hym-space-10); /* 40px default, 48px comfortable */
  padding: 0 var(--hym-space-5);
  border-radius: var(--hym-radius-md);
  background: var(--hym-brand-default);
  color: var(--hym-text-on-brand);
  font-size: 14px;
  font-weight: 700;
  transition: background var(--hym-duration-fast) var(--hym-ease-default);
}
.btn:hover { background: var(--hym-brand-hover); }
.btn:active { transform: scale(.985); }
```

### Card
```css
.card {
  background: var(--hym-bg-surface);
  border: 1px solid var(--hym-border-default);
  border-radius: var(--hym-radius-lg);
  padding: var(--hym-space-4);
  box-shadow: var(--hym-shadow-sm);
}
```

### Input
```css
.input {
  height: 54px;
  border-radius: var(--hym-radius-md);
  border: 1px solid var(--hym-border-strong);
  background: var(--hym-bg-surface);
  padding: 0 var(--hym-space-4);
  color: var(--hym-text-primary);
  transition: border-color var(--hym-duration-fast), box-shadow var(--hym-duration-fast);
}
.input:focus {
  outline: 0;
  border-color: var(--hym-brand-default);
  box-shadow: var(--hym-focus-ring);
}
```

---

## Accessibility

- **Contrast:** Minimum 4.5:1 for normal text, 3:1 for large text
- **Focus:** Visible focus rings on all interactive elements (`:focus-visible`)
- **Motion:** `prefers-reduced-motion` respected globally
- **RTL:** All environments are RTL-first (direction: rtl)
- **Touch:** Minimum 44px touch targets

---

## Migration Guide

### From Legacy Tokens
Replace incrementally:

```css
/* Before */
.my-component {
  background: var(--paper-2);
  color: var(--ink-2);
}

/* After */
.my-component {
  background: var(--hym-bg-surface);
  color: var(--hym-text-secondary);
}
```

### Creating Environment-Specific Overrides
```css
/* In environment adapter */
:root {
  --hym-brand-default: #your-brand-color;
  --hym-bg-page: #your-page-bg;
}
```

---

## File Locations

| Environment | Token File | Base Styles | Component Styles |
|-------------|-----------|-------------|------------------|
| Student App (blue mini-app) | `miniapp/src/styles/tokens.css` | `globals.css` | `v3-home.css` |
| Mini App | `miniapp/src/styles/tokens.css` | `globals.css` | Component JSX |
| Admin Panel | `webadmin/src/tokens.css` | `styles.css` | `ui.jsx` |

---

## Version

**HamsYar Unified Design System v1.0**
Last updated: 2025
