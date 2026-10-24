export function ProgressBar({ value, showLabel = false }: { value: number; showLabel?: boolean }) {
  const progress = Math.max(0, Math.min(100, value));
  return (
    <div className="w-full">
      {showLabel && <div className="mb-2 flex justify-between text-xs"><span className="text-muted">Overall progress</span><span className="font-medium text-slate-200">{progress}%</span></div>}
      <div className="h-2 overflow-hidden rounded-full bg-slate-800">
        <div className="h-full rounded-full bg-gradient-to-r from-brand to-violet-400 transition-all duration-500" style={{ width: `${progress}%` }} />
      </div>
    </div>
  );
}
