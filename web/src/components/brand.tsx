/** The Badminton Scout mark: a cork and three fanned feathers in a lime disc (docs/design.md). */
export function Mark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden className={className}>
      <circle cx="16" cy="16" r="16" fill="#c6f432" />
      <g stroke="#121a26" strokeWidth="2.2" strokeLinecap="round" fill="none">
        <path d="M13.5 18.5 L22.5 7.5" />
        <path d="M14.5 19.8 L25 13" />
        <path d="M12.2 17.4 L16.5 6.2" />
      </g>
      <circle cx="11" cy="21" r="4.2" fill="#121a26" />
    </svg>
  );
}
