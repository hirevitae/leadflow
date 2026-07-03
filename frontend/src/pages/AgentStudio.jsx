import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, formatApiError } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import { Bot, Plus, BookOpen, Sparkles } from "lucide-react";

export default function AgentStudio() {
  const nav = useNavigate();
  const [agents, setAgents] = useState([]);
  const [meta, setMeta] = useState({ personalities: [], categories: [] });
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", category: "Custom", industry: "", personality: "professional", goal: "" });

  const load = async () => {
    try {
      const [a, m] = await Promise.all([api.get("/agents"), api.get("/agents/meta")]);
      setAgents(a.data); setMeta(m.data);
    } catch (e) { toast.error("Could not load agents"); }
  };
  useEffect(() => { load(); }, []);

  const create = async () => {
    try {
      const { data } = await api.post("/agents", form);
      toast.success(`${data.name} created`);
      setOpen(false); nav(`/ai-studio/${data.id}`);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail) || "Create failed"); }
  };

  return (
    <div className="p-8 max-w-6xl mx-auto" data-testid="agent-studio-page">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="font-display font-bold text-3xl tracking-tight flex items-center gap-2"><Bot className="w-7 h-7 text-blue-600" /> AI Agent Studio</h1>
          <p className="text-sm text-zinc-500 mt-1">Create, train and test specialized AI agents — each with its own knowledge, prompts and personality.</p>
        </div>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button className="bg-blue-600 hover:bg-blue-700" data-testid="create-agent-btn"><Plus className="w-4 h-4 mr-1.5" /> New Agent</Button>
          </DialogTrigger>
          <DialogContent data-testid="create-agent-dialog">
            <DialogHeader><DialogTitle className="font-display">Create AI Agent</DialogTitle></DialogHeader>
            <div className="space-y-3">
              <Input placeholder="Agent name (e.g. Admission Counsellor)" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="agent-name-input" />
              <div className="grid grid-cols-2 gap-2">
                <Select value={form.category} onValueChange={(v) => setForm({ ...form, category: v })}>
                  <SelectTrigger data-testid="agent-category-select"><SelectValue /></SelectTrigger>
                  <SelectContent>{meta.categories.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
                </Select>
                <Select value={form.personality} onValueChange={(v) => setForm({ ...form, personality: v })}>
                  <SelectTrigger data-testid="agent-personality-select"><SelectValue /></SelectTrigger>
                  <SelectContent>{meta.personalities.map((p) => <SelectItem key={p} value={p} className="capitalize">{p}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <Input placeholder="Industry (e.g. EdTech)" value={form.industry} onChange={(e) => setForm({ ...form, industry: e.target.value })} data-testid="agent-industry-input" />
              <Textarea rows={2} placeholder="Goal — what should this agent achieve?" value={form.goal} onChange={(e) => setForm({ ...form, goal: e.target.value })} data-testid="agent-goal-input" />
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
              <Button onClick={create} disabled={!form.name.trim()} className="bg-blue-600 hover:bg-blue-700" data-testid="submit-agent-btn">Create</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      {agents.length === 0 ? (
        <div className="text-center text-zinc-500 py-20" data-testid="agents-empty">No agents yet. Create your first AI agent to get started.</div>
      ) : (
        <div className="grid md:grid-cols-3 gap-4">
          {agents.map((a) => (
            <Card key={a.id} className="cursor-pointer hover:shadow-md transition-shadow" onClick={() => nav(`/ai-studio/${a.id}`)} data-testid={`agent-card-${a.id}`}>
              <CardContent className="p-5">
                <div className="flex items-start justify-between mb-2">
                  <div className="w-10 h-10 rounded-md bg-blue-50 text-blue-700 flex items-center justify-center"><Bot className="w-5 h-5" /></div>
                  <Badge variant="outline" className={a.status === "active" ? "text-emerald-700 border-emerald-200 bg-emerald-50" : "text-zinc-500"}>{a.status}</Badge>
                </div>
                <div className="font-display font-semibold">{a.name}</div>
                <div className="text-xs text-zinc-500 mt-0.5">{a.category} · <span className="capitalize">{a.personality}</span></div>
                <div className="flex items-center gap-3 mt-3 text-xs text-zinc-500">
                  <span className="inline-flex items-center gap-1"><BookOpen className="w-3.5 h-3.5" /> {a.knowledge_count} docs</span>
                  <span className="inline-flex items-center gap-1"><Sparkles className="w-3.5 h-3.5" /> {a.language}</span>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
