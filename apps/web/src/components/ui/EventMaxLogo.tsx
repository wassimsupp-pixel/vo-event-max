/**
 * Event MAX brand mark — the "max" wordmark with the radial starburst.
 * Vector recreation of the client-supplied logo (uses currentColor so it adapts
 * to light/dark). If you have the exact asset, drop it in apps/web/public/ and
 * swap this for <Image src="/event-max-logo.png" … />.
 */
export function EventMaxLogo({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 188 72"
      className={className}
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      aria-label="Event MAX"
    >
      <text
        x="0"
        y="57"
        fontFamily="system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
        fontWeight="900"
        fontSize="72"
        letterSpacing="-4"
        fill="currentColor"
      >
        max
      </text>
      <g
        transform="translate(165, 19)"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        fill="none"
      >
        <line x1="4.20" y1="0.00" x2="10.50" y2="0.00" />
        <line x1="3.88" y1="1.61" x2="9.70" y2="4.02" />
        <line x1="2.97" y1="2.97" x2="7.42" y2="7.42" />
        <line x1="1.61" y1="3.88" x2="4.02" y2="9.70" />
        <line x1="0.00" y1="4.20" x2="0.00" y2="10.50" />
        <line x1="-1.61" y1="3.88" x2="-4.02" y2="9.70" />
        <line x1="-2.97" y1="2.97" x2="-7.42" y2="7.42" />
        <line x1="-3.88" y1="1.61" x2="-9.70" y2="4.02" />
        <line x1="-4.20" y1="0.00" x2="-10.50" y2="0.00" />
        <line x1="-3.88" y1="-1.61" x2="-9.70" y2="-4.02" />
        <line x1="-2.97" y1="-2.97" x2="-7.42" y2="-7.42" />
        <line x1="-1.61" y1="-3.88" x2="-4.02" y2="-9.70" />
        <line x1="0.00" y1="-4.20" x2="0.00" y2="-10.50" />
        <line x1="1.61" y1="-3.88" x2="4.02" y2="-9.70" />
        <line x1="2.97" y1="-2.97" x2="7.42" y2="-7.42" />
        <line x1="3.88" y1="-1.61" x2="9.70" y2="-4.02" />
      </g>
    </svg>
  )
}
