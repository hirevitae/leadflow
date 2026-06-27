import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, STAGES, stageMeta } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import AddLeadDialog from "@/components/AddLeadDialog";
import StageBadge from "@/components/StageBadge";
import { Users, MessageCircle, Phone, TrendingUp, ArrowUpRight, CalendarClock, AlertTriangle } from "lucide-react";

const KPI = ({ icon: Icon, label, value, accent, testid }) => (
  <Card data-testid={testid}>
    <CardContent className="p-5">
      <div className="flex items-start justify-between">
        <div>
          <div className="text-xs uppercase tracking-wide text-zinc-500 font-semibold">{label}</div>
          <div className="font-display text-3xl font-bold mt-1.5">{value}</div>
        </div>
        <div className={`w-9 h-9 rounded-md flex items-center justify-center ${accent}`}>
          <Icon className="w-5 h-5" strokeWidth={1.75} />
        </div>
      </div>
    </CardContent>
  </Card>
);

export default function Dashboard() {
  const [analytics, setAnalytics] = useState(null);
  const [recent, setRecent] = useState([]);
  const [tasks, setTasks] = useState([]);

  const load = async () => {
    const [a, l, t] = await Promise.all([
      api.get("/analytics/overview"),
      api.get("/leads"),
      api.get("/tasks"),
    ]);
    setAnalytics(a.data);
    setRecent(l.data.slice(0, 6));
    setTasks(t.data);
  };
  useEffect(() => { load(); }, []);

  const toggleTask = async (t) => {
    try { await api.patch(`/tasks/${t.id}`, { done: !t.done }); load(); } catch { /* ignore */ }
  };

  const now = new Date();
  const endOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 23, 59, 59);
  const todayFollowups = tasks
    .filter((t) => !t.done && new Date(t.due_date) <= endOfToday)
    .sort((a, b) => new Date(a.due_date) - new Date(b.due_date));

  const totalNonLost = analytics ? analytics.total_leads - analytics.stages.lost : 0;

  return (
    <div className="p-8 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="font-display font-bold text-3xl tracking-tight">Dashboard</h1>
          <p className="text-sm text-zinc-500 mt-1">Snapshot of your lead pipeline & outreach activity.</p>
        </div>
        <AddLeadDialog onCreated={load} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <KPI testid="kpi-total-leads" icon={Users} label="Total leads" value={analytics?.total_leads ?? "—"} accent="bg-blue-50 text-blue-700" />
        <KPI testid="kpi-active" icon={TrendingUp} label="Active pipeline" value={totalNonLost || "—"} accent="bg-indigo-50 text-indigo-700" />
        <KPI testid="kpi-whatsapp" icon={MessageCircle} label="WhatsApp sent" value={analytics?.whatsapp_sent ?? "—"} accent="bg-emerald-50 text-emerald-700" />
        <KPI testid="kpi-calls" icon={Phone} label="AI calls" value={analytics?.ai_calls ?? "—"} accent="bg-violet-50 text-violet-700" />
      </div>

      <Card className="mb-8" data-testid="today-followups-widget">
        <CardContent className="p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-display font-semibold text-lg flex items-center gap-2">
              <CalendarClock className="w-5 h-5 text-blue-600" /> Today&apos;s follow-ups
              {todayFollowups.length > 0 && (
                <span className="text-xs px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 border border-blue-200" data-testid="today-followups-count">{todayFollowups.length}</span>
              )}
            </h2>
            <Link to="/followups" className="text-sm text-blue-600 inline-flex items-center" data-testid="goto-followups">
              All follow-ups <ArrowUpRight className="w-3.5 h-3.5 ml-1" />
            </Link>
          </div>
          {todayFollowups.length === 0 ? (
            <div className="text-sm text-zinc-500 py-6 text-center" data-testid="today-followups-empty">You&apos;re all caught up — no follow-ups due today.</div>
          ) : (
            <ul className="space-y-2">
              {todayFollowups.slice(0, 6).map((t) => {
                const due = new Date(t.due_date);
                const overdue = due < now;
                return (
                  <li key={t.id} className="flex items-center gap-3 p-2.5 rounded-md border border-zinc-200 hover:bg-zinc-50" data-testid={`today-task-${t.id}`}>
                    <Checkbox checked={t.done} onCheckedChange={() => toggleTask(t)} data-testid={`today-task-check-${t.id}`} />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium truncate">{t.title}</div>
                      <div className="text-xs text-zinc-500 mt-0.5 flex items-center gap-2">
                        <span>{due.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
                        {t.lead_name && <Link to={`/leads/${t.lead_id}`} className="text-blue-600 hover:underline">{t.lead_name}</Link>}
                      </div>
                    </div>
                    {overdue && <span className="text-xs px-2 py-0.5 rounded bg-rose-50 text-rose-700 border border-rose-200 inline-flex items-center gap-1"><AlertTriangle className="w-3 h-3" /> Overdue</span>}
                  </li>
                );
              })}
            </ul>
          )}
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-2">
          <CardContent className="p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-display font-semibold text-lg">Funnel</h2>
              <Link to="/pipeline" className="text-sm text-blue-600 inline-flex items-center" data-testid="goto-pipeline">
                Open pipeline <ArrowUpRight className="w-3.5 h-3.5 ml-1" />
              </Link>
            </div>
            <div className="space-y-3">
              {STAGES.map((s) => {
                const count = analytics?.stages?.[s.key] || 0;
                const max = Math.max(1, ...Object.values(analytics?.stages || { x: 1 }));
                const w = Math.round((count / max) * 100);
                return (
                  <div key={s.key} className="flex items-center gap-3" data-testid={`funnel-row-${s.key}`}>
                    <div className="w-36 text-sm text-zinc-700">{s.label}</div>
                    <div className="flex-1 h-6 bg-zinc-100 rounded">
                      <div
                        className={`h-6 rounded ${s.key === "enrolled" ? "bg-emerald-500" : s.key === "lost" ? "bg-rose-400" : "bg-blue-600"}`}
                        style={{ width: `${w}%` }}
                      />
                    </div>
                    <div className="w-10 text-right text-sm font-medium mono">{count}</div>
                  </div>
                );
              })}
            </div>
            <div className="flex gap-6 mt-6 pt-4 border-t border-zinc-200 text-sm">
              <div><span className="text-zinc-500">Conversion:</span> <span className="font-semibold">{analytics?.conv_rate ?? 0}%</span></div>
              <div><span className="text-zinc-500">Win rate:</span> <span className="font-semibold">{analytics?.win_rate ?? 0}%</span></div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <h2 className="font-display font-semibold text-lg mb-4">Recent leads</h2>
            {recent.length === 0 ? (
              <div className="text-sm text-zinc-500 py-8 text-center">No leads yet. Add your first one.</div>
            ) : (
              <ul className="divide-y divide-zinc-200">
                {recent.map((l) => (
                  <li key={l.id}>
                    <Link to={`/leads/${l.id}`} className="block py-3 hover:bg-zinc-50 px-2 -mx-2 rounded" data-testid={`recent-lead-${l.id}`}>
                      <div className="flex items-center justify-between">
                        <div>
                          <div className="font-medium text-sm">{l.name}</div>
                          <div className="text-xs text-zinc-500">{l.course || "—"} · {l.source}</div>
                        </div>
                        <StageBadge stage={l.stage} />
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
