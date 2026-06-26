import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import { Inbox as InboxIcon, Check, X, MessageCircle, Instagram, Facebook } from "lucide-react";

const channelIcon = (c) => c?.includes("whatsapp") ? <MessageCircle className="w-4 h-4 text-emerald-600" />
  : c?.includes("instagram") ? <Instagram className="w-4 h-4 text-pink-600" />
  : <Facebook className="w-4 h-4 text-blue-600" />;

export default function Inbox() {
  const [drafts, setDrafts] = useState([]);
  const [status, setStatus] = useState(null);
  const [edits, setEdits] = useState({});

  const load = async () => {
    const [d, s] = await Promise.all([api.get("/meta/drafts"), api.get("/meta/status")]);
    setDrafts(d.data); setStatus(s.data);
  };
  useEffect(() => { load(); const t = setInterval(load, 8000); return () => clearInterval(t); }, []);

  const approve = async (id) => {
    try {
      await api.post(`/meta/drafts/${id}/approve`, { body: edits[id] });
      toast.success("Reply sent");
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Send failed"); }
  };
  const reject = async (id) => { await api.post(`/meta/drafts/${id}/reject`); load(); };

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <h1 className="font-display font-bold text-3xl tracking-tight">Inbox</h1>
      <p className="text-sm text-zinc-500 mt-1">AI-drafted replies to incoming WhatsApp / Instagram / Facebook messages awaiting your approval.</p>

      {status && (
        <Card className="mt-4 mb-6"><CardContent className="p-4 text-sm flex flex-wrap gap-4">
          <span data-testid="status-whatsapp">WhatsApp: <b className={status.whatsapp ? "text-emerald-600" : "text-rose-600"}>{status.whatsapp ? "Live" : "Not configured"}</b></span>
          <span>Facebook: <b className={status.facebook ? "text-emerald-600" : "text-rose-600"}>{status.facebook ? "Live" : "Off"}</b></span>
          <span>Instagram: <b className={status.instagram ? "text-emerald-600" : "text-rose-600"}>{status.instagram ? "Live" : "Off"}</b></span>
          <span>AI: <b className={status.ai ? "text-emerald-600" : "text-rose-600"}>{status.ai ? "Ready" : "Key missing"}</b></span>
          <span>Mode: <b>{status.mode}</b></span>
          <span className="text-zinc-500">Webhook: <span className="mono">{status.webhook_url}</span></span>
        </CardContent></Card>
      )}

      {drafts.length === 0 ? (
        <Card><CardContent className="p-12 text-center text-zinc-500">
          <InboxIcon className="w-10 h-10 mx-auto mb-2 text-zinc-300" />
          No pending drafts. Once a student messages you on WhatsApp / IG / FB, AI drafts appear here for approval.
        </CardContent></Card>
      ) : drafts.map((d) => (
        <Card key={d.id} className="mb-3" data-testid={`draft-${d.id}`}>
          <CardContent className="p-5">
            <div className="flex items-center gap-2 mb-2">
              {channelIcon(d.channel)}
              <div className="font-medium">{d.lead?.name || "Unknown"}</div>
              <span className="text-xs text-zinc-500">· {d.channel}</span>
              {d.is_faq && <span className="ml-auto text-xs px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200">FAQ: {d.category}</span>}
            </div>
            <div className="text-sm text-zinc-600 bg-zinc-50 rounded p-3 mb-2">
              <span className="text-xs uppercase tracking-wide text-zinc-500">Student said</span>
              <div>{d.incoming_body}</div>
            </div>
            <Textarea rows={3} className="mb-3"
              defaultValue={d.draft_reply}
              onChange={(e) => setEdits((p) => ({ ...p, [d.id]: e.target.value }))}
              data-testid={`draft-body-${d.id}`} />
            <div className="flex gap-2">
              <Button className="bg-blue-600 hover:bg-blue-700" onClick={() => approve(d.id)} data-testid={`approve-${d.id}`}>
                <Check className="w-4 h-4 mr-1.5" /> Approve & Send
              </Button>
              <Button variant="outline" onClick={() => reject(d.id)} data-testid={`reject-${d.id}`}>
                <X className="w-4 h-4 mr-1.5" /> Reject
              </Button>
              <span className="ml-auto text-xs text-zinc-500 self-center">Confidence: {Math.round((d.confidence || 0) * 100)}%</span>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
