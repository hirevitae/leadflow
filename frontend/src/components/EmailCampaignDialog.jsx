import { useState, useEffect } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api, formatApiError, STAGES } from "@/lib/api";
import { toast } from "sonner";

const TIMEZONES = ["Asia/Kolkata", "Asia/Dubai", "Europe/London", "America/New_York", "America/Los_Angeles", "UTC"];

export const EmailCampaignDialog = ({ open, onOpenChange, templates, onCreated }) => {
  const [name, setName] = useState("");
  const [templateId, setTemplateId] = useState("");
  const [subject, setSubject] = useState("");
  const [html, setHtml] = useState("");
  const [stages, setStages] = useState([]);
  const [mode, setMode] = useState("now");
  const [sendAt, setSendAt] = useState("");
  const [tz, setTz] = useState("Asia/Kolkata");
  const [perMinute, setPerMinute] = useState(30);
  const [bizHours, setBizHours] = useState(false);
  const [audience, setAudience] = useState(null);
  const [sending, setSending] = useState(false);

  useEffect(() => {
    if (open) { setName(""); setTemplateId(""); setSubject(""); setHtml(""); setStages([]); setMode("now"); setSendAt(""); setPerMinute(30); setBizHours(false); setAudience(null); }
  }, [open]);

  useEffect(() => {
    if (stages.length === 0) { setAudience(null); return; }
    api.post("/email/audience/preview", { stages }).then(({ data }) => setAudience(data)).catch(() => {});
  }, [stages]);

  const pickTemplate = (id) => {
    setTemplateId(id);
    const t = templates.find((x) => x.id === id);
    if (t) { setSubject(t.subject); setHtml(t.html); if (!name) setName(t.name + " campaign"); }
  };
  const toggleStage = (k) => setStages((s) => s.includes(k) ? s.filter((x) => x !== k) : [...s, k]);

  const submit = async () => {
    if (!name.trim()) { toast.error("Campaign name required"); return; }
    if (!subject.trim() || !html.trim()) { toast.error("Pick a template or set subject & content"); return; }
    if (stages.length === 0) { toast.error("Select at least one audience stage"); return; }
    if (mode === "later" && !sendAt) { toast.error("Pick a send date/time"); return; }
    setSending(true);
    try {
      const body = {
        name, template_id: templateId || null, subject, html, stages,
        schedule: { mode, send_at: mode === "later" ? new Date(sendAt).toISOString() : null, timezone: tz },
        throttle: { per_minute: Number(perMinute), business_hours_only: bizHours },
      };
      const { data } = await api.post("/email/campaigns", body);
      toast.success(mode === "later" ? "Campaign scheduled" : "Campaign started sending");
      onCreated?.(data); onOpenChange(false);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail) || "Could not create campaign"); }
    finally { setSending(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto" data-testid="campaign-dialog">
        <DialogHeader><DialogTitle>New email campaign</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <Input placeholder="Campaign name" value={name} onChange={(e) => setName(e.target.value)} data-testid="campaign-name" />
          <div>
            <label className="text-xs font-medium text-zinc-600">Template</label>
            <Select value={templateId} onValueChange={pickTemplate}>
              <SelectTrigger data-testid="campaign-template"><SelectValue placeholder="Choose a template" /></SelectTrigger>
              <SelectContent>{templates.map((t) => <SelectItem key={t.id} value={t.id}>{t.name} · {t.category}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <Input placeholder="Subject" value={subject} onChange={(e) => setSubject(e.target.value)} data-testid="campaign-subject" />
          <div>
            <label className="text-xs font-medium text-zinc-600">Audience (pipeline stages)</label>
            <div className="grid grid-cols-2 gap-1.5 mt-1">
              {STAGES.map((s) => (
                <label key={s.key} className="flex items-center gap-2 text-sm cursor-pointer" data-testid={`stage-${s.key}`}>
                  <Checkbox checked={stages.includes(s.key)} onCheckedChange={() => toggleStage(s.key)} />
                  {s.label}
                </label>
              ))}
            </div>
          </div>
          {audience && (
            <div className="rounded-md bg-blue-50 border border-blue-100 p-2.5 text-sm text-blue-800" data-testid="audience-preview">
              <span className="font-semibold">{audience.deliverable}</span> deliverable · {audience.with_email} with email · {audience.suppressed_or_dupe} suppressed/dupe
            </div>
          )}
          <div>
            <label className="text-xs font-medium text-zinc-600">Send</label>
            <div className="flex gap-2 mt-1">
              <Button variant={mode === "now" ? "default" : "outline"} size="sm" onClick={() => setMode("now")} data-testid="send-now">Immediately</Button>
              <Button variant={mode === "later" ? "default" : "outline"} size="sm" onClick={() => setMode("later")} data-testid="send-later">Schedule later</Button>
            </div>
          </div>
          {mode === "later" && (
            <div className="grid grid-cols-2 gap-2">
              <Input type="datetime-local" value={sendAt} onChange={(e) => setSendAt(e.target.value)} data-testid="send-at" />
              <Select value={tz} onValueChange={setTz}><SelectTrigger data-testid="timezone"><SelectValue /></SelectTrigger><SelectContent>{TIMEZONES.map((z) => <SelectItem key={z} value={z}>{z}</SelectItem>)}</SelectContent></Select>
            </div>
          )}
          <div className="grid grid-cols-2 gap-2 items-end">
            <div>
              <label className="text-xs font-medium text-zinc-600">Throttle (emails/min)</label>
              <Input type="number" min={1} value={perMinute} onChange={(e) => setPerMinute(e.target.value)} data-testid="throttle-per-minute" />
            </div>
            <label className="flex items-center gap-2 text-sm pb-2"><Switch checked={bizHours} onCheckedChange={setBizHours} data-testid="business-hours" /> Business hours only</label>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={submit} disabled={sending} className="bg-blue-600 hover:bg-blue-700" data-testid="create-campaign-btn">
            {sending ? "Creating…" : mode === "later" ? "Schedule campaign" : `Send to ${audience?.deliverable || 0}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
