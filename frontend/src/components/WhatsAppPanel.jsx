import { useEffect, useState } from "react";
import { api, formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import { Send, MessageCircle, Sparkles } from "lucide-react";

export default function WhatsAppPanel({ lead, onActivity }) {
  const [templates, setTemplates] = useState([]);
  const [messages, setMessages] = useState([]);
  const [body, setBody] = useState("");
  const [templateId, setTemplateId] = useState("custom");
  const [sending, setSending] = useState(false);
  const [refining, setRefining] = useState(false);

  const refine = async () => {
    if (!body.trim()) return;
    setRefining(true);
    try {
      const { data } = await api.post(`/leads/${lead.id}/refine-message`, { body });
      setBody(data.body); toast.success("Message polished");
    } catch { toast.error("Refine failed"); }
    finally { setRefining(false); }
  };

  useEffect(() => {
    api.get("/whatsapp/templates").then((r) => setTemplates(r.data)).catch(() => {});
  }, []);

  const loadMsgs = async () => {
    const { data } = await api.get(`/leads/${lead.id}/messages`);
    setMessages(data);
  };
  useEffect(() => { loadMsgs(); /* eslint-disable-next-line */ }, [lead.id]);

  const onTemplateChange = (id) => {
    setTemplateId(id);
    if (id === "custom") return;
    const t = templates.find((x) => x.id === id);
    if (t) setBody(t.body);
  };

  const send = async () => {
    if (!body.trim()) return;
    setSending(true);
    try {
      await api.post(`/leads/${lead.id}/messages`, {
        body, template: templateId === "custom" ? null : templateId,
      });
      setBody("");
      setTemplateId("custom");
      await loadMsgs();
      onActivity?.();
      toast.success("WhatsApp message sent (mock)");
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail) || "Failed to send");
    } finally { setSending(false); }
  };

  return (
    <div className="border border-zinc-200 rounded-lg bg-white flex flex-col h-[560px]" data-testid="whatsapp-panel">
      <div className="px-4 py-3 border-b border-zinc-200 flex items-center gap-2">
        <MessageCircle className="w-4 h-4 text-emerald-600" />
        <div className="font-display font-semibold text-sm">WhatsApp</div>
        <span className="text-xs text-zinc-500">{lead.phone}</span>
        <span className="ml-auto text-xs px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200">MOCK</span>
      </div>

      <div className="flex-1 overflow-auto p-4 space-y-2 bg-zinc-50" data-testid="whatsapp-stream">
        {messages.length === 0 && (
          <div className="text-center text-sm text-zinc-500 py-12">No messages yet. Send the first one below.</div>
        )}
        {messages.map((m) => (
          <div
            key={m.id}
            className={`max-w-[80%] rounded-lg px-3 py-2 text-sm ${m.direction === "outbound" ? "ml-auto bubble-out" : "bubble-in"}`}
            data-testid={`message-${m.id}`}
          >
            <div className="whitespace-pre-wrap">{m.body}</div>
            <div className="text-[10px] text-zinc-500 mt-1">
              {new Date(m.created_at).toLocaleString()} · {m.status}
            </div>
          </div>
        ))}
      </div>

      <div className="border-t border-zinc-200 p-3 space-y-2">
        <Select value={templateId} onValueChange={onTemplateChange}>
          <SelectTrigger data-testid="wa-template-select"><SelectValue placeholder="Choose template…" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="custom">Custom message</SelectItem>
            {templates.map((t) => (
              <SelectItem key={t.id} value={t.id}>{t.name} ({t.lang})</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Textarea
          rows={3} value={body} onChange={(e) => setBody(e.target.value)}
          placeholder="Type a message… use {name} and {course} as placeholders"
          data-testid="wa-body-input"
        />
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={refine} disabled={refining || !body.trim()} data-testid="wa-refine-btn">
            <Sparkles className="w-4 h-4 mr-1.5" />{refining ? "Polishing…" : "Refine with AI"}
          </Button>
          <Button onClick={send} disabled={sending || !body.trim()} className="bg-emerald-600 hover:bg-emerald-700" data-testid="wa-send-btn">
            <Send className="w-4 h-4 mr-1.5" />{sending ? "Sending…" : "Send"}
          </Button>
        </div>
      </div>
    </div>
  );
}
