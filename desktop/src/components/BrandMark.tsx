interface BrandMarkProps {
  size?: number
}

export function BrandMark({ size = 26 }: BrandMarkProps) {
  return (
    <svg
      aria-hidden="true"
      className="brand-mark"
      height={size}
      viewBox="0 0 32 32"
      width={size}
    >
      <path d="M13 4H9.5A4.5 4.5 0 0 0 5 8.5v15A4.5 4.5 0 0 0 9.5 28H13" />
      <path d="M13 8H10.5A1.5 1.5 0 0 0 9 9.5v13a1.5 1.5 0 0 0 1.5 1.5H13" />
      <path className="brand-signal" d="M17 19v-6m4 9V10m4 8v-4" />
      <circle className="brand-signal-fill" cx="17" cy="22.5" r="1.25" />
    </svg>
  )
}
