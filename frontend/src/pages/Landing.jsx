import { useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import HeroShapes from '../components/HeroShapes';

function ArrowIcon() {
  return (
    <svg viewBox="0 0 16 16" width="14" height="14" fill="none" aria-hidden="true">
      <path d="M3.5 8h9M8.5 4l4 4-4 4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/* --- decorative shape primitives, reused across sections --- */
const STAR_POINTS =
  '22,2 25.1,14.6 36.1,7.9 29.4,18.9 42,22 29.4,25.1 36.1,36.1 25.1,29.4 22,42 18.9,29.4 7.9,36.1 14.6,25.1 2,22 14.6,18.9 7.9,7.9 18.9,14.6';
const OCTAGON_POINTS = '12,4 28,4 36,12 36,28 28,36 12,36 4,28 4,12';

function Deco({ kind, className }) {
  const cls = `lp-deco ${className || ''}`;
  if (kind === 'ring') {
    return (
      <svg className={cls} viewBox="0 0 48 48" width="48" height="48" aria-hidden="true">
        <circle cx="24" cy="24" r="20" fill="none" stroke="currentColor" strokeWidth="3" />
      </svg>
    );
  }
  if (kind === 'plus') {
    return (
      <svg className={cls} viewBox="0 0 24 24" width="24" height="24" aria-hidden="true">
        <path d="M12 3v18M3 12h18" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
      </svg>
    );
  }
  if (kind === 'triangle') {
    return (
      <svg className={cls} viewBox="0 0 44 44" width="40" height="40" aria-hidden="true">
        <path d="M22 4 40 38H4Z" fill="currentColor" />
      </svg>
    );
  }
  if (kind === 'squiggle') {
    return (
      <svg className={cls} viewBox="0 0 80 20" width="80" height="20" aria-hidden="true">
        <path d="M2 10c8-12 16 12 24 0s16-12 24 0 16 12 24 0" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
      </svg>
    );
  }
  if (kind === 'star') {
    return (
      <svg className={cls} viewBox="0 0 44 44" width="44" height="44" aria-hidden="true">
        <polygon points={STAR_POINTS} fill="currentColor" />
      </svg>
    );
  }
  return (
    <svg className={cls} viewBox="0 0 40 40" width="36" height="36" aria-hidden="true">
      <polygon points={OCTAGON_POINTS} fill="currentColor" />
    </svg>
  );
}

const STEPS = [
  {
    n: '01',
    title: 'File a notice',
    body: 'Describe what you lost or found, add a photo, and mark the spot and time. If you found it, you also set a secret question only the true owner could answer.',
  },
  {
    n: '02',
    title: 'See your matches',
    body: 'You’re notified when a likely match shows up. Open your notice to see the ranked candidates, and claim the right one by answering the secret question the finder set.',
  },
  {
    n: '03',
    title: 'Collect it',
    body: 'On a correct answer you’re told which campus desk to collect from. Staff there confirm your claim, hand the item over, and record the handover.',
  },
];

const SIGNALS = [
  {
    tag: 'S1',
    title: 'Text understanding',
    body: '“Black wallet” and “dark brown leather purse” land close together, because descriptions are embedded with a sentence transformer, not string-matched.',
    weight: 0.82,
  },
  {
    tag: 'S2',
    title: 'Image similarity',
    body: 'Uploaded photos are compared with CLIP, so a picture of the item counts even when the words don’t line up.',
    weight: 0.7,
  },
  {
    tag: 'S3',
    title: 'Geo-temporal fusion',
    body: 'A find 40 m and 20 minutes away outranks one across campus a week later. Location proximity and time decay weight every candidate.',
    weight: 0.9,
  },
  {
    tag: 'S4',
    title: 'Calibrated confidence',
    body: 'Scores pass through a calibration layer, so an 80% match really is right about 80% of the time, measured with Expected Calibration Error.',
    weight: 1,
  },
];

function SignalExplorer() {
  const [active, setActive] = useState(0);
  const draggingRef = useRef(false);
  const barsRef = useRef(null);
  const signal = SIGNALS[active];

  function pickFromClientX(clientX) {
    const el = barsRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const ratio = (clientX - rect.left) / rect.width;
    const idx = Math.max(0, Math.min(SIGNALS.length - 1, Math.floor(ratio * SIGNALS.length)));
    setActive(idx);
  }

  function onKeyDown(e) {
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
      e.preventDefault();
      setActive((i) => Math.min(SIGNALS.length - 1, i + 1));
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
      e.preventDefault();
      setActive((i) => Math.max(0, i - 1));
    }
  }

  return (
    <div className="lp-signal-card">
      <div className="lp-signal-info" aria-live="polite">
        <span className="lp-signal-tag mono">{signal.tag}</span>
        <h3 className="lp-signal-title">{signal.title}</h3>
        <p className="lp-signal-body">{signal.body}</p>
        <div className="lp-signal-dots" aria-hidden="true">
          {SIGNALS.map((s, i) => (
            <span key={s.tag} className={`lp-signal-dot${i === active ? ' is-active' : ''}`} />
          ))}
        </div>
      </div>

      <div
        ref={barsRef}
        className="lp-signal-bars"
        role="group"
        aria-label="Slide across the bars to explore each matching signal"
        onKeyDown={onKeyDown}
        onPointerDown={(e) => {
          draggingRef.current = true;
          e.currentTarget.setPointerCapture(e.pointerId);
          pickFromClientX(e.clientX);
        }}
        onPointerMove={(e) => {
          if (draggingRef.current) pickFromClientX(e.clientX);
        }}
        onPointerUp={() => {
          draggingRef.current = false;
        }}
        onPointerCancel={() => {
          draggingRef.current = false;
        }}
      >
        {SIGNALS.map((s, i) => (
          <button
            key={s.tag}
            type="button"
            className={`lp-signal-col${i === active ? ' is-active' : ''}`}
            aria-pressed={i === active}
            aria-label={`${s.tag}: ${s.title}`}
            onMouseEnter={() => setActive(i)}
            onFocus={() => setActive(i)}
            onClick={() => setActive(i)}
          >
            <span className="lp-signal-col-track">
              <span
                className="lp-signal-col-fill"
                style={{ height: `${Math.round(s.weight * 100)}%` }}
              />
            </span>
            <span className="lp-signal-col-label mono">{s.tag}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

const SAFEGUARDS = [
  {
    k: '01',
    title: 'Asymmetric verification',
    body: 'Finders set a hidden question; claimants must answer it before any contact detail is shown. Three misses locks the claim for a day.',
  },
  {
    k: '02',
    title: 'Custody ledger',
    body: 'Every handover is written once and never edited. Item, claimant, verifier, and timestamp form an auditable chain.',
  },
  {
    k: '03',
    title: 'High-risk handling',
    body: 'IDs, phones, keys, and documents get priority matching, redacted numbers in public views, and escalation if unclaimed after 7 days.',
  },
  {
    k: '04',
    title: 'Smart disambiguation',
    body: 'When two matches score too close to call, you get one targeted attribute question instead of a wrong guess.',
  },
];

export default function Landing() {
  return (
    <div className="landing">
      <div className="landing-hero-wrap">
        <HeroShapes />
        <header className="landing-hero">
          <p className="landing-eyebrow mono">Campus lost &amp; found, AI matched</p>
          <h1 className="landing-title">Somebody found what you lost.</h1>
          <p className="landing-sub">
            Drop a quick notice for whatever you lost or found. The engine reads
            the words, the photo, the place and the time, and finds the other
            half of the story. No noticeboard, no group-chat begging.
          </p>
          <div className="landing-ctas">
            <Link to="/report/lost" className="cta cta--lost">
              Report something lost
              <ArrowIcon />
            </Link>
            <Link to="/report/found" className="cta cta--found">
              Report something found
              <ArrowIcon />
            </Link>
          </div>
          <button
            type="button"
            className="landing-scroll-cue"
            aria-label="See how it works"
            onClick={() =>
              document
                .getElementById('how-it-works-section')
                ?.scrollIntoView({ behavior: 'smooth', block: 'start' })
            }
          >
            <svg viewBox="0 0 24 24" width="22" height="22" fill="none" aria-hidden="true">
              <path
                d="M6 9l6 6 6-6"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </button>
        </header>
      </div>

      {/* 1. How it works: numbered timeline, not cards */}
      <section
        id="how-it-works-section"
        className="lp-sec lp-steps"
        aria-labelledby="how-it-works"
      >
        <Deco kind="plus" className="lp-deco--b" />
        <Deco kind="octagon" className="lp-deco--k" />
        <p className="lp-eyebrow mono">How it works</p>
        <h2 id="how-it-works" className="lp-h2">Three steps from lost to found.</h2>
        <ol className="lp-timeline">
          {STEPS.map((s) => (
            <li key={s.n} className="lp-tl-item">
              <span className="lp-tl-num">{s.n}</span>
              <h3 className="lp-tl-title">{s.title}</h3>
              <p className="lp-tl-body">{s.body}</p>
            </li>
          ))}
        </ol>
      </section>

      {/* 2. What powers the match: alternating zig-zag rows with a mini viz */}
      <section className="lp-sec lp-signals" aria-labelledby="what-powers">
        <Deco kind="squiggle" className="lp-deco--c" />
        <Deco kind="octagon" className="lp-deco--d" />
        <Deco kind="star" className="lp-deco--e" />
        <Deco kind="ring" className="lp-deco--l" />
        <p className="lp-eyebrow mono">What powers the match</p>
        <h2 id="what-powers" className="lp-h2">Four signals, one calibrated score.</h2>
        <p className="lp-signal-hint">Slide across the bars to see what each one contributes.</p>
        <SignalExplorer />
      </section>

      {/* 3. Safe handover: even 2x2 tile grid, accent tint on hover */}
      <section className="lp-sec lp-safe" aria-labelledby="safe-handover">
        <Deco kind="triangle" className="lp-deco--f" />
        <Deco kind="ring" className="lp-deco--g" />
        <Deco kind="plus" className="lp-deco--m" />
        <p className="lp-eyebrow mono">Safe handover</p>
        <h2 id="safe-handover" className="lp-h2">A match is only the first half.</h2>
        <div className="lp-bento">
          {SAFEGUARDS.map((f) => (
            <article key={f.k} className="lp-bento-tile">
              <span className="lp-bento-k mono">{f.k}</span>
              <h3 className="lp-bento-title">{f.title}</h3>
              <p className="lp-bento-body">{f.body}</p>
            </article>
          ))}
        </div>
      </section>

      {/* 4. Closing band */}
      <section className="lp-closing" aria-labelledby="closing-cta">
        <Deco kind="star" className="lp-deco--h" />
        <Deco kind="plus" className="lp-deco--i" />
        <Deco kind="octagon" className="lp-deco--j" />
        <h2 id="closing-cta" className="lp-closing-title">Lost something today?</h2>
        <p className="lp-closing-sub">
          It takes under a minute to file a notice. The engine does the searching.
        </p>
        <div className="landing-ctas">
          <Link to="/report/lost" className="cta cta--lost">
            Report something lost
            <ArrowIcon />
          </Link>
          <Link to="/lost" className="cta cta--found">
            Browse open notices
            <ArrowIcon />
          </Link>
        </div>
      </section>
    </div>
  );
}
