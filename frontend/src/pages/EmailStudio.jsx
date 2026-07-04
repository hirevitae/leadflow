import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { toast } from "sonner";
import { Plus, Mail, Copy, Trash2, Pencil, Send, FileText } from "lucide-react";
import { EmailTemplateDialog } from "@/components/EmailTemplateDialog";
import { EmailCampaignDialog } from "@/components/EmailCampaignDialog";
import { EmailCampaignDetail } from "@/components/EmailCampaignDetail";

const STATUS_TINT = {
  sending: "bg-blue-100 text-blue-700", scheduled: "bg-amber-100 text-amber-700",
  paused: "bg-zinc-200 text-zinc-700", completed: "bg-emerald-100 text-emerald-700",
  canceled: "bg-rose-100 text-rose-700", draft: "bg-zinc-100 text-zinc-600",
};

export default function EmailStudio() {
  const [templates, setTemplates] = useState([]);
  const [campaigns, setCampaigns] = useState([]);
  const [categories, setCategories] = useState([]);
  const [tplOpen, setTplOpen] = useState(false);
  const [editTpl, setEditTpl] = useState(null);
  const [campOpen, setCampOpen] = useState(false);
  const [detailId, setDetailId] = useState(null);

  const loadTemplates = () => api.get("/email/templates").then(({ data }) => setTemplates(data)).catch(() => {});
  const loadCampaigns = () => api.get("/email/campaigns").then(({ data }) => setCampaigns(data)).catch(() => {});
  useEffect(() => {
    loadTemplates(); loadCampaigns();
    api.get("/email/template-categories").then(({ data }) => setCategories(data)).catch(() => {});
  }, []);

  const dupTemplate = async (id) => { await api.post(`/email/templates/${id}/duplicate`); toast.success("Duplicated"); loadTemplates(); };
  const delTemplate = async (id) => { await api.delete(`/email/templates/${id}`); toast.success("Deleted"); loadTemplates(); };

  return (
    <div className="p-8 max-w-6xl mx-auto" data-testid="email-studio-page">
      <div className="flex items-center gap-3 mb-6">
        <div className="w-11 h-11 rounded-md bg-blue-50 text-blue-700 flex items-center justify-center"><Mail className="w-6 h-6" /></div>
        <div>
          <h1 className="font-display font-bold text-2xl">Email Outreach</h1>
          <p className="text-sm text-zinc-500">Design templates, run campaigns, and track delivery & engagement.</p>
        </div>
      </div>

      <Tabs defaultValue="campaigns" onValueChange={(v) => { if (v === "campaigns") loadCampaigns(); if (v === "templates") loadTemplates(); }}>
        <TabsList>
          <TabsTrigger value="campaigns" data-testid="tab-campaigns"><Send className="w-4 h-4 mr-1" /> Campaigns</TabsTrigger>
          <TabsTrigger value="templates" data-testid="tab-templates"><FileText className="w-4 h-4 mr-1" /> Templates</TabsTrigger>
        </TabsList>

        <TabsContent value="campaigns" className="mt-4">
          <div className="flex justify-end mb-3">
            <Button onClick={() => setCampOpen(true)} className="bg-blue-600 hover:bg-blue-700" data-testid="new-campaign-btn"><Plus className="w-4 h-4 mr-1" /> New campaign</Button>
          </div>
          {campaigns.length === 0 ? (
            <Card><CardContent className="p-10 text-center text-zinc-500" data-testid="campaigns-empty">No campaigns yet. Create one to start emailing your leads.</CardContent></Card>
          ) : (
            <div className="space-y-2" data-testid="campaigns-list">
              {campaigns.map((c) => {
                const s = c.stats || {}; const done = (s.sent || 0) + (s.failed || 0);
                const pct = s.total ? Math.round(done / s.total * 100) : 0;
                return (
                  <Card key={c.id} className="hover:shadow-sm cursor-pointer" onClick={() => setDetailId(c.id)} data-testid={`campaign-${c.id}`}>
                    <CardContent className="p-4 flex items-center gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2"><span className="font-medium truncate">{c.name}</span><Badge className={STATUS_TINT[c.status] || ""}>{c.status}</Badge></div>
                        <div className="text-xs text-zinc-500 mt-0.5">{s.total || 0} recipients · {s.sent || 0} sent · {s.opened || 0} opened · {s.clicked || 0} clicked</div>
                      </div>
                      <div className="text-right"><div className="text-lg font-semibold text-zinc-800">{pct}%</div><div className="text-[11px] text-zinc-400">progress</div></div>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          )}
        </TabsContent>

        <TabsContent value="templates" className="mt-4">
          <div className="flex justify-end mb-3">
            <Button onClick={() => { setEditTpl(null); setTplOpen(true); }} className="bg-blue-600 hover:bg-blue-700" data-testid="new-template-btn"><Plus className="w-4 h-4 mr-1" /> New template</Button>
          </div>
          {templates.length === 0 ? (
            <Card><CardContent className="p-10 text-center text-zinc-500" data-testid="templates-empty">No templates yet. Create your first email template.</CardContent></Card>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3" data-testid="templates-list">
              {templates.map((t) => (
                <Card key={t.id} data-testid={`template-${t.id}`}>
                  <CardContent className="p-4">
                    <div className="flex items-start gap-2">
                      <div className="flex-1 min-w-0"><div className="font-medium truncate">{t.name}</div><Badge variant="outline" className="text-[11px] mt-1">{t.category}</Badge></div>
                    </div>
                    <div className="text-xs text-zinc-500 mt-2 truncate">{t.subject || "(no subject)"}</div>
                    <div className="flex gap-1 mt-3">
                      <Button variant="ghost" size="sm" onClick={() => { setEditTpl(t); setTplOpen(true); }} data-testid={`edit-${t.id}`}><Pencil className="w-3.5 h-3.5" /></Button>
                      <Button variant="ghost" size="sm" onClick={() => dupTemplate(t.id)} data-testid={`dup-${t.id}`}><Copy className="w-3.5 h-3.5" /></Button>
                      <Button variant="ghost" size="sm" className="text-rose-600 ml-auto" onClick={() => delTemplate(t.id)} data-testid={`del-${t.id}`}><Trash2 className="w-3.5 h-3.5" /></Button>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>

      <EmailTemplateDialog open={tplOpen} onOpenChange={setTplOpen} template={editTpl} categories={categories} onSaved={loadTemplates} />
      <EmailCampaignDialog open={campOpen} onOpenChange={setCampOpen} templates={templates} onCreated={loadCampaigns} />
      <EmailCampaignDetail campaignId={detailId} open={!!detailId} onOpenChange={(v) => !v && setDetailId(null)} onChanged={loadCampaigns} />
    </div>
  );
}
