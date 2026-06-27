import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { api, formatApiError, STAGES } from "@/lib/api";
import { toast } from "sonner";
import { Megaphone, MessageCircle, PhoneCall } from "lucide-react";

export default function BulkOutreachDialog({ onDone }) {
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState("whatsapp");
  const [stage, setStage] = useState("new");
  const [templateId, setTemplateId] = useState("");
  const [language, setLanguage] = useState("english");
  const [templates, setTemplates] = useState([]);
  const [counts, setCounts] = useState({});
  const [sending, setSending] = useState(false);
  const [waMode, setWaMode] = useState("quick");
  const [metaTemplates, setMetaTemplates] = useState([]);
  const [metaErr, setMetaErr] = useState("");
  const [metaName, setMetaName] = useState("");
  const [metaParams, setMetaParams] = useState([]);

  const loadMetaTemplates = async () => {
    setMetaErr("");
    try { const { data } = await api.get("/whatsapp/meta-templates"); setMetaTemplates(data); }
    catch (e) { setMetaTemplates([]); setMetaErr(formatApiError(e.response?.data?.detail) || "Could not load Meta templates"); }
  };

  const onMetaSelect = (name) => {
    setMetaName(name);
    const t = metaTemplates.find((x) => x.name === name);
    setMetaParams(new Array(t?.param_count || 0).fill("").map((_, i) => i === 0 ? "{name}" : ""));
  };

  const loadMeta = async () => {
    try {
      const [tpl, leadsRes] = await Promise.all([
        api.get("/whatsapp/templates"),
        api.get("/leads"),
      ]);
      setTemplates(tpl.data);
      if (!templateId && tpl.data.length) setTemplateId(tpl.data[0].id);
      const c = {};
      STAGES.forEach((s) => (c[s.key] = leadsRes.data.filter((l) => l.stage === s.key).length));
      setCounts(c);
    } catch (e) {
      toast.error("Could not load outreach data");
    }
  };

  useEffect(() => {
    if (open) loadMeta();
    // eslint-disable-next-line
  }, [open]);

  const target = counts[stage] ?? 0;

  const submit = async () => {
    if (target === 0) { toast.error("No leads in this stage"); return; }
    setSending(true);
    try {
      if (mode === "whatsapp") {
        if (waMode === "meta") {
          if (!metaName) { toast.error("Pick an approved template"); setSending(false); return; }
          const t = metaTemplates.find((x) => x.name === metaName);
          const res = await api.post("/bulk/whatsapp-template", {
            stage, template_name: metaName, language: t?.language || "en", params: metaParams,
          });
          toast.success(`Template sent to ${res.data.sent} lead${res.data.sent === 1 ? "" : "s"}${res.data.failed ? `, ${res.data.failed} failed` : ""}`);
        } else {
          const res = await api.post("/bulk/whatsapp", { stage, template_id: templateId });
          toast.success(`Sent WhatsApp to ${res.data.sent} lead${res.data.sent === 1 ? "" : "s"}`);
        }
      } else {
        const res = await api.post("/bulk/calls", { stage, language });
        toast.success(`Placed AI calls to ${res.data.called} lead${res.data.called === 1 ? "" : "s"}`);
      }
      onDone?.();
      setOpen(false);
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail) || "Bulk outreach failed");
    } finally {
      setSending(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" data-testid="open-bulk-outreach-btn">
          <Megaphone className="w-4 h-4 mr-1.5" /> Bulk outreach
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-[520px]" data-testid="bulk-outreach-dialog">
        <DialogHeader>
          <DialogTitle className="font-display">Bulk outreach</DialogTitle>
        </DialogHeader>

        <Tabs value={mode} onValueChange={setMode} className="w-full">
          <TabsList className="grid grid-cols-2 w-full">
            <TabsTrigger value="whatsapp" data-testid="bulk-tab-whatsapp">
              <MessageCircle className="w-4 h-4 mr-1.5" /> WhatsApp
            </TabsTrigger>
            <TabsTrigger value="call" data-testid="bulk-tab-call">
              <PhoneCall className="w-4 h-4 mr-1.5" /> AI Call
            </TabsTrigger>
          </TabsList>

          <div className="space-y-4 pt-4">
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-zinc-700">Lead stage group</label>
              <Select value={stage} onValueChange={setStage}>
                <SelectTrigger data-testid="bulk-stage-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {STAGES.map((s) => (
                    <SelectItem key={s.key} value={s.key}>{s.label} ({counts[s.key] ?? 0})</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <TabsContent value="whatsapp" className="m-0 space-y-2">
              <div className="flex gap-1">
                <Button type="button" variant={waMode === "quick" ? "default" : "outline"} size="sm" className={waMode === "quick" ? "bg-blue-600 hover:bg-blue-700" : ""} onClick={() => setWaMode("quick")} data-testid="bulk-wamode-quick">Quick template</Button>
                <Button type="button" variant={waMode === "meta" ? "default" : "outline"} size="sm" className={waMode === "meta" ? "bg-blue-600 hover:bg-blue-700" : ""} onClick={() => { setWaMode("meta"); if (metaTemplates.length === 0) loadMetaTemplates(); }} data-testid="bulk-wamode-meta">Approved template</Button>
              </div>
              {waMode === "quick" ? (
                <>
                  <label className="text-sm font-medium text-zinc-700">Message template</label>
                  <Select value={templateId} onValueChange={setTemplateId}>
                    <SelectTrigger data-testid="bulk-template-select"><SelectValue placeholder="Choose template" /></SelectTrigger>
                    <SelectContent>
                      {templates.map((t) => (
                        <SelectItem key={t.id} value={t.id}>{t.name} · {t.lang}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </>
              ) : metaErr ? (
                <div className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded p-2">{metaErr} — add real Meta credentials in Settings → Integrations.</div>
              ) : (
                <>
                  <label className="text-sm font-medium text-zinc-700">Approved Meta template</label>
                  <Select value={metaName} onValueChange={onMetaSelect}>
                    <SelectTrigger data-testid="bulk-meta-template-select"><SelectValue placeholder="Choose approved template" /></SelectTrigger>
                    <SelectContent>
                      {metaTemplates.map((t) => <SelectItem key={t.name} value={t.name}>{t.name} · {t.language}</SelectItem>)}
                    </SelectContent>
                  </Select>
                  {metaParams.map((p, i) => (
                    <input key={i} className="w-full text-sm border border-zinc-200 rounded px-2 py-1.5"
                      placeholder={`Parameter {{${i + 1}}} — supports {name}, {course}`} value={p}
                      onChange={(e) => setMetaParams((prev) => prev.map((x, idx) => idx === i ? e.target.value : x))}
                      data-testid={`bulk-meta-param-${i}`} />
                  ))}
                </>
              )}
            </TabsContent>

            <TabsContent value="call" className="m-0 space-y-1.5">
              <label className="text-sm font-medium text-zinc-700">Call language</label>
              <Select value={language} onValueChange={setLanguage}>
                <SelectTrigger data-testid="bulk-language-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="english">English</SelectItem>
                  <SelectItem value="hindi">Hindi</SelectItem>
                </SelectContent>
              </Select>
            </TabsContent>

            <div className="rounded-md bg-blue-50 border border-blue-100 p-3 text-sm text-blue-800" data-testid="bulk-count-preview">
              {target > 0
                ? <>This will {mode === "whatsapp" ? "message" : "call"} <span className="font-semibold">{target}</span> lead{target === 1 ? "" : "s"} in the “{STAGES.find((s) => s.key === stage)?.label}” stage.</>
                : <>No leads in this stage group.</>}
            </div>
          </div>
        </Tabs>

        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)} data-testid="cancel-bulk-outreach-btn">Cancel</Button>
          <Button
            onClick={submit}
            disabled={sending || target === 0 || (mode === "whatsapp" && waMode === "quick" && !templateId) || (mode === "whatsapp" && waMode === "meta" && !metaName)}
            className="bg-blue-600 hover:bg-blue-700"
            data-testid="submit-bulk-outreach-btn"
          >
            {sending ? "Sending…" : mode === "whatsapp" ? `Send to ${target}` : `Call ${target}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
