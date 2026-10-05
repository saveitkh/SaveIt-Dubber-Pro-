import { useT } from "../i18n";

const STYLES: Record<string, string> = {
  new: "bg-slate-700 text-slate-200",
  processing: "bg-brand-600/20 text-brand-300",
  needs_review: "bg-amber-500/20 text-amber-300",
  done: "bg-emerald-500/20 text-emerald-300",
  error: "bg-red-500/20 text-red-300",
};

export function StatusChip({ status, progress }: { status: string; progress?: number | null }) {
  const t = useT();
  const LABELS: Record<string, string> = {
    new: t.status.new,
    processing: t.status.processing,
    needs_review: t.status.needsReview,
    done: t.status.done,
    error: t.status.error,
  };
  const label = LABELS[status] ?? status;
  const style = STYLES[status] ?? STYLES.new;
  return (
    <span className={`whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-medium ${style}`}>
      {label}
      {status === "processing" && typeof progress === "number" ? ` ${Math.round(progress)}%` : ""}
    </span>
  );
}
