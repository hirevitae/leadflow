import { useState, useEffect } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api, formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Monitor, Smartphone, Moon, Upload, Download } from "lucide-react";

const MERGE = ["{{name}}", "{{course}}", "{{email}}", "{{phone}}", "{{unsubscribe}}"];

export const EmailTemplateDialog = ({ open, onOpenChange, template, categories, onSaved }) => {
  const [form, setForm] = useState({ name: "", category: "Newsletter", subject: "", html: "" });
  const [device, setDevice] = useState("desktop");
  const [dark, setDark] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) {
      setForm(template
        ? { name: template.name, category: template.category, subject: template.subject, html: template.html }
        : { name: "", category: "Newsletter", subject: "", html: "<h1>Hi {{name}}</h1>\n<p>Write your message here…</p>" });
      setDevice("desktop"); setDark(false);
    }
  }, [open, template]);

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
      <DialogContent className="max-w-5xl max-h-[90vh] overflow-hidden flex flex-col" data-testid="template-dialog">
        <DialogHeader><DialogTitle>{template ? "Edit template" : "New email template"}</DialogTitle></DialogHeader>
        <div className="grid grid-cols-2 gap-5 overflow-y-auto flex-1 pr-1">
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-2">
              <Input placeholder="Template name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="template-name" />
              <Select value={form.category} onValueChange={(v) => setForm({ ...form, category: v })}>
                <SelectTrigger data-testid="template-category"><SelectValue /></SelectTrigger>
                <SelectContent>{categories.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <Input placeholder="Subject line (use {{name}})" value={form.subject} onChange={(e) => setForm({ ...form, subject: e.target.value })} data-testid="template-subject" />
            <div className="flex flex-wrap gap-1.5">
              {MERGE.map((m) => <button key={m} onClick={() => insert(m)} className="text-xs px-2 py-1 rounded bg-blue-50 text-blue-700 hover:bg-blue-100" data-testid={`merge-${m}`}>{m}</button>)}
            </div>
            <Textarea rows={14} className="font-mono text-xs" placeholder="HTML content" value={form.html} onChange={(e) => setForm({ ...form, html: e.target.value })} data-testid="template-html" />
            <div className="flex gap-2">
              <label className="inline-flex"><input type="file" accept=".html,.htm" className="hidden" onChange={importHtml} data-testid="import-html" /><Button variant="outline" size="sm" asChild><span><Upload className="w-3.5 h-3.5 mr-1" /> Import HTML</span></Button></label>
              <Button variant="outline" size="sm" onClick={exportHtml} data-testid="export-html"><Download className="w-3.5 h-3.5 mr-1" /> Export</Button>
            </div>
          </div>
          <div className="space-y-2">
            <div className="flex items-center gap-1.5">
              <Button variant={device === "desktop" ? "default" : "outline"} size="sm" onClick={() => setDevice("desktop")} data-testid="preview-desktop"><Monitor className="w-3.5 h-3.5" /></Button>
              <Button variant={device === "mobile" ? "default" : "outline"} size="sm" onClick={() => setDevice("mobile")} data-testid="preview-mobile"><Smartphone className="w-3.5 h-3.5" /></Button>
              <Button variant={dark ? "default" : "outline"} size="sm" onClick={() => setDark(!dark)} data-testid="preview-dark"><Moon className="w-3.5 h-3.5" /></Button>
              <span className="text-xs text-zinc-400 ml-1">Live preview</span>
            </div>
            <div className="border border-zinc-200 rounded-md overflow-hidden bg-zinc-50 flex justify-center h-[420px]">
              <iframe title="preview" srcDoc={previewDoc} data-testid="template-preview" className="h-full bg-white transition-all" style={{ width: device === "mobile" ? 375 : "100%" }} />
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={save} disabled={saving} className="bg-blue-600 hover:bg-blue-700" data-testid="save-template-btn">{saving ? "Saving…" : "Save template"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
