export default function DashboardLoading() {
  return (
    <div className="space-y-8 animate-pulse">
      <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-end">
        <div>
          <div className="h-5 w-32 rounded-lg bg-[var(--color-charcoal)]" />
          <div className="mt-3 h-7 w-64 rounded-lg bg-[var(--color-charcoal)]" />
          <div className="mt-1.5 h-4 w-96 rounded-lg bg-[var(--color-charcoal)]" />
        </div>
      </div>
      <div className="grid gap-6 md:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-32 rounded-2xl border border-[var(--color-graphite)]/30 bg-[var(--color-ash)] p-6 space-y-4">
            <div className="h-4 w-24 rounded bg-[var(--color-charcoal)]" />
            <div className="h-6 w-16 rounded bg-[var(--color-charcoal)]" />
          </div>
        ))}
      </div>
      <div className="grid gap-6 xl:grid-cols-[1.3fr_0.7fr]">
        <div className="h-72 rounded-2xl border border-[var(--color-graphite)]/30 bg-[var(--color-ash)] p-6 space-y-4">
          <div className="h-5 w-32 rounded bg-[var(--color-charcoal)]" />
          <div className="space-y-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-9 w-full rounded bg-[var(--color-charcoal)]" />
            ))}
          </div>
        </div>
        <div className="h-72 rounded-2xl border border-[var(--color-graphite)]/30 bg-[var(--color-ash)] p-6 space-y-4">
          <div className="h-5 w-28 rounded bg-[var(--color-charcoal)]" />
          <div className="space-y-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-10 w-full rounded bg-[var(--color-charcoal)]" />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
