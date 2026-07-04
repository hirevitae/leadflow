import { useState, useEffect, useCallback } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Card, CardContent } from "@/components/ui/card";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { Pause, Play, XCircle } from "lucide-react";

const STATUS_TINT = {
  sending: "bg-blue-100 text-blue-700", scheduled: "bg-amber-100 text-amber-700",
  testing: "bg-violet-100 text-violet-700",
  paused: "bg-zinc-200 text-zinc-700", completed: "bg-emerald-100 text-emerald-700",
  canceled: "bg-rose-100 text-rose-700", draft: "bg-zinc-100 text-zinc-600",
};

export const EmailCampaignDetail = ({ campaignId, open, onOpenChange, onChanged }) => {
  const [c, setC] = useState(null);
  const [an, setAn] = useState(null);

  const load = useCallback(async () => {
    if (!campaignId) return;
    try {
      const [{ data }, { data: a }] = await Promise.all([
        api.get(`/email/campaigns/${campaignId}`),
        api.get(`/email/campaigns/${campaignId}/analytics`),
      ]);
      setC(data); setAn(a);
    } catch (e) { /* ignore */ }
  }, [campaignId]);

  useEffect(() => { if (open) load(); }, [open, load]);
  useEffect(() => {
    if (!open || !c) return;
    if (!["sending", "scheduled"].includes(c.status)) return;
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [open, c, load]);

  const act = async (action) => {
    try { await api.post(`/email/campaigns/${campaignId}/${action}`); toast.success(`Campaign ${action}d`); load(); onChanged?.(); }
    catch { toast.error("Action failed"); }
  };

  if (!c) return null;
  const s = c.stats || {};
  const done = (s.sent || 0) + (s.failed || 0);
  const pct = s.total ? Math.round(done / s.total * 100) : 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto" data-testid="campaign-detail">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-3">
            {c.name}
            <Badge className={STATUS_TINT[c.status] || ""} data-testid="campaign-status">{c.status}</Badge>
          </DialogTitle>
        </DialogHeader>

        <div className="flex items-center gap-2 mb-2">
          {["sending", "scheduled"].includes(c.status) && <Button size="sm" variant="outline" onClick={() => act("pause")} data-testid="pause-btn"><Pause className="w-3.5 h-3.5 mr-1" /> Pause</Button>}
          {c.status === "paused" && <Button size="sm" variant="outline" onClick={() => act("resume")} data-testid="resume-btn"><Play className="w-3.5 h-3.5 mr-1" /> Resume</Button>}
          {["sending", "scheduled", "paused"].includes(c.status) && <Button size="sm" variant="outline" className="text-rose-600" onClick={() => act("cancel")} data-testid="cancel-btn"><XCircle className="w-3.5 h-3.5 mr-1" /> Cancel</Button>}
        </div>

        <div className="mb-4">
          <div className="flex justify-between text-xs text-zinc-500 mb-1"><span>Progress</span><span data-testid="progress-label">{done}/{s.total} ({pct}%)</span></div>
          <Progress value={pct} data-testid="campaign-progress" />
        </div>

        {c.recurrence?.enabled && <div className="text-xs text-zinc-500 mb-3" data-testid="recurrence-badge">🔁 Recurring · {c.recurrence.frequency}{c.is_recurrence_child_of ? " (auto-generated run)" : ""}</div>}

        {c.ab?.enabled && (
          <div className="mb-4 border border-violet-100 bg-violet-50/40 rounded-md p-3" data-testid="ab-results">
            <div className="text-sm font-semibold text-violet-800 mb-2">A/B test {c.ab.winner_variant_id ? `· Winner: ${c.ab.winner_name}` : "· in progress"}</div>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
              {(c.ab.variants || []).map((v) => {
                const vs = v.stats || {}; const sent = Math.max(vs.sent || 0, 1);
                const isWin = v.id === c.ab.winner_variant_id;
                return (
                  <div key={v.id} className={`rounded-md border p-2 ${isWin ? "border-emerald-400 bg-emerald-50" : "border-zinc-200 bg-white"}`} data-testid={`variant-result-${v.name}`}>
                    <div className="text-xs font-semibold flex items-center gap-1">{v.name} {isWin && <span className="text-emerald-600">★</span>}</div>
                    <div className="text-[11px] text-zinc-500 truncate">{v.subject}</div>
                    <div className="text-[11px] text-zinc-600 mt-1">{vs.sent || 0} sent · {Math.round((vs.clicked || 0) / sent * 100)}% CTR · {Math.round((vs.opened || 0) / sent * 100)}% open</div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        <div className="grid grid-cols-3 md:grid-cols-6 gap-2 mb-4">
          {[["Sent", s.sent], ["Delivered", s.delivered], ["Opened", s.opened], ["Clicked", s.clicked], ["Bounced", s.bounced], ["Failed", s.failed]].map(([k, v]) => (
            <Card key={k} data-testid={`stat-${k.toLowerCase()}`}><CardContent className="p-3"><div className="text-xl font-bold">{v || 0}</div><div className="text-[11px] text-zinc-500">{k}</div></CardContent></Card>
          ))}
        </div>

        {an && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-4">
            {[["Delivery", an.rates.delivery_rate], ["Open", an.rates.open_rate], ["Click", an.rates.click_rate], ["Bounce", an.rates.bounce_rate]].map(([k, v]) => (
              <div key={k} className="rounded-md border border-zinc-200 p-2.5"><div className="text-lg font-semibold text-zinc-800">{v}%</div><div className="text-[11px] text-zinc-500">{k} rate</div></div>
            ))}
          </div>
        )}

        {an?.clicks_over_time?.length > 0 && (
          <div className="h-48 mb-4" data-testid="clicks-chart">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={an.clicks_over_time}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="t" fontSize={10} tickFormatter={(v) => v.slice(11)} /><YAxis allowDecimals={false} fontSize={10} /><Tooltip /><Bar dataKey="n" fill="#2563eb" radius={[4, 4, 0, 0]} /></BarChart>
            </ResponsiveContainer>
          </div>
        )}

        <div>
          <div className="text-sm font-semibold text-zinc-700 mb-1">Recent activity</div>
          {(!c.recent_events || c.recent_events.length === 0) ? <div className="text-sm text-zinc-400">No tracking events yet. Events appear once Resend delivers/opens are reported (requires a verified sending domain).</div> : (
            <ul className="divide-y divide-zinc-100 text-sm" data-testid="events-list">
              {c.recent_events.map((e) => (
                <li key={e.id} className="py-1.5 flex items-center gap-2"><Badge variant="outline" className="capitalize text-[11px]">{e.type}</Badge><span className="text-zinc-600 truncate">{e.email}</span><span className="text-xs text-zinc-400 ml-auto">{new Date(e.created_at).toLocaleTimeString()}</span></li>
              ))}
            </ul>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
};
