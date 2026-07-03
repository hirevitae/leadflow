import { useEffect, useState } from "react";
import { api, formatApiError } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { MessageCircle, Facebook, Instagram, Mail, Sparkles, Eye, EyeOff, Copy, RefreshCw, Trash2, Plug, CheckCircle2, Loader2, Upload, Download, Phone, AudioLines, Bot } from "lucide-react";

const ICONS = { whatsapp: MessageCircle, facebook: Facebook, instagram: Instagram, email: Mail, ai: Sparkles, twilio: Phone, elevenlabs: AudioLines, openai: Bot };

const STATUS = {
  connected: { dot: "🟢", label: "Connected", cls: "bg-emerald-50 text-emerald-700 border-emerald-200" },
  needs_verification: { dot: "🟡", label: "Needs Verification", cls: "bg-amber-50 text-amber-700 border-amber-200" },
  invalid: { dot: "🔴", label: "Invalid Credentials", cls: "bg-rose-50 text-rose-700 border-rose-200" },
  not_configured: { dot: "⚪", label: "Not Configured", cls: "bg-zinc-100 text-zinc-500 border-zinc-200" },
};

const timeAgo = (iso) => {
  if (!iso) return "—";
  const s = Math.floor((Date.now() - new Date(iso)) / 1000);
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return new Date(iso).toLocaleDateString();
};

