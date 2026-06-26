import { useEffect, useState } from "react";
import { api, formatApiError } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import { CheckCircle2, XCircle, Plug, Newspaper, MessageSquare, Users, Plus, Trash2 } from "lucide-react";

const INTEGRATION_LABELS = {
  whatsapp: { label: "WhatsApp Cloud API", keys: "WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_ACCESS_TOKEN" },
  meta_verify: { label: "Meta Webhook Verify", keys: "META_VERIFY_TOKEN" },
  facebook: { label: "Facebook Page", keys: "FB_PAGE_ID, FB_PAGE_ACCESS_TOKEN" },
  instagram: { label: "Instagram", keys: "IG_BUSINESS_ACCOUNT_ID, FB_PAGE_ACCESS_TOKEN" },
  email: { label: "Email (Resend)", keys: "RESEND_API_KEY, SENDER_EMAIL" },
  llm: { label: "AI (Emergent LLM)", keys: "EMERGENT_LLM_KEY" },
};

export default function Settings() {
  const [status, setStatus] = useState({});
  const [content, setContent] = useState(null);
  const [tpls, setTpls] = useState({ whatsapp_templates: [], call_scripts: {} });
  const [team, setTeam] = useState({ round_robin: false });
  const [kw, setKw] = useState("");

  const loadAll = async () => {
    try {
      const [s, c, t, tm] = await Promise.all([
        api.get("/integrations/status"),
        api.get("/config/content"),
        api.get("/config/templates"),
        api.get("/config/team"),
      ]);
      setStatus(s.data);
      setContent(c.data);
      setTpls({ whatsapp_templates: t.data.whatsapp_templates || [], call_scripts: t.data.call_scripts || {} });
      setTeam(tm.data);
    } catch (e) {
      toast.error("Could not load settings");
    }
  };
  useEffect(() => { loadAll(); }, []);

  const saveContent = async () => {
    try {
      const { data } = await api.put("/config/content", content);
      setContent(data);
      toast.success("Auto-search settings saved");
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail) || "Save failed"); }
  };

  const saveTemplates = async () => {
    try {
      await api.put("/config/templates", tpls);
      toast.success("Templates & scripts saved");
      loadAll();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail) || "Save failed"); }
  };

  const saveTeam = async (val) => {
    try {
      const { data } = await api.put("/config/team", { round_robin: val });
      setTeam(data);
      toast.success(`Round-robin ${val ? "enabled" : "disabled"}`);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail) || "Save failed"); }
  };

  if (!content) return <div className="p-8 text-zinc-500">Loading…</div>;

  return (
    <div className="p-8 max-w-5xl mx-auto" data-testid="settings-page">
      <div className="mb-6">
        <h1 className="font-display font-bold text-3xl tracking-tight">Settings</h1>
        <p className="text-sm text-zinc-500 mt-1">Configure integrations, auto-search, templates and team — all live, no code changes.</p>
      </div>

      <Tabs defaultValue="integrations">
        <TabsList>
          <TabsTrigger value="integrations" data-testid="settings-tab-integrations"><Plug className="w-4 h-4 mr-1.5" /> Integrations</TabsTrigger>
          <TabsTrigger value="content" data-testid="settings-tab-content"><Newspaper className="w-4 h-4 mr-1.5" /> Auto-search</TabsTrigger>
          <TabsTrigger value="templates" data-testid="settings-tab-templates"><MessageSquare className="w-4 h-4 mr-1.5" /> Templates</TabsTrigger>
          <TabsTrigger value="team" data-testid="settings-tab-team"><Users className="w-4 h-4 mr-1.5" /> Team</TabsTrigger>
        </TabsList>

        {/* INTEGRATIONS */}
        <TabsContent value="integrations" className="mt-4">
          <Card>
            <CardHeader><CardTitle className="font-display text-lg">API integrations</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm text-zinc-500">Keys are stored securely in the backend environment. Add or update them in <span className="mono">backend/.env</span>; this panel shows live connection status.</p>
              {Object.entries(INTEGRATION_LABELS).map(([key, meta]) => (
                <div key={key} className="flex items-center justify-between p-3 rounded-md border border-zinc-200" data-testid={`integration-${key}`}>
                  <div>
                    <div className="font-medium text-sm">{meta.label}</div>
                    <div className="text-xs text-zinc-400 mono mt-0.5">{meta.keys}</div>
                  </div>
                  {status[key] ? (
                    <Badge className="bg-emerald-50 text-emerald-700 border-emerald-200"><CheckCircle2 className="w-3.5 h-3.5 mr-1" /> Configured</Badge>
                  ) : (
                    <Badge className="bg-zinc-100 text-zinc-500 border-zinc-200"><XCircle className="w-3.5 h-3.5 mr-1" /> Not configured</Badge>
                  )}
                </div>
              ))}
            </CardContent>
          </Card>
        </TabsContent>

        {/* CONTENT / AUTO-SEARCH */}
        <TabsContent value="content" className="mt-4">
          <Card>
            <CardHeader><CardTitle className="font-display text-lg">Auto-search & content schedule</CardTitle></CardHeader>
            <CardContent className="space-y-5">
              <div className="flex items-center justify-between p-3 rounded-md bg-zinc-50 border border-zinc-200">
                <div>
                  <div className="font-medium text-sm">Hourly auto-generation</div>
                  <div className="text-xs text-zinc-500">When ON, the system searches your keywords on the interval below and drafts posts automatically.</div>
                </div>
                <Switch checked={content.enabled} onCheckedChange={(v) => setContent({ ...content, enabled: v })} data-testid="content-enabled-switch" />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-sm font-medium text-zinc-700">Search interval</label>
                  <Select value={String(content.interval_hours)} onValueChange={(v) => setContent({ ...content, interval_hours: parseInt(v) })}>
                    <SelectTrigger data-testid="content-interval-select"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {[1, 2, 3, 6, 12, 24].map((h) => <SelectItem key={h} value={String(h)}>Every {h} hour{h > 1 ? "s" : ""}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex items-center justify-between p-3 rounded-md border border-zinc-200 mt-6">
                  <span className="text-sm font-medium text-zinc-700">Auto-publish to FB/IG</span>
                  <Switch checked={content.auto_publish} onCheckedChange={(v) => setContent({ ...content, auto_publish: v })} data-testid="content-autopublish-switch" />
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="text-sm font-medium text-zinc-700">Search keywords (jobs / notifications to track)</label>
                <div className="flex flex-wrap gap-2 mb-2" data-testid="content-keywords">
                  {content.search_keywords.map((k, i) => (
                    <Badge key={i} variant="outline" className="gap-1.5 py-1">
                      {k}
                      <button onClick={() => setContent({ ...content, search_keywords: content.search_keywords.filter((_, idx) => idx !== i) })} data-testid={`remove-keyword-${i}`}>
                        <Trash2 className="w-3 h-3 text-zinc-400 hover:text-rose-600" />
                      </button>
                    </Badge>
                  ))}
                  {content.search_keywords.length === 0 && <span className="text-xs text-zinc-400">No keywords yet.</span>}
                </div>
                <div className="flex gap-2">
                  <Input value={kw} onChange={(e) => setKw(e.target.value)} placeholder="e.g. Railway RRB recruitment" data-testid="content-keyword-input"
                    onKeyDown={(e) => { if (e.key === "Enter" && kw.trim()) { setContent({ ...content, search_keywords: [...content.search_keywords, kw.trim()] }); setKw(""); } }} />
                  <Button variant="outline" onClick={() => { if (kw.trim()) { setContent({ ...content, search_keywords: [...content.search_keywords, kw.trim()] }); setKw(""); } }} data-testid="add-keyword-btn">
                    <Plus className="w-4 h-4" />
                  </Button>
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="text-sm font-medium text-zinc-700">Search sources (RSS URL templates, use <span className="mono">{"{q}"}</span> for the keyword)</label>
                <Textarea rows={3} className="mono text-xs"
                  value={(content.search_sources || []).join("\n")}
                  onChange={(e) => setContent({ ...content, search_sources: e.target.value.split("\n").map((s) => s.trim()).filter(Boolean) })}
                  data-testid="content-sources-textarea" />
                <p className="text-xs text-zinc-400">One URL per line. Default uses Google News.</p>
              </div>

              <div className="flex justify-end">
                <Button onClick={saveContent} className="bg-blue-600 hover:bg-blue-700" data-testid="save-content-btn">Save auto-search settings</Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* TEMPLATES */}
        <TabsContent value="templates" className="mt-4 space-y-4">
          <Card>
            <CardHeader><CardTitle className="font-display text-lg">WhatsApp templates</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              {tpls.whatsapp_templates.map((t, i) => (
                <div key={i} className="p-3 rounded-md border border-zinc-200 space-y-2" data-testid={`template-row-${i}`}>
                  <div className="grid grid-cols-3 gap-2">
                    <Input value={t.id} placeholder="id" onChange={(e) => { const a = [...tpls.whatsapp_templates]; a[i] = { ...t, id: e.target.value }; setTpls({ ...tpls, whatsapp_templates: a }); }} />
                    <Input value={t.name} placeholder="name" onChange={(e) => { const a = [...tpls.whatsapp_templates]; a[i] = { ...t, name: e.target.value }; setTpls({ ...tpls, whatsapp_templates: a }); }} />
                    <Select value={t.lang} onValueChange={(v) => { const a = [...tpls.whatsapp_templates]; a[i] = { ...t, lang: v }; setTpls({ ...tpls, whatsapp_templates: a }); }}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent><SelectItem value="english">english</SelectItem><SelectItem value="hindi">hindi</SelectItem></SelectContent>
                    </Select>
                  </div>
                  <Textarea rows={2} value={t.body} placeholder="Message body — use {name} and {course}"
                    onChange={(e) => { const a = [...tpls.whatsapp_templates]; a[i] = { ...t, body: e.target.value }; setTpls({ ...tpls, whatsapp_templates: a }); }} />
                  <div className="flex justify-end">
                    <Button variant="ghost" size="sm" className="text-rose-600" onClick={() => setTpls({ ...tpls, whatsapp_templates: tpls.whatsapp_templates.filter((_, idx) => idx !== i) })} data-testid={`remove-template-${i}`}>
                      <Trash2 className="w-4 h-4 mr-1" /> Remove
                    </Button>
                  </div>
                </div>
              ))}
              <Button variant="outline" onClick={() => setTpls({ ...tpls, whatsapp_templates: [...tpls.whatsapp_templates, { id: `tpl_${Date.now()}`, name: "New template", lang: "english", body: "" }] })} data-testid="add-template-btn">
                <Plus className="w-4 h-4 mr-1" /> Add template
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle className="font-display text-lg">AI call opening scripts</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              {["english", "hindi"].map((lng) => (
                <div key={lng} className="space-y-1.5">
                  <label className="text-sm font-medium text-zinc-700 capitalize">{lng}</label>
                  <Textarea rows={2} value={tpls.call_scripts[lng] || ""} placeholder={`${lng} opening — use {name} and {course}`}
                    onChange={(e) => setTpls({ ...tpls, call_scripts: { ...tpls.call_scripts, [lng]: e.target.value } })} data-testid={`call-script-${lng}`} />
                </div>
              ))}
            </CardContent>
          </Card>

          <div className="flex justify-end">
            <Button onClick={saveTemplates} className="bg-blue-600 hover:bg-blue-700" data-testid="save-templates-btn">Save templates & scripts</Button>
          </div>
        </TabsContent>

        {/* TEAM */}
        <TabsContent value="team" className="mt-4">
          <Card>
            <CardHeader><CardTitle className="font-display text-lg">Team automation</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between p-3 rounded-md border border-zinc-200">
                <div>
                  <div className="font-medium text-sm">Round-robin lead assignment</div>
                  <div className="text-xs text-zinc-500">Automatically distribute new & imported leads evenly across counsellors.</div>
                </div>
                <Switch checked={team.round_robin} onCheckedChange={saveTeam} data-testid="team-roundrobin-switch" />
              </div>
              <p className="text-sm text-zinc-500">Manage team members on the <a href="/team" className="text-blue-600 hover:underline">Team page</a>.</p>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
