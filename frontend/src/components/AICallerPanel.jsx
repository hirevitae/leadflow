import { useEffect, useRef, useState } from "react";
import { api, formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import { Phone, PhoneCall, Languages, Radio } from "lucide-react";

export default function AICallerPanel({ lead, onActivity }) {
  const [lang, setLang] = useState(lead?.language === "hindi" ? "hindi" : "english");
  const [calls, setCalls] = useState([]);
  const [active, setActive] = useState(false);
  const [transcript, setTranscript] = useState([]);
  const [latest, setLatest] = useState(null);
  const [agents, setAgents] = useState([]);
  const [agentId, setAgentId] = useState("none");
  const [liveStatus, setLiveStatus] = useState(null);
  const pollRef = useRef(null);

  const load = async () => {
    const { data } = await api.get(`/leads/${lead.id}/calls`);
    setCalls(data);
    if (data[0]) setLatest(data[0]);
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [lead.id]);
  useEffect(() => { api.get("/agents").then(({ data }) => setAgents(data)).catch(() => {}); }, []);
  useEffect(() => () => clearInterval(pollRef.current), []);

  const startCall = async () => {
    setActive(true);
    setTranscript([]);
    try {
      const body = { language: lang };
      if (agentId !== "none") body.agent_id = agentId;
      const { data } = await api.post(`/leads/${lead.id}/calls`, body);
      for (let i = 0; i < data.transcript.length; i++) {
        await new Promise((r) => setTimeout(r, 700));
        setTranscript((t) => [...t, data.transcript[i]]);
      }
      await new Promise((r) => setTimeout(r, 500));
      setActive(false);
      setLatest(data);
      await load();
      onActivity?.();
      toast.success(`AI call (${lang}) completed`);
    } catch (e) {
      setActive(false);
      toast.error(formatApiError(e.response?.data?.detail) || "Call failed");
    }
  };

  const usingAgent = agentId !== "none";

  const startLiveCall = async () => {
    setActive(true); setTranscript([]); setLiveStatus("ringing");
    try {
      const body = { language: lang };
      if (agentId !== "none") body.agent_id = agentId;
      const { data } = await api.post(`/leads/${lead.id}/voice-call`, body);
      const cid = data.id;
      toast.success("Calling the lead's phone…");
      const done = ["completed", "failed", "busy", "no-answer", "canceled"];
      pollRef.current = setInterval(async () => {
        try {
          const { data: cl } = await api.get(`/leads/${lead.id}/calls`);
          const c = cl.find((x) => x.id === cid);
          if (!c) return;
          setTranscript(c.transcript || []);
          setLiveStatus(c.status);
          if (done.includes(c.status) || c.live === false) {
            clearInterval(pollRef.current);
            setActive(false); setLiveStatus(null); setLatest(c);
            await load(); onActivity?.();
            toast.success(`Call ${c.status}`);
          }
        } catch { /* keep polling */ }
      }, 3000);
    } catch (e) {
      setActive(false); setLiveStatus(null);
      toast.error(formatApiError(e.response?.data?.detail) || "Could not place call");
    }
  };

  return (
    <div className="border border-zinc-200 rounded-lg bg-white flex flex-col h-[560px]" data-testid="ai-caller-panel">
      <div className="px-4 py-3 border-b border-zinc-200 flex items-center gap-2">
        <Phone className="w-4 h-4 text-blue-600" />
        <div className="font-display font-semibold text-sm">AI Caller</div>
        <span className="ml-auto text-xs px-2 py-0.5 rounded border" style={{}} data-testid="ai-caller-mode">{usingAgent ? <span className="text-emerald-700 bg-emerald-50 border-emerald-200 px-2 py-0.5 rounded">AI AGENT</span> : <span className="text-amber-700 bg-amber-50 border-amber-200 px-2 py-0.5 rounded">SCRIPTED</span>}</span>
      </div>

      <div className="px-4 py-3 border-b border-zinc-200 flex items-center gap-2 flex-wrap">
        <Languages className="w-4 h-4 text-zinc-500" />
        <Select value={lang} onValueChange={setLang} disabled={active}>
          <SelectTrigger className="w-32" data-testid="call-language-select"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="english">English</SelectItem>
            <SelectItem value="hindi">हिन्दी (Hindi)</SelectItem>
          </SelectContent>
        </Select>
        <Select value={agentId} onValueChange={setAgentId} disabled={active}>
          <SelectTrigger className="w-44" data-testid="call-agent-select"><SelectValue placeholder="AI Agent" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="none">No agent (scripted)</SelectItem>
            {agents.map((a) => <SelectItem key={a.id} value={a.id}>{a.name}</SelectItem>)}
          </SelectContent>
        </Select>

        {!active ? (
          <div className="ml-auto flex items-center gap-2">
            <Button onClick={startCall} variant="outline" data-testid="start-call-btn">
              <Phone className="w-4 h-4 mr-1.5" /> Simulate
            </Button>
            <Button onClick={startLiveCall} className="bg-blue-600 hover:bg-blue-700" data-testid="start-live-call-btn">
              <PhoneCall className="w-4 h-4 mr-1.5" /> Live Call
            </Button>
          </div>
        ) : (
          <div className="ml-auto flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 pulse-ring" />
            <span className="text-sm text-emerald-700 font-medium" data-testid="live-call-status">
              {liveStatus ? <span className="inline-flex items-center gap-1"><Radio className="w-3.5 h-3.5" /> {liveStatus}</span> : "Call active"}
            </span>
          </div>
        )}
      </div>

      <div className="flex-1 overflow-auto p-4 bg-zinc-50" data-testid="call-transcript">
        {!active && transcript.length === 0 && !latest && (
          <div className="text-center text-sm text-zinc-500 py-10">
            Choose a language and click <span className="font-medium">Start AI Call</span> to begin a simulated outreach.
          </div>
        )}
        {(active ? transcript : (latest?.transcript || [])).map((t, i) => (
          <div key={i} className="mb-2">
            <div className="text-[10px] uppercase tracking-wide text-zinc-500 mb-0.5">{t.speaker}</div>
            <div className={`inline-block rounded-lg px-3 py-2 text-sm ${t.speaker === "AI" ? "bg-blue-50 text-blue-900" : "bg-white border border-zinc-200"}`}>
              {t.text}
            </div>
          </div>
        ))}
      </div>

      {latest && !active && (
        <div className="border-t border-zinc-200 px-4 py-2 text-xs text-zinc-600">
          <span className="font-medium">Summary:</span> {latest.summary} · Outcome: <span className="text-emerald-700 font-medium">{latest.outcome}</span>
        </div>
      )}

      {calls.length > 0 && (
        <div className="border-t border-zinc-200 px-4 py-2 text-xs text-zinc-500">
          {calls.length} previous AI call{calls.length > 1 ? "s" : ""}
        </div>
      )}
    </div>
  );
}
