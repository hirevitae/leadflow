import { useState, useEffect } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api, formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Monitor, Smartphone, Moon, Upload, Download, Code, LayoutTemplate, History, RotateCcw } from "lucide-react";
import { GrapesEmailBuilder } from "@/components/GrapesEmailBuilder";

const MERGE = ["{{name}}", "{{course}}", "{{email}}", "{{phone}}", "{{unsubscribe}}"];

export const EmailTemplateDialog = ({ open, onOpenChange, template, categories, onSaved }) => {
  const [form, setForm] = useState({ name: "", category: "Newsletter", subject: "", html: "" });
  const [device, setDevice] = useState("desktop");
  const [dark, setDark] = useState(false);
  const [saving, setSaving] = useState(false);
  const [tab, setTab] = useState("code");
  const [versions, setVersions] = useState([]);

  useEffect(() => {
    if (open) {
      setForm(template
        ? { name: template.name, category: template.category, subject: template.subject, html: template.html }
        : { name: "", category: "Newsletter", subject: "", html: "<h1>Hi {{name}}</h1>\n<p>Write your message here…</p>" });
      setDevice("desktop"); setDark(false); setTab("code"); setVersions([]);
    }
  }, [open, template]);

  const loadVersions = () => template && api.get(`/email/templates/${template.id}/versions`).then(({ data }) => setVersions(data)).catch(() => {});
  const restore = async (vid) => {
    try { const { data } = await api.post(`/email/templates/${template.id}/versions/${vid}/restore`); setForm({ name: data.name, category: data.category, subject: data.subject, html: data.html }); toast.success("Version restored"); loadVersions(); }
    catch { toast.error("Restore failed"); }
  };

  const insert = (token) => setForm((f) => ({ ...f, html: f.html + " " + token }));
  const importHtml = (e) => {
    const file = e.target.files?.[0]; if (!file) return;
    const reader = new FileReader();
    reader.onload = () => setForm((f) => ({ ...f, html: reader.result }));
    reader.readAsText(file); e.target.value = "";
  };
  const exportHtml = () => {
    const blob = new Blob([form.html], { type: "text/html" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
    a.download = `${form.name || "template"}.html`; a.click();
  };

  const save = async () => {
    if (!form.name.trim()) { toast.error("Name is required"); return; }
    setSaving(true);
    try {
      if (template) await api.put(`/email/templates/${template.id}`, form);
      else await api.post("/email/templates", form);
      toast.success("Template saved"); onSaved?.(); onOpenChange(false);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail) || "Save failed"); }
    finally { setSaving(false); }
  };

  const previewDoc = `<html><body style="margin:0;background:${dark ? "#0b0b0f" : "#f4f4f5"};padding:16px;color:${dark ? "#e5e5e5" : "#111"}"><div style="max-width:600px;margin:0 auto;background:${dark ? "#18181b" : "#fff"};padding:24px;border-radius:8px">${form.html}</div></body></html>`;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-5xl max-h-[92vh] overflow-hidden flex flex-col" data-testid="template-dialog">
        <DialogHeader><DialogTitle>{template ? "Edit template" : "New email template"}</DialogTitle></DialogHeader>
        <div className="grid grid-cols-3 gap-2">
          <Input placeholder="Template name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="template-name" />
          <Select value={form.category} onValueChange={(v) => setForm({ ...form, category: v })}>
            <SelectTrigger data-testid="template-category"><SelectValue /></SelectTrigger>
            <SelectContent>{categories.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
          </Select>
          <Input placeholder="Subject ({{name}})" value={form.subject} onChange={(e) => setForm({ ...form, subject: e.target.value })} data-testid="template-subject" />
        </div>

        <Tabs value={tab} onValueChange={(v) => { setTab(v); if (v === "history") loadVersions(); }} className="flex-1 overflow-hidden flex flex-col mt-2">
          <TabsList>
            <TabsTrigger value="code" data-testid="tab-code"><Code className="w-4 h-4 mr-1" /> Code</TabsTrigger>
            <TabsTrigger value="visual" data-testid="tab-visual"><LayoutTemplate className="w-4 h-4 mr-1" /> Visual</TabsTrigger>
            {template && <TabsTrigger value="history" data-testid="tab-history"><History className="w-4 h-4 mr-1" /> History</TabsTrigger>}
          </TabsList>

          <TabsContent value="code" className="overflow-y-auto flex-1 mt-2">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <div className="flex flex-wrap gap-1.5">
                  {MERGE.map((m) => <button key={m} onClick={() => insert(m)} className="text-xs px-2 py-1 rounded bg-blue-50 text-blue-700 hover:bg-blue-100" data-testid={`merge-${m}`}>{m}</button>)}
                </div>
                <Textarea rows={15} className="font-mono text-xs" placeholder="HTML content" value={form.html} onChange={(e) => setForm({ ...form, html: e.target.value })} data-testid="template-html" />
                <div className="flex gap-2">
                  <label className="inline-flex"><input type="file" accept=".html,.htm" className="hidden" onChange={importHtml} data-testid="import-html" /><Button variant="outline" size="sm" asChild><span><Upload className="w-3.5 h-3.5 mr-1" /> Import</span></Button></label>
                  <Button variant="outline" size="sm" onClick={exportHtml} data-testid="export-html"><Download className="w-3.5 h-3.5 mr-1" /> Export</Button>
                </div>
              </div>
              <div className="space-y-2">
                <div className="flex items-center gap-1.5">
                  <Button variant={device === "desktop" ? "default" : "outline"} size="sm" onClick={() => setDevice("desktop")} data-testid="preview-desktop"><Monitor className="w-3.5 h-3.5" /></Button>
                  <Button variant={device === "mobile" ? "default" : "outline"} size="sm" onClick={() => setDevice("mobile")} data-testid="preview-mobile"><Smartphone className="w-3.5 h-3.5" /></Button>
                  <Button variant={dark ? "default" : "outline"} size="sm" onClick={() => setDark(!dark)} data-testid="preview-dark"><Moon className="w-3.5 h-3.5" /></Button>
                  <span className="text-xs text-zinc-400 ml-1">Preview</span>
                </div>
                <div className="border border-zinc-200 rounded-md overflow-hidden bg-zinc-50 flex justify-center h-[420px]">
                  <iframe title="preview" srcDoc={previewDoc} data-testid="template-preview" className="h-full bg-white" style={{ width: device === "mobile" ? 375 : "100%" }} />
                </div>
              </div>
            </div>
          </TabsContent>

          <TabsContent value="visual" className="overflow-y-auto flex-1 mt-2">
            {tab === "visual" && <GrapesEmailBuilder value={form.html} onChange={(html) => setForm((f) => ({ ...f, html }))} />}
            <p className="text-xs text-zinc-400 mt-1">Drag blocks to design. Merge fields like {"{{name}}"} still work — type them into text blocks.</p>
          </TabsContent>

          <TabsContent value="history" className="overflow-y-auto flex-1 mt-2">
            {versions.length === 0 ? <div className="text-sm text-zinc-400 p-4" data-testid="versions-empty">No previous versions. Each content edit is snapshotted here.</div> : (
              <ul className="divide-y divide-zinc-100" data-testid="versions-list">
                {versions.map((v) => (
                  <li key={v.id} className="py-2.5 flex items-center gap-3" data-testid={`version-${v.version_no}`}>
                    <span className="text-xs font-semibold text-zinc-500 w-8">v{v.version_no}</span>
                    <div className="flex-1 min-w-0"><div className="text-sm truncate">{v.subject}</div><div className="text-xs text-zinc-400">{new Date(v.created_at).toLocaleString()} · {v.created_by}</div></div>
                    <Button variant="outline" size="sm" onClick={() => restore(v.id)} data-testid={`restore-${v.version_no}`}><RotateCcw className="w-3.5 h-3.5 mr-1" /> Restore</Button>
                  </li>
                ))}
              </ul>
            )}
          </TabsContent>
        </Tabs>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={save} disabled={saving} className="bg-blue-600 hover:bg-blue-700" data-testid="save-template-btn">{saving ? "Saving…" : "Save template"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
