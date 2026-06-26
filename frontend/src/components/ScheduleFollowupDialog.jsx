import { useState } from "react";
import { api, formatApiError } from "@/lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { CalendarClock } from "lucide-react";

export default function ScheduleFollowupDialog({ lead, onDone }) {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [due, setDue] = useState("");

  const submit = async () => {
    if (!title.trim() || !due) { toast.error("Title and date required"); return; }
    try {
      await api.post("/tasks", { title, due_date: new Date(due).toISOString(), lead_id: lead.id });
      toast.success("Follow-up scheduled");
      setOpen(false); setTitle(""); setDue("");
      onDone?.();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail) || "Failed"); }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" data-testid="open-schedule-followup-btn"><CalendarClock className="w-4 h-4 mr-1" /> Schedule follow-up</Button>
      </DialogTrigger>
      <DialogContent data-testid="schedule-followup-dialog">
        <DialogHeader><DialogTitle className="font-display">Schedule follow-up</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <Input placeholder={`e.g. Call ${lead.name} about demo`} value={title} onChange={(e) => setTitle(e.target.value)} data-testid="followup-title-input" />
          <Input type="datetime-local" value={due} onChange={(e) => setDue(e.target.value)} data-testid="followup-due-input" />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
          <Button onClick={submit} disabled={!title.trim() || !due} className="bg-blue-600 hover:bg-blue-700" data-testid="submit-followup-btn">Schedule</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
