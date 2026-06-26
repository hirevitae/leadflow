import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, formatApiError } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { toast } from "sonner";
import { CheckCircle2, Clock, AlertTriangle, CalendarClock } from "lucide-react";

export default function Followups() {
  const [tasks, setTasks] = useState([]);

  const load = async () => {
    try { const { data } = await api.get("/tasks"); setTasks(data); }
    catch (e) { toast.error("Could not load follow-ups"); }
  };
  useEffect(() => { load(); }, []);

  const toggle = async (t) => {
    try { await api.patch(`/tasks/${t.id}`, { done: !t.done }); load(); }
    catch (e) { toast.error("Update failed"); }
  };

  const now = new Date();
  const pending = tasks.filter((t) => !t.done);
  const overdue = pending.filter((t) => new Date(t.due_date) < now);
  const done = tasks.filter((t) => t.done);

  const Row = ({ t }) => {
    const due = new Date(t.due_date);
    const isOverdue = !t.done && due < now;
    return (
      <div className="flex items-center gap-3 p-3 rounded-md border border-zinc-200 hover:bg-zinc-50" data-testid={`task-${t.id}`}>
        <Checkbox checked={t.done} onCheckedChange={() => toggle(t)} data-testid={`task-check-${t.id}`} />
        <div className="flex-1 min-w-0">
          <div className={`text-sm font-medium ${t.done ? "line-through text-zinc-400" : ""}`}>{t.title}</div>
          <div className="text-xs text-zinc-500 mt-0.5 flex items-center gap-2">
            <span className="inline-flex items-center gap-1"><CalendarClock className="w-3.5 h-3.5" /> {due.toLocaleString()}</span>
            {t.lead_name && <Link to={`/leads/${t.lead_id}`} className="text-blue-600 hover:underline">{t.lead_name}</Link>}
            {t.owner_name && <span>· {t.owner_name}</span>}
          </div>
        </div>
        {isOverdue && <span className="text-xs px-2 py-0.5 rounded bg-rose-50 text-rose-700 border border-rose-200 inline-flex items-center gap-1"><AlertTriangle className="w-3 h-3" /> Overdue</span>}
      </div>
    );
  };

  return (
    <div className="p-8 max-w-4xl mx-auto" data-testid="followups-page">
      <div className="mb-6">
        <h1 className="font-display font-bold text-3xl tracking-tight">Follow-ups</h1>
        <p className="text-sm text-zinc-500 mt-1">Scheduled reminders across your leads.</p>
      </div>

      <div className="grid grid-cols-3 gap-3 mb-6">
        <Card><CardContent className="p-4"><div className="text-xs text-zinc-500 flex items-center gap-1"><Clock className="w-3.5 h-3.5" /> Pending</div><div className="text-2xl font-display font-bold mt-1" data-testid="stat-pending">{pending.length}</div></CardContent></Card>
        <Card><CardContent className="p-4"><div className="text-xs text-rose-500 flex items-center gap-1"><AlertTriangle className="w-3.5 h-3.5" /> Overdue</div><div className="text-2xl font-display font-bold mt-1 text-rose-600" data-testid="stat-overdue">{overdue.length}</div></CardContent></Card>
        <Card><CardContent className="p-4"><div className="text-xs text-emerald-600 flex items-center gap-1"><CheckCircle2 className="w-3.5 h-3.5" /> Completed</div><div className="text-2xl font-display font-bold mt-1 text-emerald-600" data-testid="stat-done">{done.length}</div></CardContent></Card>
      </div>

      <div className="space-y-2 mb-8">
        <h2 className="text-sm font-semibold text-zinc-700">Upcoming & overdue</h2>
        {pending.length === 0 ? <div className="text-sm text-zinc-500 py-6 text-center">No pending follow-ups. Schedule one from a lead's page.</div>
          : pending.sort((a, b) => new Date(a.due_date) - new Date(b.due_date)).map((t) => <Row key={t.id} t={t} />)}
      </div>

      {done.length > 0 && (
        <div className="space-y-2">
          <h2 className="text-sm font-semibold text-zinc-700">Completed</h2>
          {done.map((t) => <Row key={t.id} t={t} />)}
        </div>
      )}
    </div>
  );
}
