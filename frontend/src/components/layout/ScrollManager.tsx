import { useEffect, useLayoutEffect, useRef } from "react";
import { useLocation, useNavigationType } from "react-router-dom";

const MAIN_ID = "main-content";

/**
 * Scroll behaviour for the app's persistent `<main>` scroll container.
 *
 * The window never scrolls here, so the browser's own restoration does nothing
 * and a newly opened page kept the previous page's offset (deep audit F15).
 * - Moving to a different page (link, redirect): start at the top.
 * - Back/Forward: return to where that history entry was left, so a planner
 *   lands back on the row they opened.
 * - Same page, new query string (filters): leave the position alone.
 */
export function ScrollManager() {
  const location = useLocation();
  const navigationType = useNavigationType();
  const positions = useRef(new Map<string, number>());
  const previous = useRef({ key: location.key, pathname: location.pathname });

  // Keep the current entry's position up to date as the user scrolls.
  useEffect(() => {
    const main = document.getElementById(MAIN_ID);
    if (!main) return;
    const key = location.key;
    const onScroll = () => positions.current.set(key, main.scrollTop);
    main.addEventListener("scroll", onScroll, { passive: true });
    return () => main.removeEventListener("scroll", onScroll);
  }, [location.key]);

  useLayoutEffect(() => {
    const main = document.getElementById(MAIN_ID);
    const prev = previous.current;
    previous.current = { key: location.key, pathname: location.pathname };
    if (!main || prev.key === location.key) return;
    if (!positions.current.has(prev.key)) positions.current.set(prev.key, main.scrollTop);

    if (navigationType === "POP") {
      main.scrollTop = positions.current.get(location.key) ?? 0;
    } else if (prev.pathname !== location.pathname) {
      main.scrollTop = 0;
    }
  }, [location.key, location.pathname, navigationType]);

  return null;
}
