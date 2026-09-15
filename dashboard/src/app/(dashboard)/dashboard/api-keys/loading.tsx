export default function ApiKeysLoading() {
  return (
    <div className="space-y-6 animate-pulse">
      <div className="h-5 w-24 rounded-md bg-muted" />
      <div className="h-7 w-48 rounded-md bg-muted" />
      <div className="grid gap-4 lg:grid-cols-[0.82fr_1.18fr]">
        <div className="h-72 rounded-xl border border-border bg-card p-5">
          <div className="h-5 w-28 rounded bg-muted" />
          <div className="mt-4 h-9 w-full rounded bg-muted" />
          <div className="mt-4 h-40 w-full rounded bg-muted" />
          <div className="mt-4 h-9 w-32 rounded bg-muted" />
        </div>
        <div className="h-72 rounded-xl border border-border bg-card p-5">
          <div className="h-5 w-24 rounded bg-muted" />
          <div className="mt-4 space-y-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="h-12 w-full rounded bg-muted" />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
