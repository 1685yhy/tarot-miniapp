# DESIGN COUNCIL PRD: 星光映照 (Starlight Reflection)

**Council convened:** 2026-07-30
**Council members:** Don Norman (Cognitive Science), Jony Ive (Design), Steve Jobs (Product Vision)
**Status:** Final — actionable for development

---

## Table of Contents

1. Product Overview
2. User Personas
3. Core Flows
4. Page-by-Page Specification
5. Visual Design System
6. Interaction Pattern Library
7. Error & Edge Case Strategy
8. Performance Requirements
9. Accessibility Requirements
10. Implementation Roadmap

---

## 1. Product Overview

### 1.1 Elevator Pitch

星光映照 is a WeChat Mini Program that delivers daily tarot-based self-reflection, powered by AI interpretation. It is not a fortune-telling app. It is a mirror—helping users see what they already know but haven't articulated. The experience should feel like lying on grass at midnight, gazing at the stars, having a quiet conversation with someone who listens without judgment.

### 1.2 Target User

Women aged 20-35 in China, interested in self-discovery, spirituality, and journaling. They are not necessarily tarot experts. They come for emotional resonance, not predictive accuracy. They are price-sensitive but willing to pay for something that feels authentic and emotionally intelligent.

### 1.3 Core Principles (from Council Verdicts)

1. **The card is the hero.** Every screen radiates from the card. Nothing on the home page should visually compete with the daily card.
2. **Monetization must not corrupt the emotional experience.** Users should feel seen, not sold to. Membership prompts must be restrained and contextually appropriate.
3. **Remove, remove, remove.** Every element must justify its existence. If you can delete something and the experience improves, delete it.
4. **Progressive disclosure.** Show the user only what they need at each step. Reveal complexity gradually.
5. **The user chooses their interpreter.** Personas are not random assignments. The user selects who speaks to them.

### 1.4 Critical Design Constraints

- WeChat Mini Program platform (WXML/WXSS/WXS, no DOM access, limited CSS features)
- No CSS Grid support (use Flexbox)
- No `conic-gradient` or advanced CSS mask (use alternative visual approaches)
- Dark theme is primary and only theme (deep indigo background)
- Load time target: under 2 seconds to interactive on 4G
- Bundle size target: under 2MB total

---

## 2. User Personas

### 2.1 Primary: Xiao Ling (小玲)

- **Age:** 27
- **Occupation:** Marketing manager, Shanghai
- **Behavior:** Opens the app every morning before work. Draws her daily card during her subway commute. Reads the interpretation. Sometimes writes a diary entry if something resonates. Does NOT browse the encyclopedia. Does NOT participate in community features.
- **Needs:** Speed (she has 5 minutes), emotional warmth (her job is high-pressure), consistency (she wants a daily ritual).
- **Pain points with current version:** Home page takes too long to process. Too many options before she can draw her card. Membership prompts feel like a cold shower.

### 2.2 Secondary: Mei (美美)

- **Age:** 22
- **Occupation:** University student, Beijing
- **Behavior:** Uses the app in the evening when she's stressed about exams or relationships. Uses more spread types. Writes diary entries with photos. Occasionally shares readings with friends. Browsed the encyclopedia once.
- **Needs:** Depth (she wants detailed interpretations), exploration (she tries different spreads), social validation (sharing makes the experience feel real).
- **Pain points with current version:** Can't choose her persona. Diary feels disconnected from the reading. Too many features she doesn't use (community, annual report).

### 2.3 Tertiary: Auntie Chen (陈阿姨)

- **Age:** 45
- **Occupation:** Homemaker, Chengdu
- **Behavior:** Uses the app occasionally when friends share readings in WeChat groups. Very low engagement. May not log in. May never write a diary entry.
- **Needs:** Zero friction. Shareable content. No account creation barrier.
- **Pain points with current version:** Onboarding is confusing. Too many buttons. Doesn't understand the navigation.

---

## 3. Core Flows

### 3.1 Primary Flow: Daily Card Ritual (must be 3 taps max)

```
Tap 1: Open app → Daily card appears center screen (pre-draw state with "tap to reveal" animation)
Tap 2: Tap card → Card flips, revealing today's tarot card with name
Tap 3: Tap card again → Brief interpretation appears inline (not a new page)

[Optional] Continue to full reading → One more tap to a clean reading screen
```

**What the current version does wrong:**
- The daily card shares the page with 10 other elements
- The pre-draw state has too many animations (shimmer, sparkle, ripple, glow)
- The post-draw state has too many badges (flipped/unflipped, streak, collection, learned)
- The interpretation requires navigating to a separate page

