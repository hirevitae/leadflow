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
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { ArrowLeft, Bot, Upload, FileText, Trash2, Send, Sparkles, BookOpen, Loader2, GraduationCap, BarChart3, ClipboardCheck, History, RotateCcw, AlertTriangle, Check, Star, Flag, Phone } from "lucide-react";

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

  // Phase 2 state
  const [qa, setQa] = useState([]);
  const [newQa, setNewQa] = useState({ question: "", answer: "" });
  const [unknowns, setUnknowns] = useState([]);
  const [teach, setTeach] = useState({});
  const [analytics, setAnalytics] = useState(null);
  const [calls, setCalls] = useState([]);
  const [versions, setVersions] = useState([]);

  const load = async () => {
    try {
      const [a, d, m] = await Promise.all([api.get(`/agents/${id}`), api.get(`/agents/${id}/knowledge`), api.get("/agents/meta")]);
      setAgent(a.data); setDocs(d.data); setMeta(m.data);
    } catch (e) { toast.error("Could not load agent"); }
  };
  const loadTraining = async () => {
    try {
      const [q, u, v] = await Promise.all([api.get(`/agents/${id}/qa`), api.get(`/agents/${id}/unknowns`), api.get(`/agents/${id}/prompt-versions`)]);
      setQa(q.data); setUnknowns(u.data); setVersions(v.data);
    } catch (e) { /* silent */ }
  };
  const loadAnalytics = async () => {
    try { const { data } = await api.get(`/agents/${id}/analytics`); setAnalytics(data); } catch (e) { /* silent */ }
  };
  const loadCalls = async () => {
    try { const { data } = await api.get(`/agents/${id}/calls`); setCalls(data); } catch (e) { /* silent */ }
  };
  useEffect(() => { load(); loadTraining(); /* eslint-disable-next-line */ }, [id]);

  const save = async () => {
    setSaving(true);
    try {
      const { data } = await api.put(`/agents/${id}`, agent);
      setAgent(data); toast.success("Agent saved"); loadTraining();
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
      setMsgs((m) => [...m, { role: "ai", text: data.reply, sources: data.sources, confidence: data.confidence, grounded: data.grounded }]);
    } catch (e) {
      setMsgs((m) => [...m, { role: "ai", text: formatApiError(e.response?.data?.detail) || "Error", error: true }]);
    } finally { setThinking(false); loadTraining(); }
  };

  // Phase 2 actions
  const addQa = async () => {
    if (!newQa.question.trim() || !newQa.answer.trim()) { toast.error("Question and answer required"); return; }
    try {
      await api.post(`/agents/${id}/qa`, newQa);
      setNewQa({ question: "", answer: "" }); toast.success("Q&A added to training"); loadTraining(); load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail) || "Failed"); }
  };
  const teachUnknown = async (q) => {
    const answer = (teach[q] || "").trim();
    if (!answer) { toast.error("Type the answer to teach the agent"); return; }
    try {
      await api.post(`/agents/${id}/unknowns/resolve`, { question: q, answer });
      toast.success("Agent taught — added to knowledge"); setTeach((t) => ({ ...t, [q]: "" })); loadTraining(); load();
    } catch (e) { toast.error("Failed"); }
  };
  const dismissUnknown = async (q) => {
    try { await api.delete(`/agents/${id}/unknowns`, { params: { question: q } }); loadTraining(); } catch { toast.error("Failed"); }
  };
  const rollback = async (versionId) => {
    try {
      const { data } = await api.post(`/agents/${id}/prompt-versions/rollback`, { version_id: versionId });
      setAgent((a) => ({ ...a, system_prompt: data.system_prompt })); toast.success("Prompt rolled back"); loadTraining();
    } catch (e) { toast.error("Rollback failed"); }
  };
  const reviewCall = async (callId, patch) => {
    try {
      await api.post(`/agents/${id}/calls/${callId}/review`, patch);
      toast.success("Review saved"); loadCalls();
    } catch (e) { toast.error("Failed"); }
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

      <Tabs defaultValue="settings" onValueChange={(v) => { if (v === "analytics") loadAnalytics(); if (v === "qa") loadCalls(); if (v === "training") loadTraining(); }}>
        <TabsList className="flex-wrap h-auto">
          <TabsTrigger value="settings" data-testid="agent-tab-settings">Settings & Prompts</TabsTrigger>
          <TabsTrigger value="knowledge" data-testid="agent-tab-knowledge"><BookOpen className="w-4 h-4 mr-1" /> Knowledge ({docs.length})</TabsTrigger>
          <TabsTrigger value="training" data-testid="agent-tab-training"><GraduationCap className="w-4 h-4 mr-1" /> Training</TabsTrigger>
          <TabsTrigger value="playground" data-testid="agent-tab-playground"><Sparkles className="w-4 h-4 mr-1" /> Playground</TabsTrigger>
          <TabsTrigger value="analytics" data-testid="agent-tab-analytics"><BarChart3 className="w-4 h-4 mr-1" /> Analytics</TabsTrigger>
          <TabsTrigger value="qa" data-testid="agent-tab-qa"><ClipboardCheck className="w-4 h-4 mr-1" /> QA Review</TabsTrigger>
        </TabsList>

        <TabsContent value="settings" className="mt-4 space-y-4">
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

          <Card><CardContent className="p-5">
            <div className="flex items-center gap-2 mb-3"><History className="w-4 h-4 text-zinc-500" /><div className="text-sm font-semibold text-zinc-700">Prompt version history</div></div>
            {versions.length === 0 ? <div className="text-sm text-zinc-400" data-testid="versions-empty">No previous versions yet. Edits to the system prompt are saved here automatically.</div> : (
              <ul className="divide-y divide-zinc-100" data-testid="prompt-versions-list">
                {versions.map((v) => (
                  <li key={v.id} className="py-2.5 flex items-start gap-3" data-testid={`version-${v.id}`}>
                    <div className="flex-1 min-w-0">
                      <div className="text-xs text-zinc-400">{new Date(v.created_at).toLocaleString()} · {v.created_by || "system"}</div>
                      <div className="text-sm text-zinc-700 truncate">{v.system_prompt || <span className="italic text-zinc-400">(empty prompt)</span>}</div>
                    </div>
                    <Button variant="outline" size="sm" onClick={() => rollback(v.id)} data-testid={`rollback-${v.id}`}><RotateCcw className="w-3.5 h-3.5 mr-1" /> Restore</Button>
                  </li>
                ))}
              </ul>
            )}
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

        <TabsContent value="training" className="mt-4 space-y-4">
          <Card><CardContent className="p-5 space-y-3">
            <div className="flex items-center gap-2"><GraduationCap className="w-4 h-4 text-blue-600" /><div className="text-sm font-semibold text-zinc-700">Add a Q&A pair</div></div>
            <p className="text-xs text-zinc-400">Teach exact answers to common questions. These are added to the knowledge base and retrieved during chats & calls.</p>
            <Input placeholder="Question (e.g. What is the course fee?)" value={newQa.question} onChange={(e) => setNewQa({ ...newQa, question: e.target.value })} data-testid="qa-question-input" />
            <Textarea rows={2} placeholder="Answer" value={newQa.answer} onChange={(e) => setNewQa({ ...newQa, answer: e.target.value })} data-testid="qa-answer-input" />
            <div className="flex justify-end"><Button onClick={addQa} className="bg-blue-600 hover:bg-blue-700" data-testid="add-qa-btn">Add to training</Button></div>
          </CardContent></Card>

          <Card><CardContent className="p-5">
            <div className="flex items-center gap-2 mb-3"><AlertTriangle className="w-4 h-4 text-amber-500" /><div className="text-sm font-semibold text-zinc-700">Knowledge gaps — questions the agent couldn't answer</div></div>
            {unknowns.length === 0 ? <div className="text-sm text-zinc-400" data-testid="unknowns-empty">No gaps detected yet. When the agent can't answer confidently, the question shows up here.</div> : (
              <ul className="space-y-3" data-testid="unknowns-list">
                {unknowns.map((u) => (
                  <li key={u.question} className="border border-amber-100 bg-amber-50/40 rounded-md p-3" data-testid={`unknown-${u.question}`}>
                    <div className="flex items-center gap-2 mb-2"><span className="text-sm font-medium text-zinc-800">{u.question_text || u.question}</span><Badge variant="outline" className="text-[11px]">asked {u.count}×</Badge></div>
                    <Textarea rows={2} placeholder="Teach the correct answer…" value={teach[u.question] || ""} onChange={(e) => setTeach((t) => ({ ...t, [u.question]: e.target.value }))} data-testid={`teach-input-${u.question}`} />
                    <div className="flex justify-end gap-2 mt-2">
                      <Button variant="ghost" size="sm" onClick={() => dismissUnknown(u.question)} data-testid={`dismiss-${u.question}`}>Dismiss</Button>
                      <Button size="sm" className="bg-blue-600 hover:bg-blue-700" onClick={() => teachUnknown(u.question)} data-testid={`teach-btn-${u.question}`}><Check className="w-3.5 h-3.5 mr-1" /> Teach agent</Button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </CardContent></Card>

          <Card><CardContent className="p-0">
            <div className="p-4 text-sm font-semibold text-zinc-700 border-b border-zinc-100">Saved Q&A ({qa.length})</div>
            {qa.length === 0 ? <div className="p-6 text-center text-zinc-400 text-sm" data-testid="qa-empty">No Q&A pairs yet.</div> : (
              <ul className="divide-y divide-zinc-100" data-testid="qa-list">
                {qa.map((d) => (
                  <li key={d.id} className="flex items-center gap-3 p-3" data-testid={`qa-item-${d.id}`}>
                    <FileText className="w-4 h-4 text-zinc-400" />
                    <div className="flex-1 min-w-0"><div className="text-sm font-medium truncate">{d.title}</div><div className="text-xs text-zinc-400">{d.chars} chars</div></div>
                    <Button variant="ghost" size="sm" className="text-rose-600" onClick={() => delDoc(d.id)} data-testid={`del-qa-${d.id}`}><Trash2 className="w-4 h-4" /></Button>
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

        <TabsContent value="analytics" className="mt-4 space-y-4" data-testid="analytics-tab-content">
          {!analytics ? <div className="text-sm text-zinc-400 p-4">Loading analytics…</div> : (
            <>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {[
                  { label: "Chats", value: analytics.chats, testid: "stat-chats" },
                  { label: "Calls", value: analytics.calls, testid: "stat-calls" },
                  { label: "Grounded rate", value: `${analytics.grounded_rate}%`, testid: "stat-grounded" },
                  { label: "Avg confidence", value: analytics.avg_confidence, testid: "stat-confidence" },
                  { label: "Knowledge docs", value: analytics.knowledge_docs, testid: "stat-docs" },
                  { label: "Open gaps", value: analytics.unknown_questions, testid: "stat-gaps" },
                ].map((s) => (
                  <Card key={s.label} data-testid={s.testid}><CardContent className="p-4"><div className="text-2xl font-bold text-zinc-800">{s.value}</div><div className="text-xs text-zinc-500">{s.label}</div></CardContent></Card>
                ))}
              </div>
              <Card><CardContent className="p-5">
                <div className="text-sm font-semibold text-zinc-700 mb-3">Top questions</div>
                {(!analytics.top_questions || analytics.top_questions.length === 0) ? <div className="text-sm text-zinc-400">No questions logged yet.</div> : (
                  <div className="h-64" data-testid="top-questions-chart">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={analytics.top_questions} layout="vertical" margin={{ left: 40 }}>
                        <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                        <XAxis type="number" allowDecimals={false} fontSize={11} />
                        <YAxis type="category" dataKey="q" width={160} fontSize={11} tickFormatter={(v) => v.length > 24 ? v.slice(0, 24) + "…" : v} />
                        <Tooltip />
                        <Bar dataKey="n" fill="#2563eb" radius={[0, 4, 4, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </CardContent></Card>
              <Card><CardContent className="p-5">
                <div className="text-sm font-semibold text-zinc-700 mb-3">Call outcomes</div>
                {(!analytics.outcomes || Object.keys(analytics.outcomes).length === 0) ? <div className="text-sm text-zinc-400">No calls yet.</div> : (
                  <div className="flex flex-wrap gap-2" data-testid="outcomes-list">
                    {Object.entries(analytics.outcomes).map(([k, v]) => (
                      <Badge key={k} variant="outline" className="capitalize text-sm py-1 px-3">{k.replace("_", " ")}: {v}</Badge>
                    ))}
                  </div>
                )}
              </CardContent></Card>
            </>
          )}
        </TabsContent>

        <TabsContent value="qa" className="mt-4 space-y-3" data-testid="qa-review-tab-content">
          {calls.length === 0 ? <div className="text-sm text-zinc-400 p-4" data-testid="calls-empty">No calls generated by this agent yet. Run an AI call from a lead with this agent assigned.</div> : (
            calls.map((c) => (
              <Card key={c.id} data-testid={`call-${c.id}`}><CardContent className="p-4 space-y-3">
                <div className="flex items-center gap-2 flex-wrap">
                  <Phone className="w-4 h-4 text-zinc-500" />
                  <span className="text-sm font-medium capitalize">Outcome: {(c.outcome || "unknown").replace("_", " ")}</span>
                  <Badge variant="outline" className="text-[11px]">{c.language}</Badge>
                  <span className="text-xs text-zinc-400 ml-auto">{new Date(c.created_at).toLocaleString()}</span>
                  {c.qa_reviewed && <Badge className="bg-emerald-100 text-emerald-700 text-[11px]">Reviewed</Badge>}
                  {c.qa_flagged && <Badge className="bg-rose-100 text-rose-700 text-[11px]">Flagged</Badge>}
                </div>
                <div className="text-sm text-zinc-600 italic">{c.summary}</div>
                <div className="max-h-48 overflow-y-auto space-y-1.5 bg-zinc-50 rounded-md p-3" data-testid={`transcript-${c.id}`}>
                  {(c.transcript || []).map((t, i) => (
                    <div key={i} className="text-sm"><span className={`font-medium ${t.speaker === "AI" ? "text-blue-700" : "text-zinc-700"}`}>{t.speaker}:</span> <span className="text-zinc-700">{t.text}</span></div>
                  ))}
                </div>
                <div className="flex items-center gap-3 border-t border-zinc-100 pt-2.5">
                  <div className="flex items-center gap-1">
                    {[1, 2, 3, 4, 5].map((n) => (
                      <button key={n} onClick={() => reviewCall(c.id, { rating: n })} data-testid={`rate-${c.id}-${n}`}>
                        <Star className={`w-4 h-4 ${(c.qa_rating || 0) >= n ? "fill-amber-400 text-amber-400" : "text-zinc-300"}`} />
                      </button>
                    ))}
                  </div>
                  <Button variant="ghost" size="sm" className={c.qa_flagged ? "text-rose-600" : "text-zinc-500"} onClick={() => reviewCall(c.id, { flagged: !c.qa_flagged })} data-testid={`flag-${c.id}`}><Flag className="w-3.5 h-3.5 mr-1" /> {c.qa_flagged ? "Unflag" : "Flag"}</Button>
                  <Button variant="outline" size="sm" className="ml-auto" onClick={() => reviewCall(c.id, { note: c.qa_note || "" })} data-testid={`mark-reviewed-${c.id}`}><ClipboardCheck className="w-3.5 h-3.5 mr-1" /> Mark reviewed</Button>
                </div>
              </CardContent></Card>
            ))
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
