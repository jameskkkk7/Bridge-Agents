/** The Bridge-Agents mark: two coloured endpoints joined by a bridge arc. */
export function BrandMark({ className = "" }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={`brand-mark flex size-8 shrink-0 items-center justify-center rounded-lg text-white shadow-sm ring-1 ring-black/5 dark:ring-white/15 ${className}`}
    >
      <svg
        viewBox="0 0 24 24"
        className="size-5"
        fill="none"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path
          d="M3.5 12.5C5.2 9 8.4 7 12 7s6.8 2 8.5 5.5"
          stroke="rgba(255,255,255,0.78)"
          strokeWidth="1.6"
        />
        <circle cx="7.4" cy="16.4" r="2.8" fill="#22d3ee" />
        <circle cx="16.6" cy="16.4" r="2.8" fill="#a78bfa" />
        <path d="M10.2 16.4h3.6" stroke="#f8fafc" strokeWidth="1.7" />
      </svg>
    </span>
  );
}