**What the council recommends:**
- The daily card should occupy the upper 60% of the home page on first visit
- All secondary entries (diary, community, membership, spread grid) should be below the fold
- The card animation should be one elegant flip, not a light show
- Remove the streak badge, collection ring, and "learned" badge from the main card surface
- Move streak and collection data to the profile page

### 3.2 Secondary Flow: Full Reading

```
Step 1: From home page, user selects a spread type (shown as a grid of cards)
Step 2: (Optional) User selects their interpretation persona
Step 3: Three-stage loading animation (shuffle → flip → interpret) — reduced from current duration
Step 4: Reading result page — TL;DR at top, persona badge prominent, interpretation text as hero
Step 5: Below interpretation: optional actions (save, share, diary)
```

**Critical changes from current version:**
- Persona selection MUST happen before the card is drawn, not randomly assigned
- The loading sequence should be 1.5 seconds total (not 5+)
- Quick mode (no loading animation) should be the default on repeat visits
- The interpretation text should be fully visible without scrolling or expanding
- Membership upsells should appear AFTER the user has completed the reading, not during
- Remove the "undo reading" button — undermines the emotional weight of the reading
- Remove the "depth unlock" card — integrate depth into the standard reading

### 3.3 Tertiary Flow: Chat / Follow-up

```
Step 1: From reading result, user taps "追问" (ask more)
Step 2: Chat page loads with persona context bar at top
Step 3: User types question, receives WebSocket-streamed response
Step 4: Free quota bar shows remaining follow-ups (below input, not prominent)
```

**Critical changes:**
- The persona context bar should be more prominent (this is WHO is speaking)
- Remove the membership prompt from the chat footer — show only when user actually exhausts quota
- The empty state should invite conversation, not sell
- Remove the AI disclaimer from every message — show once at the bottom of the reading result page

### 3.4 Monetization Flow (restrained)

```
Not a flow — a single touchpoint:
After the user's 5th free reading (or after the 3rd reading in a session):
  → A SINGLE card appears below the reading result:
     "You've received 5 readings this week. Our members get unlimited access + deeper interpretations.
      Learn more →"
  → That's it. No banners. No animated stars. No pulsing CTAs.
```

---

## 4. Page-by-Page Specification

### 4.1 Home Page (pages/index/index)

**Current problems (from council):**
- 11 interactive entry points competing for attention
- Daily card is visually buried under animations and badges
- Membership prompts interrupt the emotional experience
- No clear hierarchy of importance
- The shooting star easter egg is delightful but has no business on the home page

**Required changes (ordered by priority):**

**P0 — Reorganize content into clear zones:**
- Zone 1 (top 60% of viewport): Daily card ONLY. No badges. No streak. No collection ring. Just the card, its name, and a subtle invitation to tap.
- Zone 2 (scroll below): Quick spread selector (show 2 spread cards max, not 4). "View all" link.
- Zone 3 (further below): Diary entry button (single line, not a card with emoji and arrows).
- Zone 4 (bottom): Free tier status (text only, no progress bar animation). Membership link (text link, not a card).

**P1 — Reduce daily card animation complexity:**
- Remove shimmer sweep effect
- Remove orbiting sparkle dots
- Remove breathing glow overlay (keep subtle border glow)
- Keep card flip animation (this is the ONE moment of delight)
- Keep tap ripple (this provides tactile feedback)
- Card ready state: single gentle pulse animation, not pulsing + breathing + shimmering

**P2 — Consolidate badges:**
- Remove streak badge from card surface (move to profile)
- Remove collection progress ring from card surface (move to encyclopedia or profile)
- Remove "已学习" badge from card surface (replace with simple color shift on card border)
- Keep daily updated/reminder badge (small, below card, text-only)

