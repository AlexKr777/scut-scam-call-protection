import { deriveCapabilityEmpty } from '../api/capability-view-model'

export function CapabilityEmpty({ page }: { page: 'History' | 'Alerts' }) {
  const copy = deriveCapabilityEmpty(page)
  return (
    <section className="capability-empty" aria-labelledby="capability-heading">
      <span>{page}</span>
      <h1 id="capability-heading">{copy.heading}</h1>
      <p>{copy.detail}</p>
      <small>Available when the local service gains persistent storage.</small>
    </section>
  )
}
