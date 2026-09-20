interface IllustrationProps {
  className?: string
}

/** Shared decorative motif for empty states — an abstract compass with a dotted route. */
export function TravelIllustration({ className }: IllustrationProps) {
  return (
    <svg
      className={className}
      width="180"
      height="130"
      viewBox="0 0 200 140"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <circle cx="100" cy="68" r="46" stroke="currentColor" strokeOpacity="0.22" strokeWidth="1.5" />
      <circle cx="100" cy="68" r="3" fill="currentColor" fillOpacity="0.35" />
      <polygon points="100,44 108,68 100,92 92,68" fill="currentColor" fillOpacity="0.16" />
      <path
        d="M22 118 C 60 118, 60 30, 100 30 S 150 60, 178 22"
        stroke="currentColor"
        strokeOpacity="0.32"
        strokeWidth="2"
        strokeLinecap="round"
        strokeDasharray="1 8"
      />
      <circle cx="22" cy="118" r="4" fill="currentColor" fillOpacity="0.45" />
      <circle cx="178" cy="22" r="4" fill="currentColor" fillOpacity="0.45" />
      <circle cx="150" cy="100" r="2.5" fill="currentColor" fillOpacity="0.3" />
      <circle cx="45" cy="35" r="2" fill="currentColor" fillOpacity="0.3" />
    </svg>
  )
}
