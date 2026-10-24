export function PageHeading({ title, subtitle, action }: { title: string; subtitle: string; action?: React.ReactNode }) {
  return (
    <div className="mb-7 flex flex-wrap items-end justify-between gap-4">
      <div><h2 className="text-2xl font-semibold tracking-tight text-white">{title}</h2><p className="mt-1.5 text-sm text-muted">{subtitle}</p></div>
      {action}
    </div>
  );
}
