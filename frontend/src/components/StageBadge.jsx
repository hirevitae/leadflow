import { stageMeta } from "@/lib/api";

export default function StageBadge({ stage }) {
  const m = stageMeta(stage);
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-md border text-xs font-medium ${m.tint}`}
      data-testid={`stage-badge-${stage}`}
    >
      {m.label}
    </span>
  );
}
