const STAR_POINTS =
  '22,2 25.1,14.6 36.1,7.9 29.4,18.9 42,22 29.4,25.1 36.1,36.1 25.1,29.4 22,42 18.9,29.4 7.9,36.1 14.6,25.1 2,22 14.6,18.9 7.9,7.9 18.9,14.6';
const OCTAGON_POINTS = '12,4 28,4 36,12 36,28 28,36 12,36 4,28 4,12';

export default function HeroShapes() {
  return (
    <div className="hero-shapes" aria-hidden="true">
      {/* left side */}
      <svg className="hero-shape hero-shape--star" viewBox="0 0 44 44" width="50" height="50">
        <polygon points={STAR_POINTS} fill="var(--found)" />
      </svg>
      <svg className="hero-shape hero-shape--octagon-sm" viewBox="0 0 40 40" width="32" height="32">
        <polygon points={OCTAGON_POINTS} fill="var(--brand-gold)" />
      </svg>
      <span className="hero-shape hero-shape--dot-left" />

      {/* right side */}
      <span className="hero-shape hero-shape--dot-right" />
      <svg className="hero-shape hero-shape--octagon" viewBox="0 0 40 40" width="40" height="40">
        <polygon points={OCTAGON_POINTS} fill="var(--lost)" />
      </svg>
      <svg className="hero-shape hero-shape--star-sm" viewBox="0 0 44 44" width="34" height="34">
        <polygon points={STAR_POINTS} fill="var(--brand-pink)" />
      </svg>
    </div>
  );
}
