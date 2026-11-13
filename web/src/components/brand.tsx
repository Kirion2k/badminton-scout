/** The Badminton Scout crest: a half court in a midnight badge, and a lime shuttle in flight
 * across it (cork, feather skirt, two ribs). The court is the data; the shuttle is the play. */
export function Mark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden className={className}>
      <rect width="32" height="32" rx="8" fill="#0b1526" />
      <g fill="none" stroke="#3a5378" strokeWidth="1.1">
        <rect x="5.5" y="4.5" width="21" height="23" />
        <path d="M5.5 11h21M16 11v16.5" />
      </g>
      <path d="M11.9 18.2 16.8 9.8 23.2 16.2 14.8 21.1Z" fill="#c8f031" />
      <g stroke="#0b1526" strokeWidth="0.9" strokeLinecap="round">
        <path d="M13.3 19.7 18.4 11.4M13.3 19.7 21.5 14.6" />
      </g>
      <circle
        cx="11.5"
        cy="21.5"
        r="3.3"
        fill="#c8f031"
        stroke="#0b1526"
        strokeWidth="0.9"
      />
    </svg>
  );
}
