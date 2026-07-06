export default function MemoriesLoading() {
  return (
    <div className="space-y-8 animate-pulse">
      <div>
        <div className="h-5 w-24 rounded-lg bg-[var(--color-charcoal)]" />
        <div className="mt-3 h-7 w-48 rounded-lg bg-[var(--color-charcoal)]" />
      </div>
      <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="h-44 rounded-2xl border border-[var(--color-graphite)]/30 bg-[var(--color-ash)] p-6 space-y-3">
            <div className="h-4 w-32 rounded bg-[var(--color-charcoal)]" />
            <div className="h-3 w-full rounded bg-[var(--color-charcoal)]" />
            <div className="h-3 w-3/4 rounded bg-[var(--color-charcoal)]" />
            <div className="flex gap-2 pt-2">
              <div className="h-5 w-14 rounded-md bg-[var(--color-charcoal)]" />
              <div className="h-5 w-16 rounded-md bg-[var(--color-charcoal)]" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