function IntegrationCard({ data, onChanged }) {
  const Icon = ICONS[data.provider] || Plug;
  const [form, setForm] = useState({});
  const [show, setShow] = useState({});
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);

  useEffect(() => { setForm({}); }, [data.updated_at]);

  const isConfigured = data.fields.filter((f) => data.label).length && data.status !== "not_configured";
  const st = STATUS[data.status] || STATUS.not_configured;

  const setVal = (k, v) => setForm((p) => ({ ...p, [k]: v }));

  const save = async () => {
    setSaving(true);
    try {
      await api.post("/admin/integrations", { provider: data.provider, values: form });
      toast.success(`${data.label} saved`);
      onChanged();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail) || "Save failed"); }
    finally { setSaving(false); }
  };

  const test = async () => {
    setTesting(true);
    try {
      const { data: res } = await api.post("/admin/integrations/test", { provider: data.provider });
      res.ok ? toast.success(`${data.label}: ${res.detail}`) : toast.error(`${data.label}: ${res.detail}`);
      onChanged();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail) || "Test failed"); }
    finally { setTesting(false); }
  };

  const rotate = async (key) => {
    try { await api.post("/admin/integrations/rotate-secret", { provider: data.provider, key }); toast.success("Secret cleared — enter a new value"); onChanged(); }
    catch (e) { toast.error("Rotate failed"); }
  };

  const reset = async () => {
    if (!confirm(`Reset all ${data.label} settings?`)) return;
    try { await api.delete(`/admin/integrations/${data.provider}`); toast.success(`${data.label} reset`); onChanged(); }
    catch (e) { toast.error("Reset failed"); }
  };

  const testLabel = data.provider === "email" ? "Send Test Email" : data.provider === "ai" ? "Test API" : "Test Connection";

  return (
    <Card data-testid={`integration-card-${data.provider}`}>
      <CardContent className="p-5 space-y-4">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-md bg-blue-50 text-blue-700 flex items-center justify-center"><Icon className="w-5 h-5" /></div>
            <div>
              <div className="font-display font-semibold">{data.label}</div>
              <div className="text-xs text-zinc-500">{data.description}</div>
            </div>
          </div>
          <Badge className={st.cls} data-testid={`status-${data.provider}`}>{st.dot} {st.label}</Badge>
        </div>

        <div className="space-y-3">
          {data.fields.map((f) => (
            <div key={f.key} className="space-y-1">
              <label className="text-xs font-medium text-zinc-600">{f.label}{!f.secret && f.options ? "" : f.secret ? " 🔒" : ""}</label>
              {f.options ? (
                <Select value={form[f.key] ?? f.value ?? ""} onValueChange={(v) => setVal(f.key, v)}>
                  <SelectTrigger data-testid={`field-${data.provider}-${f.key}`}><SelectValue placeholder="Select" /></SelectTrigger>
                  <SelectContent>{f.options.map((o) => <SelectItem key={o} value={o}>{o}</SelectItem>)}</SelectContent>
                </Select>
              ) : (
                <div className="flex items-center gap-1.5">
                  <Input
                    data-testid={`field-${data.provider}-${f.key}`}
                    type={f.secret && !show[f.key] ? "password" : "text"}
                    placeholder={f.secret && f.configured ? f.value : (f.value || `Enter ${f.label}`)}
                    value={form[f.key] ?? (f.secret ? "" : f.value)}
                    onChange={(e) => setVal(f.key, e.target.value)}
                  />
                  {f.secret && (
                    <>
                      <Button variant="outline" size="icon" className="shrink-0" onClick={() => setShow((s) => ({ ...s, [f.key]: !s[f.key] }))} data-testid={`toggle-${data.provider}-${f.key}`}>
                        {show[f.key] ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                      </Button>
                      {f.configured && (
                        <Button variant="outline" size="icon" className="shrink-0" title="Rotate / clear secret" onClick={() => rotate(f.key)} data-testid={`rotate-${data.provider}-${f.key}`}>
                          <RefreshCw className="w-4 h-4" />
                        </Button>
                      )}
                    </>
                  )}
                  {!f.secret && f.value && (
                    <Button variant="outline" size="icon" className="shrink-0" title="Copy" onClick={() => { navigator.clipboard.writeText(f.value); toast.success("Copied"); }}>
                      <Copy className="w-4 h-4" />
                    </Button>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>

        <div className="flex items-center justify-between pt-1">
          <div className="text-[11px] text-zinc-400 space-y-0.5">
            <div>Last verified: {timeAgo(data.last_verified_at)}{data.response_time_ms ? ` · ${data.response_time_ms}ms` : ""}</div>
            {data.updated_by && <div>Updated by: {data.updated_by}</div>}
            {data.last_error && <div className="text-rose-500 max-w-xs truncate" title={data.last_error}>Error: {data.last_error}</div>}
          </div>
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" className="text-rose-600" onClick={reset} data-testid={`reset-${data.provider}`}><Trash2 className="w-4 h-4" /></Button>
            <Button variant="outline" size="sm" onClick={test} disabled={testing || data.status === "not_configured"} data-testid={`test-${data.provider}`}>
              {testing ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <CheckCircle2 className="w-4 h-4 mr-1" />}{testLabel}
            </Button>
            <Button size="sm" className="bg-blue-600 hover:bg-blue-700" onClick={save} disabled={saving} data-testid={`save-${data.provider}`}>
              {saving ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : null}Save
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export default function IntegrationsManager() {
  const [items, setItems] = useState(null);

  const load = async () => {
    try { const { data } = await api.get("/admin/integrations"); setItems(data); }
    catch (e) { toast.error("Could not load integrations"); }
  };
  useEffect(() => { load(); }, []);

  const exportConfig = async () => {
    try {
      const { data } = await api.get("/admin/integrations/export");
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `integrations-config-${Date.now()}.json`; a.click();
      URL.revokeObjectURL(url);
      toast.success("Configuration exported");
    } catch (e) { toast.error("Export failed"); }
  };

  const importConfig = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const text = await file.text();
      const json = JSON.parse(text);
      const { data } = await api.post("/admin/integrations/import", json);
      toast.success(`Imported ${data.imported} setting(s)`);
      load();
    } catch (err) { toast.error("Import failed — invalid file"); }
    finally { e.target.value = ""; }
  };

  if (!items) return <div className="grid md:grid-cols-2 gap-4">{[0, 1, 2, 3].map((i) => <div key={i} className="h-64 rounded-lg bg-zinc-100 animate-pulse" />)}</div>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-end gap-2">
        <input type="file" accept="application/json" id="import-config-input" className="hidden" onChange={importConfig} data-testid="import-config-input" />
        <Button variant="outline" size="sm" onClick={() => document.getElementById("import-config-input").click()} data-testid="import-config-btn">
          <Upload className="w-4 h-4 mr-1" /> Import
        </Button>
        <Button variant="outline" size="sm" onClick={exportConfig} data-testid="export-config-btn">
          <Download className="w-4 h-4 mr-1" /> Export
        </Button>
      </div>
      <div className="grid md:grid-cols-2 gap-4" data-testid="integrations-manager">
        {items.map((it) => <IntegrationCard key={it.provider} data={it} onChanged={load} />)}
      </div>
    </div>
  );
}
