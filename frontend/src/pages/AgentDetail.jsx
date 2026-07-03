import { useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api, formatApiError } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import { ArrowLeft, Bot, Upload, FileText, Trash2, Send, Sparkles, BookOpen, Loader2 } from "lucide-react";

export default function AgentDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const [agent, setAgent] = useState(null);
  const [meta, setMeta] = useState({ personalities: [], categories: [] });
  const [docs, setDocs] = useState([]);
  const [saving, setSaving] = useState(false);
  const [manual, setManual] = useState({ title: "", content: "" });
  const [msgs, setMsgs] = useState([]);
  const [chat, setChat] = useState("");
  const [thinking, setThinking] = useState(false);
  const fileRef = useRef();

  const load = async () => {
    try {
      const [a, d, m] = await Promise.all([api.get(`/agents/${id}`), api.get(`/agents/${id}/knowledge`), api.get("/agents/meta")]);
      setAgent(a.data); setDocs(d.data); setMeta(m.data);
    } catch (e) { toast.error("Could not load agent"); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [id]);

  const save = async () => {
    setSaving(true);
    try {
      const { data } = await api.put(`/agents/${id}`, agent);
      setAgent(data); toast.success("Agent saved");
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail) || "Save failed"); }
    finally { setSaving(false); }
  };

  const upload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const fd = new FormData(); fd.append("file", file);
    try {
      const { data } = await api.post(`/agents/${id}/knowledge/upload`, fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success(`Trained on ${file.name} (${data.chunks} chunks)`);
      load();
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail) || "Upload failed"); }
    finally { e.target.value = ""; }
  };

  const addManual = async () => {
    if (!manual.title.trim() || !manual.content.trim()) { toast.error("Title and content required"); return; }
    try {
      await api.post(`/agents/${id}/knowledge/text`, manual);
      setManual({ title: "", content: "" }); toast.success("Knowledge added"); load();
    } catch (e) { toast.error("Failed"); }
  };

  const delDoc = async (docId) => {
    try { await api.delete(`/agents/${id}/knowledge/${docId}`); load(); } catch { toast.error("Delete failed"); }
  };

  const send = async () => {
    if (!chat.trim()) return;
    const q = chat; setChat(""); setMsgs((m) => [...m, { role: "user", text: q }]); setThinking(true);
    try {
      const { data } = await api.post(`/agents/${id}/chat`, { message: q });
      setMsgs((m) => [...m, { role: "ai", text: data.reply, sources: data.sources, confidence: data.confidence }]);
    } catch (e) {
      setMsgs((m) => [...m, { role: "ai", text: formatApiError(e.response?.data?.detail) || "Error", error: true }]);
    } finally { setThinking(false); }
  };

  if (!agent) return <div className="p-8 text-zinc-500">Loading…</div>;
  const set = (k, v) => setAgent({ ...agent, [k]: v });

  return (
    <div className="p-8 max-w-5xl mx-auto" data-testid="agent-detail-page">
      <button onClick={() => nav("/ai-studio")} className="text-sm text-zinc-500 hover:text-zinc-800 inline-flex items-center gap-1 mb-4" data-testid="back-to-studio"><ArrowLeft className="w-4 h-4" /> AI Studio</button>
      <div className="flex items-center gap-3 mb-6">
        <div className="w-11 h-11 rounded-md bg-blue-50 text-blue-700 flex items-center justify-center"><Bot className="w-6 h-6" /></div>
        <div>
          <h1 className="font-display font-bold text-2xl">{agent.name}</h1>
          <div className="text-xs text-zinc-500">{agent.category} · {docs.length} knowledge docs</div>
        </div>
        <Badge variant="outline" className="ml-auto capitalize">{agent.status}</Badge>
      </div>

      <Tabs defaultValue="settings">
        <TabsList>
          <TabsTrigger value="settings" data-testid="agent-tab-settings">Settings & Prompts</TabsTrigger>
          <TabsTrigger value="knowledge" data-testid="agent-tab-knowledge"><BookOpen className="w-4 h-4 mr-1" /> Knowledge ({docs.length})</TabsTrigger>
          <TabsTrigger value="playground" data-testid="agent-tab-playground"><Sparkles className="w-4 h-4 mr-1" /> Playground</TabsTrigger>
        </TabsList>

        <TabsContent value="settings" className="mt-4">
          <Card><CardContent className="p-5 space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div><label className="text-xs font-medium text-zinc-600">Name</label><Input value={agent.name} onChange={(e) => set("name", e.target.value)} data-testid="set-name" /></div>
              <div><label className="text-xs font-medium text-zinc-600">Industry</label><Input value={agent.industry || ""} onChange={(e) => set("industry", e.target.value)} data-testid="set-industry" /></div>
              <div><label className="text-xs font-medium text-zinc-600">Category</label>
                <Select value={agent.category} onValueChange={(v) => set("category", v)}><SelectTrigger data-testid="set-category"><SelectValue /></SelectTrigger><SelectContent>{meta.categories.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent></Select>
              </div>
              <div><label className="text-xs font-medium text-zinc-600">Personality</label>
                <Select value={agent.personality} onValueChange={(v) => set("personality", v)}><SelectTrigger data-testid="set-personality"><SelectValue /></SelectTrigger><SelectContent>{meta.personalities.map((p) => <SelectItem key={p} value={p} className="capitalize">{p}</SelectItem>)}</SelectContent></Select>
              </div>
              <div><label className="text-xs font-medium text-zinc-600">Language</label>
                <Select value={agent.language} onValueChange={(v) => set("language", v)}><SelectTrigger data-testid="set-language"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="english">English</SelectItem><SelectItem value="hindi">Hindi</SelectItem></SelectContent></Select>
              </div>
              <div><label className="text-xs font-medium text-zinc-600">Status</label>
                <Select value={agent.status} onValueChange={(v) => set("status", v)}><SelectTrigger data-testid="set-status"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="draft">Draft</SelectItem><SelectItem value="active">Active</SelectItem></SelectContent></Select>
              </div>
            </div>
            <div><label className="text-xs font-medium text-zinc-600">Goal</label><Textarea rows={2} value={agent.goal || ""} onChange={(e) => set("goal", e.target.value)} data-testid="set-goal" /></div>
            <div><label className="text-xs font-medium text-zinc-600">System prompt (persona & rules)</label><Textarea rows={4} value={agent.system_prompt || ""} onChange={(e) => set("system_prompt", e.target.value)} placeholder="e.g. Be concise, always offer a free demo, never quote prices not in the knowledge base." data-testid="set-system-prompt" /></div>
            <div className="grid grid-cols-2 gap-3">
              <div><label className="text-xs font-medium text-zinc-600">Greeting</label><Textarea rows={2} value={agent.greeting || ""} onChange={(e) => set("greeting", e.target.value)} data-testid="set-greeting" /></div>
              <div><label className="text-xs font-medium text-zinc-600">Fallback (when unsure)</label><Textarea rows={2} value={agent.fallback || ""} onChange={(e) => set("fallback", e.target.value)} data-testid="set-fallback" /></div>
            </div>
            <div className="flex justify-end"><Button onClick={save} disabled={saving} className="bg-blue-600 hover:bg-blue-700" data-testid="save-agent-btn">{saving ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : null}Save agent</Button></div>
          </CardContent></Card>
        </TabsContent>

        <TabsContent value="knowledge" className="mt-4 space-y-4">
          <Card><CardContent className="p-5 space-y-3">
            <div className="flex items-center gap-2">
              <input ref={fileRef} type="file" className="hidden" accept=".pdf,.docx,.txt,.csv,.md,.xlsx,.html,.json" onChange={upload} data-testid="knowledge-file-input" />
              <Button variant="outline" onClick={() => fileRef.current.click()} data-testid="upload-knowledge-btn"><Upload className="w-4 h-4 mr-1.5" /> Upload document</Button>
              <span className="text-xs text-zinc-400">PDF, DOCX, TXT, CSV, XLSX, MD, HTML</span>
            </div>
            <div className="border-t border-zinc-100 pt-3 space-y-2">
              <div className="text-sm font-medium text-zinc-700">Or add text knowledge</div>
              <Input placeholder="Title (e.g. Pricing & Offers)" value={manual.title} onChange={(e) => setManual({ ...manual, title: e.target.value })} data-testid="manual-title-input" />
              <Textarea rows={3} placeholder="Paste facts, FAQs, scripts, policies…" value={manual.content} onChange={(e) => setManual({ ...manual, content: e.target.value })} data-testid="manual-content-input" />
              <div className="flex justify-end"><Button onClick={addManual} data-testid="add-manual-btn">Add knowledge</Button></div>
            </div>
          </CardContent></Card>
          <Card><CardContent className="p-0">
            {docs.length === 0 ? <div className="p-6 text-center text-zinc-500 text-sm" data-testid="knowledge-empty">No knowledge yet. Upload docs to train this agent.</div> : (
              <ul className="divide-y divide-zinc-100" data-testid="knowledge-list">
                {docs.map((d) => (
                  <li key={d.id} className="flex items-center gap-3 p-3" data-testid={`knowledge-doc-${d.id}`}>
                    <FileText className="w-4 h-4 text-zinc-400" />
                    <div className="flex-1 min-w-0"><div className="text-sm font-medium truncate">{d.title}</div><div className="text-xs text-zinc-400">{d.chunks} chunks · {d.chars} chars · {d.type}</div></div>
                    <Button variant="ghost" size="sm" className="text-rose-600" onClick={() => delDoc(d.id)} data-testid={`del-doc-${d.id}`}><Trash2 className="w-4 h-4" /></Button>
                  </li>
                ))}
              </ul>
            )}
          </CardContent></Card>
        </TabsContent>

        <TabsContent value="playground" className="mt-4">
          <Card><CardContent className="p-0 flex flex-col h-[520px]">
            <div className="flex-1 overflow-y-auto p-4 space-y-3" data-testid="playground-messages">
              {msgs.length === 0 && <div className="text-center text-zinc-400 text-sm pt-16">Ask your agent anything — it answers from its knowledge base.</div>}
              {msgs.map((m, i) => (
                <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                  <div className={`max-w-[80%] rounded-lg px-3 py-2 text-sm ${m.role === "user" ? "bg-blue-600 text-white" : m.error ? "bg-rose-50 text-rose-700 border border-rose-200" : "bg-zinc-100 text-zinc-800"}`}>
                    <div>{m.text}</div>
                    {m.role === "ai" && !m.error && m.sources?.length > 0 && (
                      <div className="mt-1.5 pt-1.5 border-t border-zinc-200 text-[11px] text-zinc-500">
                        Sources: {m.sources.map((s) => s.title).join(", ")} · confidence {Math.round((m.confidence || 0) * 100)}%
                      </div>
                    )}
                  </div>
                </div>
              ))}
              {thinking && <div className="text-xs text-zinc-400 flex items-center gap-1"><Loader2 className="w-3 h-3 animate-spin" /> thinking…</div>}
            </div>
            <div className="border-t border-zinc-200 p-3 flex gap-2">
              <Input value={chat} onChange={(e) => setChat(e.target.value)} onKeyDown={(e) => e.key === "Enter" && send()} placeholder="Type a question…" data-testid="playground-input" />
              <Button onClick={send} disabled={thinking || !chat.trim()} className="bg-blue-600 hover:bg-blue-700" data-testid="playground-send-btn"><Send className="w-4 h-4" /></Button>
            </div>
          </CardContent></Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
