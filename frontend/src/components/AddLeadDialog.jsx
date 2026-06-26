import { useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api, formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Plus } from "lucide-react";

export default function AddLeadDialog({ onCreated, triggerLabel = "Add lead" }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    name: "", phone: "", email: "", course: "",
    source: "website", language: "english", priority: "medium", notes: "",
  });
  const [saving, setSaving] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const { data } = await api.post("/leads", form);
      toast.success(`Lead "${data.name}" added`);
      setOpen(false);
      setForm({ name: "", phone: "", email: "", course: "", source: "website", language: "english", priority: "medium", notes: "" });
      onCreated?.(data);
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail) || "Failed to create lead");
    } finally { setSaving(false); }
  };

  const upd = (k) => (v) => setForm((f) => ({ ...f, [k]: v?.target ? v.target.value : v }));

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button className="bg-blue-600 hover:bg-blue-700" data-testid="open-add-lead-btn">
          <Plus className="w-4 h-4 mr-1.5" /> {triggerLabel}
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-[520px]" data-testid="add-lead-dialog">
        <DialogHeader>
          <DialogTitle className="font-display">New lead</DialogTitle>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Name *</Label>
              <Input required value={form.name} onChange={upd("name")} data-testid="lead-name-input" />
            </div>
            <div>
              <Label>Phone *</Label>
              <Input required value={form.phone} onChange={upd("phone")} data-testid="lead-phone-input" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Email</Label>
              <Input type="email" value={form.email} onChange={upd("email")} data-testid="lead-email-input" />
            </div>
            <div>
              <Label>Course interested</Label>
              <Input value={form.course} onChange={upd("course")} placeholder="e.g. Data Science" data-testid="lead-course-input" />
            </div>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <Label>Source</Label>
              <Select value={form.source} onValueChange={upd("source")}>
                <SelectTrigger data-testid="lead-source-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="website">Website</SelectItem>
                  <SelectItem value="referral">Referral</SelectItem>
                  <SelectItem value="instagram">Instagram</SelectItem>
                  <SelectItem value="facebook">Facebook</SelectItem>
                  <SelectItem value="google_ads">Google Ads</SelectItem>
                  <SelectItem value="walk_in">Walk-in</SelectItem>
                  <SelectItem value="manual">Manual</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Language</Label>
              <Select value={form.language} onValueChange={upd("language")}>
                <SelectTrigger data-testid="lead-language-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="english">English</SelectItem>
                  <SelectItem value="hindi">Hindi</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Priority</Label>
              <Select value={form.priority} onValueChange={upd("priority")}>
                <SelectTrigger data-testid="lead-priority-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="low">Low</SelectItem>
                  <SelectItem value="medium">Medium</SelectItem>
                  <SelectItem value="high">High</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div>
            <Label>Notes</Label>
            <Textarea rows={3} value={form.notes} onChange={upd("notes")} data-testid="lead-notes-input" />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setOpen(false)} data-testid="cancel-add-lead-btn">Cancel</Button>
            <Button type="submit" className="bg-blue-600 hover:bg-blue-700" disabled={saving} data-testid="submit-add-lead-btn">
              {saving ? "Saving…" : "Create lead"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
