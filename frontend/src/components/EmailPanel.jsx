import { useEffect, useState } from "react";
import { api, formatApiError } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import { Mail, Send } from "lucide-react";

export default function EmailPanel({ lead, onActivity }) {
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [sending, setSending] = useState(false);
  const [emails, setEmails] = useState([]);

  const load = async () => {
    try { const { data } = await api.get(`/leads/${lead.id}/emails`); setEmails(data); } catch { /* ignore */ }
  };
  useEffect(() => { load(); }, [lead.id]);

  const send = async () => {
    if (!subject.trim() || !body.trim()) { toast.error("Subject and body required"); return; }
    setSending(true);
    try {
      await api.post(`/leads/${lead.id}/email`, { subject, body });
      toast.success("Email sent");
      setSubject(""); setBody("");
      load(); onActivity?.();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail) || "Email failed");
    } finally { setSending(false); }
  };

  return (
    <Card data-testid="email-panel">
      <CardContent className="p-5 space-y-3">
        <div className="flex items-center gap-2 font-medium"><Mail className="w-4 h-4 text-blue-600" /> Email {lead.email ? <span className="text-sm text-zinc-500 font-normal">→ {lead.email}</span> : <span className="text-xs text-rose-500 font-normal">(no email on file)</span>}</div>
        <Input placeholder="Subject" value={subject} onChange={(e) => setSubject(e.target.value)} data-testid="email-subject-input" />
        <Textarea rows={4} placeholder="Write your message… use {name} for personalization" value={body} onChange={(e) => setBody(e.target.value)} data-testid="email-body-input" />
        <div className="flex justify-end">
          <Button onClick={send} disabled={sending || !lead.email} className="bg-blue-600 hover:bg-blue-700" data-testid="send-email-btn">
            <Send className="w-4 h-4 mr-1.5" /> {sending ? "Sending…" : "Send email"}
          </Button>
        </div>
        {emails.length > 0 && (
          <div className="pt-3 border-t border-zinc-200 space-y-2" data-testid="email-history">
            {emails.map((e) => (
              <div key={e.id} className="p-2.5 rounded-md bg-zinc-50 border border-zinc-200">
                <div className="text-sm font-medium">{e.subject}</div>
                <div className="text-xs text-zinc-500 mt-0.5">{new Date(e.created_at).toLocaleString()} · sent</div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
