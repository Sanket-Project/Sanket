import clsx from "clsx";

/**
 * SANKET brand mark — the "forecast peak".
 *
 * A single rising-and-cresting curve (a demand signal peaking) with a node dot
 * at the predicted apex. The curve also quietly reads as an "S". Drawn in the
 * brand palette: Blue Whale tile (#03363D) + Jet Stream curve (#BDD9D7).
 * See frontend/DESIGN.md for the full rationale.
 */

const BLUE_WHALE = "#03363D";
const JET_STREAM = "#BDD9D7";

type LogoVariant = "tile" | "bare";

interface LogoMarkProps {
  /** Square size of the mark in pixels. */
  size?: number;
  /** "tile" = teal rounded tile with Jet Stream curve; "bare" = curve only, in currentColor. */
  variant?: LogoVariant;
  /** Override the curve/stroke color. */
  curveColor?: string;
  /** Override the tile fill (tile variant only). */
  tileColor?: string;
  className?: string;
  title?: string;
}

export function LogoMark({
  size = 36,
  variant = "tile",
  curveColor,
  tileColor,
  className,
  title = "SANKET",
}: LogoMarkProps) {
  const isTile = variant === "tile";
  const stroke = curveColor ?? (isTile ? JET_STREAM : "currentColor");
  const node = curveColor ?? (isTile ? "#ffffff" : "currentColor");

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      fill="none"
      role="img"
      aria-label={title}
      className={className}
    >
      {isTile && (
        <>
          <rect width="64" height="64" rx="14" fill={tileColor ?? BLUE_WHALE} />
          <rect
            x="0.75"
            y="0.75"
            width="62.5"
            height="62.5"
            rx="13.25"
            fill="none"
            stroke={JET_STREAM}
            strokeOpacity="0.16"
            strokeWidth="1.5"
          />
        </>
      )}
      <line
        x1="13"
        y1="46"
        x2="51"
        y2="46"
        stroke={stroke}
        strokeWidth="1.8"
        strokeLinecap="round"
        opacity="0.22"
      />
      <path
        d="M13 42 C22 42 24 23 32 21 C40 19 43 33 51 30"
        fill="none"
        stroke={stroke}
        strokeWidth="3.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="32" cy="21" r="3.4" fill={node} />
    </svg>
  );
}

interface LogoProps extends LogoMarkProps {
  /** Show the "SANKET" wordmark next to the mark. */
  showWordmark?: boolean;
  /** Wordmark text. */
  wordmark?: string;
  /** Optional small caps kicker under the wordmark, e.g. "Predictive OS". */
  kicker?: string;
  /** Extra classes on the wordmark text (color, etc.). Defaults to inherit. */
  wordmarkClassName?: string;
  /** Extra classes on the kicker text. */
  kickerClassName?: string;
}

export default function Logo({
  showWordmark = true,
  wordmark = "SANKET",
  kicker,
  wordmarkClassName,
  kickerClassName,
  className,
  size = 36,
  ...markProps
}: LogoProps) {
  return (
    <div className={clsx("flex items-center gap-2.5", className)}>
      <LogoMark size={size} {...markProps} />
      {showWordmark && (
        <div className="leading-none">
          <span
            className={clsx(
              "font-display font-bold tracking-tight",
              wordmarkClassName,
            )}
            style={{ fontSize: Math.round(size * 0.44) }}
          >
            {wordmark}
          </span>
          {kicker && (
            <span
              className={clsx(
                "mt-1 block font-semibold uppercase tracking-[0.18em]",
                kickerClassName ?? "text-content-subtle",
              )}
              style={{ fontSize: Math.max(9, Math.round(size * 0.24)) }}
            >
              {kicker}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
