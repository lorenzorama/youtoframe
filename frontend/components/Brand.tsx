// Neutral, original wordmark + viewfinder icon. Deliberately avoids any
// resemblance to YouTube/Google branding (no play button, no platform red,
// no "You"/"Tube" name echo) to steer clear of trademark confusion.
export default function Brand({ className = "" }: { className?: string }) {
  return (
    <span className={`inline-flex items-center gap-2 ${className}`}>
      <svg
        viewBox="0 0 24 24"
        className="h-5 w-5 text-ink"
        fill="none"
        stroke="currentColor"
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M4 8V5.5A1.5 1.5 0 0 1 5.5 4H8" />
        <path d="M16 4h2.5A1.5 1.5 0 0 1 20 5.5V8" />
        <path d="M20 16v2.5a1.5 1.5 0 0 1-1.5 1.5H16" />
        <path d="M8 20H5.5A1.5 1.5 0 0 1 4 18.5V16" />
        <circle cx="12" cy="12" r="2.5" />
      </svg>
      <span className="text-base font-semibold tracking-tight text-ink">Frame Extractor</span>
    </span>
  );
}
