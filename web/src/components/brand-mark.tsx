/** The Bridge-Agents mark: two endpoints joined by a bridge arc. */
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
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M3.5 17.5c0-4.7 3.8-8.5 8.5-8.5s8.5 3.8 8.5 8.5" />
        <path d="M3.5 17.5h17" />
        <path d="M7.5 17.5v-2.3M16.5 17.5v-2.3" />
        <circle cx="3.5" cy="17.5" r="1.2" fill="currentColor" stroke="none" />
        <circle cx="20.5" cy="17.5" r="1.2" fill="currentColor" stroke="none" />
      </svg>
    </span>
  );
}
