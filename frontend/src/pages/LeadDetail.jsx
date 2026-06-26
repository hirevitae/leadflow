import { useEffect, useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { api, STAGES, formatApiError } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import StageBadge from "@/components/StageBadge";
import WhatsAppPanel from "@/components/WhatsAppPanel";
import AICallerPanel from "@/components/AICallerPanel";
import { toast } from "sonner";
import { ArrowLeft, Mail, Phone, BookOpen, Globe, Flag, Trash2, Sparkles, Flame } from "lucide-react";

const activityIcon = {
  lead_created: "🆕",
  stage_changed: "➡️",
  whatsapp_sent: "💬",
  ai_call: "📞",
  note: "📝",
};

export default function LeadDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const [lead, setLead] = useState(null);
  const [activities, setActivities] = useState([]);
  const [note, setNote] = useState("");

  const loadLead = async () => {
    const { data } = await api.get(`/leads/${id}`);
    setLead(data);
  };
  const loadActs = async () => {
    const { data } = await api.get(`/leads/${id}/activities`);
    setActivities(data);
  };

  useEffect(() => { loadLead(); loadActs(); }, [id]);

  const changeStage = async (s) => {
    try {
      const { data } = await api.post(`/leads/${id}/stage`, { stage: s });
      setLead(data);
      loadActs();
      toast.success(`Moved to ${s.replace("_", " ")}`);
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    }
  };

  const addNote = async () => {
    if (!note.trim()) return;
    await api.post(`/leads/${id}/notes`, { text: note });
    setNote("");
    loadActs();
  };

  const deleteLead = async () => {
    if (!confirm("Delete this lead and all activity?")) return;
    await api.delete(`/leads/${id}`);
    toast.success("Lead deleted");
    nav("/leads");
  };

  const summarize = async () => {
    try {
      const { data } = await api.post(`/leads/${id}/summarize`);
      toast.success(`Interest score: ${data.interest_score}/100`);
      loadLead();
    } catch { toast.error("Summary failed"); }
  };

  if (!lead) return <div className="p-8 text-zinc-500">Loading…</div>;

  return (
    <div className="p-8 max-w-7xl mx-auto">
      <Link to="/leads" className="text-sm text-zinc-500 hover:text-zinc-900 inline-flex items-center mb-4" data-testid="back-to-leads">
        <ArrowLeft className="w-4 h-4 mr-1" /> Back to leads
      </Link>

      <div className="flex items-start justify-between mb-6">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="font-display font-bold text-3xl tracking-tight" data-testid="lead-name">{lead.name}</h1>
            <StageBadge stage={lead.stage} />
            <span className={`text-xs px-2 py-0.5 rounded border capitalize ${
              lead.priority === "high" ? "bg-rose-50 text-rose-700 border-rose-200" :
              lead.priority === "low" ? "bg-zinc-100 text-zinc-600 border-zinc-200" :
              "bg-amber-50 text-amber-700 border-amber-200"}`}>
              {lead.priority} priority
            </span>
          </div>
          <div className="flex items-center gap-5 mt-3 text-sm text-zinc-600">
            <span className="inline-flex items-center gap-1.5"><Phone className="w-4 h-4" /> <span className="mono">{lead.phone}</span></span>
            {lead.email && <span className="inline-flex items-center gap-1.5"><Mail className="w-4 h-4" /> {lead.email}</span>}
            {lead.course && <span className="inline-flex items-center gap-1.5"><BookOpen className="w-4 h-4" /> {lead.course}</span>}
            <span className="inline-flex items-center gap-1.5 capitalize"><Globe className="w-4 h-4" /> {lead.language}</span>
            <span className="inline-flex items-center gap-1.5 capitalize"><Flag className="w-4 h-4" /> {lead.source}</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Select value={lead.stage} onValueChange={changeStage}>
            <SelectTrigger className="w-48" data-testid="change-stage-select"><SelectValue /></SelectTrigger>
            <SelectContent>
              {STAGES.map((s) => <SelectItem key={s.key} value={s.key}>{s.label}</SelectItem>)}
            </SelectContent>
          </Select>
          <Button variant="outline" onClick={summarize} data-testid="summarize-btn">
            <Sparkles className="w-4 h-4 mr-1" /> AI Summary
          </Button>
          <Button variant="outline" onClick={deleteLead} data-testid="delete-lead-btn">
            <Trash2 className="w-4 h-4 mr-1" /> Delete
          </Button>
        </div>
      </div>

      {lead.convo_summary && (
        <div className="mb-4 p-4 rounded-md border border-amber-200 bg-amber-50/60 flex items-start gap-3" data-testid="lead-summary-card">
          <Flame className="w-5 h-5 text-amber-600 mt-0.5" />
          <div className="flex-1">
            <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-amber-700 font-semibold">
              Interest score
              <span className="px-2 py-0.5 rounded bg-amber-200 text-amber-900 mono">{lead.interest_score ?? 0}/100</span>
            </div>
            <div className="text-sm text-zinc-800 mt-1">{lead.convo_summary}</div>
            {lead.next_step && <div className="text-xs text-zinc-600 mt-1"><b>Next:</b> {lead.next_step}</div>}
          </div>
        </div>
      )}

      <Tabs defaultValue="conversations" className="w-full">
        <TabsList data-testid="lead-tabs">
          <TabsTrigger value="conversations" data-testid="tab-conversations">Conversations</TabsTrigger>
          <TabsTrigger value="activity" data-testid="tab-activity">Activity ({activities.length})</TabsTrigger>
          <TabsTrigger value="notes" data-testid="tab-notes">Notes</TabsTrigger>
        </TabsList>

        <TabsContent value="conversations" className="mt-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <WhatsAppPanel lead={lead} onActivity={() => { loadActs(); loadLead(); }} />
            <AICallerPanel lead={lead} onActivity={() => { loadActs(); loadLead(); }} />
          </div>
        </TabsContent>

        <TabsContent value="activity" className="mt-4">
          <Card>
            <CardContent className="p-6">
              {activities.length === 0 ? (
                <div className="text-sm text-zinc-500 text-center py-10">No activity yet.</div>
              ) : (
                <ol className="relative border-l border-zinc-200 ml-2">
                  {activities.map((a) => (
                    <li key={a.id} className="mb-5 ml-4" data-testid={`activity-${a.id}`}>
                      <div className="absolute -left-1.5 mt-1.5 w-3 h-3 rounded-full bg-white border border-zinc-300" />
                      <div className="text-sm">
                        <span className="mr-1.5">{activityIcon[a.kind] || "•"}</span>
                        {a.text}
                      </div>
                      <div className="text-xs text-zinc-500 mt-0.5">
                        {new Date(a.created_at).toLocaleString()} · {a.user_name}
                      </div>
                    </li>
                  ))}
                </ol>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="notes" className="mt-4">
          <Card>
            <CardContent className="p-6 space-y-3">
              <Textarea rows={4} placeholder="Add a manual follow-up note…" value={note}
                onChange={(e) => setNote(e.target.value)} data-testid="note-input" />
              <div className="flex justify-end">
                <Button onClick={addNote} className="bg-blue-600 hover:bg-blue-700" data-testid="add-note-btn">Save note</Button>
              </div>
              <div className="pt-4 border-t border-zinc-200 space-y-3">
                {activities.filter((a) => a.kind === "note").map((n) => (
                  <div key={n.id} className="p-3 rounded-md bg-zinc-50 border border-zinc-200">
                    <div className="text-sm">{n.text}</div>
                    <div className="text-xs text-zinc-500 mt-1">{new Date(n.created_at).toLocaleString()} · {n.user_name}</div>
                  </div>
                ))}
                {activities.filter((a) => a.kind === "note").length === 0 && (
                  <div className="text-sm text-zinc-500 text-center py-4">No notes yet.</div>
                )}
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