**P3 — Restrain membership prompts:**
- Remove the animated membership prompt card (the one with 3 stars and twinkle animation)
- Remove the trial expiry banner (integrate into free quota text)
- Move the 9.9 yuan CTA to a secondary position (after the user's first spread selection, not before)
- Keep the free quota bar as text only

**Layout template (top to bottom):**

```
┌────────────────────────────────┐
│  [Parallax stars — very subtle]│
│                                │
│           [ 品牌名称 ]          │
│        星光映照 · 每日一牌       │
│                                │
│       ┌────────────────┐       │
│       │                │       │
│       │   DAILY CARD   │       │
│       │   (tap to      │       │
│       │    reveal)     │       │
│       │                │       │
│       └────────────────┘       │
│   [✓ 今日运势已更新]             │
│                                │
│  ──── 以上是首屏 ────           │
│  (以下需要滚动)                  │
│                                │
│  快速解读                        │
│  ┌──────┐ ┌──────┐            │
│  │ 三牌  │ │ 恋人  │  → 更多   │
│  └──────┘ └──────┘            │
│                                │
│  记录今天  →                     │
│                                │
│  免费解读 0/5 · 明日重置         │
│  升级会员 →                     │
└────────────────────────────────┘
```

### 4.2 Reading Result (pages/reading-result/reading-result)

**Current problems:**
- Interpretation text is collapsed by default (requires tap to expand)
- TL;DR is positioned above the persona badge (wrong order)
- Teaching section, share CTA, reflection card, depth unlock, action cards all compete
- Three-stage loading is too long

**Required changes:**

**P0 — Restructure content hierarchy:**
1. **Top:** Persona badge (prominent — icon + name + description)
2. **Second:** Interpretation text (always expanded, no collapse)
3. **Third:** Action items (checklist form)
4. **Fourth (collapsible):** Card teaching / deep analysis
5. **Bottom:** Share + Save + Diary buttons (in a row, not stacked)

**P1 — Loading sequence changes:**
- Reduce each stage to 0.4 seconds (total 1.2s from current ~4s)
- Quick mode (no loading animation) should be default for repeat visits
- Show a cached/abbreviated reading immediately while the full version loads in background

**P2 — Remove or consolidate:**
- Remove "undo reading" button entirely
- Remove "depth unlock" upsell card
- Remove share CTA card (the share button at the bottom is sufficient)
- Merge reflection card into diary entry button

### 4.3 Chat (pages/chat/chat)

**Current problems:**
- Membership prompt at bottom feels intrusive
- Free quota bar below input creates anxiety
- Persona bar is present but understated

**Required changes:**
- Persona bar should be the first thing the user sees (icon + name + "is listening")
- Free quota bar: show only when user has 1 or fewer remaining follow-ups
- Remove the membership prompt from chat body entirely (show a text link when quota exhausted)
- Streamed response cursor: keep the blinking pipe character
- Failed message retry UX is well-designed — keep as-is

### 4.4 Diary (pages/diary/diary)

**Current problems:**
- Mix of journal entries, mood tracking, weekly AI review, and image sharing
- The weekly review is shown inline and auto-loads, which may surprise users
- The modal create flow is well-designed but the page structure is unclear

**Required changes:**
- Keep the list + modal create pattern (this is well-executed)
- Weekly review should require explicit user action to generate, not auto-load
- Move mood trend chart to a tab or collapsible section (currently takes too much vertical space)
- Remove the floating AI review button (duplicates the review-card header)

### 4.5 Encyclopedia / Profile (not in scope for this PRD deep-dive)

**General guidance from council:**
- Encyclopedia should be searchable, not just browsable
- Profile should consolidate: streak data, collection progress, reading history, membership status
- Remove any upsells from encyclopedia (knowledge should be free)

---

## 5. Visual Design System

### 5.1 Color Palette (KEEP — council-approved)

The current color system is the best-designed part of this product. Do not change it.

| Token | Value | Usage |
|---|---|---|
| `--color-bg` | `#1A1A3E` | Page background |
| `--color-gold` | `#F4D48C` | Primary accent, headings, CTAs |
| `--color-gold-dark` | `#D4B06A` | Secondary gold, pressed states |
| `--color-lavender` | `#B8A9E0` | Secondary text, captions |
| `--color-text-primary` | `#F0EDE8` | Body text |
| `--color-text-tertiary` | `#A098C0` | Muted text, hints |
| `--color-success` | `#7BC6A0` | Positive states, streak badges |
| `--color-error` | `#E87A8A` | Error states |

**One addition:** Add `--color-surface-elevated` for modal/overlay backgrounds to distinguish from regular cards. Currently modals and cards use the same gradient, which flattens visual depth.

### 5.2 Typography (KEEP with minor adjustments)

The type scale is appropriate. One change: the `--font-size-display` at 56rpx for the title is too large for the daily card context. Reduce to 48rpx for hero title, keep 56rpx for splash/brand only.

### 5.3 Spacing (KEEP)

The spacing scale is well-considered. The current page uses `32rpx` padding which is correct for WeChat mini programs.

### 5.4 Starfield & Atmosphere (CONTROVERSIAL — see council split)

**Council conclusion:** KEEP the parallax star layers and nebula glows but REDUCE their visual weight by 50%.

- Reduce star opacity from current values to half
- Remove the shooting star easter egg from the home page (it fires once every 30 seconds for a 200ms flash — users don't see it and it adds CSS weight)
- Keep nebula gradients but remove the rotate animation (the rotation is imperceptible and adds GPU overhead)
- Keep the hero golden radial glow

### 5.5 Card System (CONSOLIDATE)

Current state: 7 card variants (warm, teaching, press, reveal, rise, floating, shimmer).

Target state: 3 card variants
- **Card-default:** For spread grid, diary entries, information cards
- **Card-interactive:** For tappable cards with press feedback (`scale(0.97)` on tap)
- **Card-featured:** For the daily card only — has breathing glow border

This eliminates: card-warm, card-shimmer, card-float, card-rise, card-reveal as separate variants. The featured card absorbs the card-warm gradient and the breathing glow. Everything else gets card-default.

### 5.6 Animation System (SIMPLIFY)

Current state: 20+ named animations across CSS classes.

Target state: 10 animation types maximum.

**Keep:**
- `page-fade-up` (staggered entrance — essential for perceived performance)
- `card-flip` (the card reveal — the single most important animation)
- `ripple-expand` (tap feedback — essential for touch affordance)
- `card-glow-breathe` (subtle life on featured card)
- `sparkle-float` (reduced to 3 particles instead of 6)

**Remove:**
- `stars-drift-slow/mid/close` (starfield doesn't need parallax — static is fine)
- `nebula-rotate` (imperceptible)
- `shooting-star-fly` (remove the easter egg entirely)
- `season-glow`, `season-star` (remove seasonal banner — it's a distraction 11 months of the year)
- `card-shake` (the shuffle animation before daily card draw)
- `card-ready-pulse` (consolidate into card-warm-breathe)

---

## 6. Interaction Pattern Library

### 6.1 Card Tap Pattern

All tappable cards share this behavior:
- `transform: scale(0.97)` on `:active`
- Border color lightens from `rgba(gold, 0.12)` to `rgba(gold, 0.25)` on `:active`
- 200ms transition, ease-out
- No additional hover states (no hover on mobile)
- No ripple on non-daily cards (keep ripple only for the main daily card)

### 6.2 Page Transition Pattern

- Enter: `page-fade-up` (300ms, staggered by section: hero at 0ms, content at 200ms, footer at 400ms)
- Exit: No exit animation (instant — WeChat doesn't reliably support exit transitions)
- Loading: Skeleton with same border-radius and color tokens as the content it replaces
- Error: Full-page error state with icon + message + retry button

### 6.3 Loading Pattern (RECONSIDERED)

Current: 3-stage loading with shuffle, flip, and interpret animations (4+ seconds total).

New:
- **First visit or quick mode (default):** Show skeleton for 800ms, then content. No stage animations.
- **Immersive mode (opt-in):** Single "interpreting..." state with gentle pulse. Max 2 seconds. Skip shuffle and flip stages entirely — they added time without value.
- **Error during loading:** Show current stage + retry option immediately. Do not wait for timeout.

### 6.4 Empty State Pattern

Every content area must have an intentional empty state:
- Diary page: "今天抽到了什么牌？翻开每日一牌，记录此刻心情" — keep current version
- Reading history: "还没有解读记录" with CTA to first reading
- Community: "还没有话题" — but consider removing community entirely if engagement is low

### 6.5 Error State Pattern (KEEP current — well-executed)

The current error states across all pages are consistent and well-designed. Maintain the pattern:
- Icon (or emoji where icons don't load)
- Short error title (e.g., "连接中断" not technical "Network Error")
- Error detail (the actual error message, user-readable)
- Retry button

---

## 7. Error & Edge Case Strategy

### 7.1 Network Errors

- **No network:** Show cached daily card if available. Reading result cannot be cached (server-generated). Show graceful error with retry.
- **Slow network:** Show loading skeleton immediately. Show time-status text in reading result after 8 seconds ("This is taking longer than usual"). Never auto-timeout.
- **API failure:** Show friendly error message. Map all HTTP error codes to human-readable Chinese messages (currently done via `getFriendlyError()` — keep this pattern).

### 7.2 Card Image Errors

Current solution: `binderror` handler shows fallback with card name. This is robust. Extend to all card image components (currently only daily card has this — diary entry cards, reading result cards, encyclopedia cards should all have the same fallback).

### 7.3 Data Inconsistency

Edge cases to handle:
- User has a daily card stored but the card data is corrupted → re-fetch from server
- User draws a card but the API returns an error → show retry, do NOT charge the user's daily quota
- User opens the app offline but the daily card is cached → show cached version, indicate "offline" subtly
- Free quota counter desyncs with server → server is source of truth; local counter is optimistic

### 7.4 State Management

- User membership state: Read from server on every `onShow`, cache for session duration
- Daily card draw state: Read from server, cache locally with date key (to detect "new day")
- Reading history: Local cache with server sync. Limit to 50 items in local storage.
- Diary entries: Server-driven. Local cache for offline reading. Max 200 entries.

---

## 8. Performance Requirements

### 8.1 Load Time Targets

| Metric | Target | Current (estimated) |
|---|---|---|
| First paint | < 1.5s on 4G | ~2.5s |
| Time to interactive | < 2.5s on 4G | ~4s |
| Page transition (tab) | < 500ms | ~800ms |
| Reading result generation | < 3s from tap | ~5-8s |

### 8.2 Bundle Size

| Asset | Current | Target |
|---|---|---|
| Total package | Unknown | < 2MB |
| Image assets | Unknown | < 800KB |
| JS bundles | Unknown | < 600KB |
| CSS/WXSS | Unknown | < 50KB |

### 8.3 Specific Recommendations

1. **Lazy-load encyclopedia images** — cards are image-heavy. Only load images when the user scrolls to them.
2. **Reduce image asset sizes** — Card images in `/images/cards/` should be WebP format at 240px width max. Current resolution unknown but likely too high for WeChat display.
3. **Preload subpackages** — The current `preloadRule` in app.json is good. Ensure reading result and daily card subpackages are preloaded from the home page.
4. **Remove unused CSS** — The current `index.wxss` is 2600 lines. Many animation classes are defined but may be unreferenced. Audit and remove dead code.
5. **Reduce animation CSS weight** — The starfield uses `box-shadow` to render 40+ pseudo-stars. This is creative but expensive. Consider reducing to 15 stars per layer, or replacing with a single starfield image.

---

## 9. Accessibility Requirements

### 9.1 Current State Assessment

The app has some accessibility considerations:
- `aria-label` attributes on key images (daily card, diary entry icons)
- `prefers-reduced-motion` media query (defined in index.wxss)
- Semantic elements (`button`, `text`) used appropriately

However, accessibility is clearly not a priority in the current build. The council notes the following gaps.

### 9.2 Required Improvements

**P1 — Critical:**

1. **All interactive elements must have accessible labels.** Currently, the spread cards, diary entry, community entry, and membership CTA use `bindtap` on `view` elements without `aria-label`. Any `view` with `bindtap`, `role="button"`, or cursor:pointer needs `aria-label`.

2. **Color contrast.** The gold text on indigo background (`#F4D48C` on `#1A1A3E`) passes WCAG AA for large text only. For body text at 24rpx (~12px), the contrast ratio is approximately 3.8:1 — below the 4.5:1 AA threshold. Consider brightening the gold for small text, or use lighter body text.

3. **Reduced motion must be honored.** The current `prefers-reduced-motion` media query covers most animations but is incomplete. Motion-sensitive users should see all animations disabled, including:
   - Card flip animation (show instant state transition instead)
   - Loading sequence animations (show static skeleton)
   - Sparkle particles (already handled)
   - Streak badge entrance animations

**P2 — Important:**

4. **Touch target sizes.** All tappable elements must have a minimum touch target of 44x44pt (approximately 88x88rpx at standard WeChat scale). Audit all small tappable areas:
   - "关闭" button on overlays (currently uses `view` with `catchtap` — may be too small)
   - Star particles in overlays (not tappable, but positioned over tappable content — ensure they don't block touches)
   - Zodiac grid items (currently fine at ~150rpx wide)

5. **Focus indicators.** WeChat mini programs don't typically handle keyboard focus, but for TalkBack/ VoiceOver compatibility, ensure all interactive elements are reachable and their states are announced.

**P3 — Nice to have:**

6. **Semantic heading hierarchy.** Use actual heading elements (`<text class="heading-level-1">`, etc.) for screen reader navigation. Currently, all text is either `title-*` or `body-*` CSS classes with no semantic differentiation.

---

## 10. Implementation Roadmap

### Phase A: Quick Wins (1-2 weeks)

Changes that improve the experience dramatically with minimal engineering effort:

| Task | Owner | Effort | Impact |
|---|---|---|---|
| Reorder home page content (card first, everything else below fold) | Frontend | 2 days | High |
| Reduce loading sequence from 4s+ to 1.2s | API + Frontend | 1 day | High |
| Make persona selection explicit before reading starts | Frontend | 2 days | High |
| Remove shooting star easter egg | Frontend | 0.5 day | Low |
| Reduce animation complexity on daily card (remove shimmer, sparkle orbit) | Frontend | 1 day | Medium |
| Make interpretation text always expanded (remove collapse) | Frontend | 0.5 day | Medium |
| Add aria-label to all tappable view elements | Frontend | 1 day | Medium |

### Phase B: Information Architecture Overhaul (2-3 weeks)

| Task | Owner | Effort | Impact |
|---|---|---|---|
| Consolidate 7 card variants to 3 | Frontend | 3 days | High |
| Reduce home page entry points from 11 to 5 | Frontend | 2 days | Critical |
| Restructure reading result page (persona top, interpretation hero) | Frontend | 2 days | High |
| Move streak + collection to profile page | Frontend | 1 day | Medium |
| Remove seasonal banner, undo reading button, depth unlock card | Frontend | 1 day | Medium |
| Reduce starfield particles by 50% | Frontend | 0.5 day | Low |
| Remove parallax drift from starfield (static positioning only) | Frontend | 0.5 day | Low |

### Phase C: Monetization Restraint (1-2 weeks)

| Task | Owner | Effort | Impact |
|---|---|---|---|
| Replace animated membership card with single text CTA | Frontend | 1 day | High |
| Move 9.9 yuan CTA to post-first-reading context | Frontend | 1 day | Medium |
| Remove membership prompts from chat and reading result | Frontend | 0.5 day | High |
| Add persona selection toggle to membership flow | Frontend | 0.5 day | Low |

### Phase D: Accessibility + Performance (1-2 weeks)

| Task | Owner | Effort | Impact |
|---|---|---|---|
| Audit and fix color contrast for body text | Design | 2 days | Medium |
| Complete reduced-motion coverage audit | Frontend | 1 day | Medium |
| Reduce image asset sizes (WebP, 240px width) | Assets | 2 days | Medium |
| Add semantic heading hierarchy | Frontend | 1 day | Low |
| Audit touch target sizes | QA | 1 day | Medium |

### Total estimated effort: 6-9 weeks for full redesign

---

## Appendix A: Council Verbatim Quotes

> "The best tarot reading experience should feel like a quiet conversation under stars, not a carnival midway. The beauty is there, buried under decoration." — **Jony Ive**

> "This app has an identity crisis. Is it a tarot reader? A diary app? A social network? A subscription business? The home page screams 'I don't know what to cut.'" — **Steve Jobs**

> "The user has no mental model for what this app actually does on first visit because the onboarding tries to explain three concepts simultaneously while a dozen cards, badges, banners, and progress bars compete for attention underneath." — **Don Norman**

> "If you commit to the card-as-primary, then everything else on the page should be subordinate—grayed out, minimized, or hidden until the card interaction is complete." — **Jony Ive**

> "The cumulative weight of monetization signals transforms what should feel like a sacred space into a shopping mall." — **Jony Ive**

> "The best monetization is invisible: make the free experience so good that users want to pay, rather than so limited that they feel forced." — **Steve Jobs**

> "Perceived control is a fundamental driver of user satisfaction. If a user gets the Frank Sun when they're emotionally vulnerable, and they want the Gentle Star, that's a failure of user agency." — **Don Norman**

---

## Appendix B: Metrics to Track Post-Redesign

| Metric | Current Baseline | Target | Why |
|---|---|---|---|
| Daily card draw rate | Unknown | > 60% of DAU | Core action — if users don't draw, the app isn't working |
| Reading completion rate | Unknown | > 70% | Users who start a reading should finish it |
| Diary entry rate | Unknown | > 15% of DAU | Diary is the retention mechanism |
| Free-to-paid conversion | Unknown | > 5% | Current conversion may be suppressed by aggressive upsells |
| Page load time P95 | Unknown | < 3s | Performance is a feature |
| Return rate (Day 7) | Unknown | > 30% | Weekly retention is the north star for a daily ritual product |

---

*This PRD was generated by the Design Council on 2026-07-30. All recommendations are actionable and prioritized. The council has reviewed the codebase, debated the findings, and reached consensus on all critical points. Unresolved disagreements are documented in Section 5.4 and should be resolved by A/B testing the starfield and animation weight.*
