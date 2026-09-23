/**
 * Line icons, drawn inline.
 *
 * Emoji were standing in for these and they were the weakest part of the UI:
 * every platform draws them differently, they cannot take the accent colour,
 * and a row of them in a tab bar reads as a chat message rather than
 * navigation. These inherit `currentColor` and sit on a 24px grid.
 */

type IconProps = {
  size?: number;
  strokeWidth?: number;
  className?: string;
  filled?: boolean;
};

function Svg({
  size = 24,
  strokeWidth = 1.9,
  className,
  children,
}: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden
    >
      {children}
    </svg>
  );
}

export function HomeIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path
        d="M3 10.2 12 3l9 7.2V20a1.6 1.6 0 0 1-1.6 1.6H4.6A1.6 1.6 0 0 1 3 20z"
        fill={props.filled ? "currentColor" : "none"}
        fillOpacity={props.filled ? 0.18 : 0}
      />
      <path d="M9.2 21.6v-6.4h5.6v6.4" />
    </Svg>
  );
}

export function ChatIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path
        d="M21 11.5a8.5 8.5 0 0 1-12.4 7.6L3 21l1.9-5.6A8.5 8.5 0 1 1 21 11.5z"
        fill={props.filled ? "currentColor" : "none"}
        fillOpacity={props.filled ? 0.18 : 0}
      />
    </Svg>
  );
}

export function FriendsIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="9" cy="8" r="3.4" />
      <path d="M2.8 20.2a6.2 6.2 0 0 1 12.4 0" />
      <path d="M16.6 5.1a3.4 3.4 0 0 1 0 6.1M18 14.6a6.2 6.2 0 0 1 3.2 5.6" />
    </Svg>
  );
}

export function PersonIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="8" r="3.6" />
      <path d="M5 20.4a7 7 0 0 1 14 0" />
    </Svg>
  );
}

export function BoltIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path
        d="M13.2 2 4.8 13.2h5.6L10.2 22l8.6-11.4h-5.8z"
        fill={props.filled ? "currentColor" : "none"}
      />
    </Svg>
  );
}

export function FlameIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path
        d="M12.5 2.5c.4 3-1.6 4.2-3 5.8-1.6 1.8-2.5 3.4-2.5 5.4a5 5 0 0 0 10 0c0-1.5-.5-2.6-1.3-3.6.2 1.3-.4 2.2-1.2 2.5.6-3.2-.8-6.5-2-10.1z"
        fill={props.filled ? "currentColor" : "none"}
      />
    </Svg>
  );
}

export function SparkleIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path
        d="M12 2.8c.9 4.6 3.6 7.3 8.2 8.2-4.6.9-7.3 3.6-8.2 8.2-.9-4.6-3.6-7.3-8.2-8.2 4.6-.9 7.3-3.6 8.2-8.2z"
        fill={props.filled ? "currentColor" : "none"}
      />
    </Svg>
  );
}

export function KeyIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="7.6" cy="16.4" r="3.6" />
      <path d="M10.2 13.8 20 4m-3 3 2.4 2.4M14.6 9.4 17 11.8" />
    </Svg>
  );
}

export function ChevronIcon({ size = 20, strokeWidth = 2.2, className }: IconProps) {
  // Never a text glyph: `›` is a mirroring character and Unicode flips it
  // inside an RTL run, so a back chevron typed as text points the wrong way.
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      className={className}
      aria-hidden
    >
      <path
        d="M9 6l6 6-6 6"
        stroke="currentColor"
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
