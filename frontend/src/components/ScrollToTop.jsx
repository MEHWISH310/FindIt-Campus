import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';

// React Router keeps the previous scroll position on navigation, so jumping
// from a footer link at the bottom of one page would land you halfway down
// the next. Reset to the top whenever the path changes.
export default function ScrollToTop() {
  const { pathname } = useLocation();

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);

  return null;
}
