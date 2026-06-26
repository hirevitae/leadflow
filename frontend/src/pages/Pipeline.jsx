import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, STAGES, formatApiError } from "@/lib/api";
import AddLeadDialog from "@/components/AddLeadDialog";
import { toast } from "sonner";
import { Phone, MessageCircle, GripVertical } from "lucide-react";

export default function Pipeline() {
  const [leads, setLeads] = useState([]);
  const [dragId, setDragId] = useState(null);

  const load = async () => {
    const { data } = await api.get("/leads");
    setLeads(data);
  };
  useEffect(() => { load(); }, []);

  const grouped = useMemo(() => {
    const g = {};
    STAGES.forEach((s) => (g[s.key] = []));
    leads.forEach((l) => (g[l.stage] || (g[l.stage] = [])).push(l));
    return g;
  }, [leads]);

  const onDrop = async (stage) => {
    if (!dragId) return;
    const lead = leads.find((l) => l.id === dragId);
    if (!lead || lead.stage === stage) { setDragId(null); return; }
    // Optimistic
    setLeads((prev) => prev.map((l) => (l.id === dragId ? { ...l, stage } : l)));
    setDragId(null);
    try {
      await api.post(`/leads/${lead.id}/stage`, { stage });
      toast.success(`${lead.name} → ${stage.replace("_", " ")}`);
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
      load();
    }
  };

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6 max-w-[1600px]">
        <div>
          <h1 className="font-display font-bold text-3xl tracking-tight">Pipeline</h1>
          <p className="text-sm text-zinc-500 mt-1">Drag leads across stages to update their status.</p>
        </div>
        <AddLeadDialog onCreated={load} />
      </div>

      <div className="kanban-scroll overflow-x-auto pb-4">
        <div className="flex gap-4 min-w-max" data-testid="kanban-board">
          {STAGES.map((s) => (
            <div
              key={s.key}
              className="w-[300px] flex-shrink-0 bg-zinc-100/60 rounded-lg p-3"
              onDragOver={(e) => e.preventDefault()}
              onDrop={() => onDrop(s.key)}
              data-testid={`kanban-column-${s.key}`}
            >
              <div className="flex items-center justify-between mb-3 px-1 sticky top-0">
                <div className="flex items-center gap-2">
                  <span className={`w-2 h-2 rounded-full ${
                    s.key === "enrolled" ? "bg-emerald-500" :
                    s.key === "lost" ? "bg-rose-400" :
                    s.key === "negotiation" ? "bg-amber-500" :
                    s.key === "demo_scheduled" ? "bg-violet-500" :
                    s.key === "interested" ? "bg-indigo-500" :
                    s.key === "contacted" ? "bg-blue-500" : "bg-zinc-400"
                  }`} />
                  <span className="font-display text-sm font-semibold">{s.label}</span>
                </div>
                <span className="text-xs text-zinc-500 mono">{grouped[s.key].length}</span>
              </div>

              <div className="space-y-2 min-h-[200px]">
                {grouped[s.key].length === 0 && (
                  <div className="text-xs text-zinc-400 text-center py-6">Empty</div>
                )}
                {grouped[s.key].map((l) => (
                  <Link
                    key={l.id}
                    to={`/leads/${l.id}`}
                    draggable
                    onDragStart={() => setDragId(l.id)}
                    className="lead-card block bg-white border border-zinc-200 rounded-md p-3 cursor-grab active:cursor-grabbing"
                    data-testid={`kanban-card-${l.id}`}
                  >
                    <div className="flex items-start justify-between">
                      <div className="font-medium text-sm">{l.name}</div>
                      <GripVertical className="w-3.5 h-3.5 text-zinc-300" />
                    </div>
                    <div className="text-xs text-zinc-500 mt-1">{l.course || "—"}</div>
                    <div className="flex items-center justify-between mt-3 text-[11px] text-zinc-500">
                      <span className="mono">{l.phone}</span>
                      <span className={`px-1.5 py-0.5 rounded ${
                        l.priority === "high" ? "bg-rose-50 text-rose-700" :
                        l.priority === "low"  ? "bg-zinc-100 text-zinc-600" :
                                                "bg-amber-50 text-amber-700"
                      }`}>{l.priority}</span>
                    </div>
                  </Link>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
