import { Link } from 'react-router-dom';
import HeroShapes from '../components/HeroShapes';

function ArrowIcon() {
  return (
    <svg viewBox="0 0 16 16" width="14" height="14" fill="none" aria-hidden="true">
      <path d="M3.5 8h9M8.5 4l4 4-4 4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export default function Landing() {
  return (
    <div className="landing-hero-wrap">
      <HeroShapes />
      <header className="landing-hero">
        <p className="landing-eyebrow mono">Campus lost &amp; found — AI matched</p>
        <h1 className="landing-title">Somebody found what you lost.</h1>
        <p className="landing-sub">
          Pin a notice for what you lost or found. The matching engine compares
          descriptions, photos, location, and time to find the other half of
          the story — no scrolling through a noticeboard required.
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
      </header>
    </div>
  );
}
