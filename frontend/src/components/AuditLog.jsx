import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Table, TableHeader, TableRow, TableHead, TableBody, TableCell } from "@/components/ui/table";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import { ScrollText, ChevronLeft, ChevronRight } from "lucide-react";

const ACTION_CLS = {
  update: "bg-blue-50 text-blue-700 border-blue-200",
  test: "bg-violet-50 text-violet-700 border-violet-200",
  rotate: "bg-amber-50 text-amber-700 border-amber-200",
  reset: "bg-rose-50 text-rose-700 border-rose-200",
  export: "bg-zinc-100 text-zinc-600 border-zinc-200",
  import: "bg-emerald-50 text-emerald-700 border-emerald-200",
};
const PROVIDERS = ["whatsapp", "facebook", "instagram", "email", "ai", "all"];
const ACTIONS = ["update", "test", "rotate", "reset", "export", "import"];
const PAGE = 25;

export default function AuditLog() {
  const [logs, setLogs] = useState([]);
  const [total, setTotal] = useState(0);
  const [skip, setSkip] = useState(0);
  const [provider, setProvider] = useState("");
  const [action, setAction] = useState("");

  const load = useCallback(async () => {
    try {
      const params = new URLSearchParams({ limit: String(PAGE), skip: String(skip) });
      if (provider) params.set("provider", provider);
      if (action) params.set("action", action);
      const { data } = await api.get(`/admin/integrations/audit?${params.toString()}`);
      setLogs(data.items); setTotal(data.total);
    } catch (e) { toast.error("Could not load audit logs"); }
  }, [skip, provider, action]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { setSkip(0); }, [provider, action]);

  const page = Math.floor(skip / PAGE) + 1;
  const pages = Math.max(1, Math.ceil(total / PAGE));

  return (
    <div className="space-y-4" data-testid="audit-log">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h2 className="font-display font-semibold text-lg flex items-center gap-2"><ScrollText className="w-5 h-5 text-blue-600" /> Audit Logs</h2>
        <div className="flex items-center gap-2">
          <Select value={provider || "all"} onValueChange={(v) => setProvider(v === "all" ? "" : v)}>
            <SelectTrigger className="w-40 h-9" data-testid="audit-filter-provider"><SelectValue placeholder="All providers" /></SelectTrigger>
            <SelectContent>{PROVIDERS.map((p) => <SelectItem key={p} value={p}>{p === "all" ? "All providers" : p}</SelectItem>)}</SelectContent>
          </Select>
          <Select value={action || "all"} onValueChange={(v) => setAction(v === "all" ? "" : v)}>
            <SelectTrigger className="w-36 h-9" data-testid="audit-filter-action"><SelectValue placeholder="All actions" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All actions</SelectItem>
              {ACTIONS.map((a) => <SelectItem key={a} value={a}>{a}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
      </div>

      <Card>
        <CardContent className="p-0">
          <Table data-testid="audit-table">
            <TableHeader>
              <TableRow>
                <TableHead>When</TableHead><TableHead>Provider</TableHead><TableHead>Action</TableHead>
                <TableHead>Old</TableHead><TableHead>New</TableHead><TableHead>By</TableHead><TableHead>IP</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {logs.length === 0 && (
                <TableRow><TableCell colSpan={7} className="text-center text-zinc-500 py-10">No audit activity for this filter.</TableCell></TableRow>
              )}
              {logs.map((l, i) => (
                <TableRow key={i} data-testid={`audit-row-${i}`}>
                  <TableCell className="text-xs text-zinc-500 whitespace-nowrap">{new Date(l.created_at).toLocaleString()}</TableCell>
                  <TableCell className="text-sm font-medium capitalize">{l.provider}</TableCell>
                  <TableCell><Badge variant="outline" className={ACTION_CLS[l.action] || ""}>{l.action}</Badge></TableCell>
                  <TableCell className="text-xs mono text-zinc-500">{l.old_value || "—"}</TableCell>
                  <TableCell className="text-xs mono text-zinc-500">{l.new_value || "—"}</TableCell>
                  <TableCell className="text-xs text-zinc-600">{l.updated_by}</TableCell>
                  <TableCell className="text-xs text-zinc-400">{l.ip_address || "—"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <div className="flex items-center justify-between text-sm text-zinc-500" data-testid="audit-pagination">
        <span>{total} entr{total === 1 ? "y" : "ies"} · page {page} of {pages}</span>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" disabled={skip === 0} onClick={() => setSkip(Math.max(0, skip - PAGE))} data-testid="audit-prev-btn"><ChevronLeft className="w-4 h-4" /> Prev</Button>
          <Button variant="outline" size="sm" disabled={skip + PAGE >= total} onClick={() => setSkip(skip + PAGE)} data-testid="audit-next-btn">Next <ChevronRight className="w-4 h-4" /></Button>
        </div>
      </div>
    </div>
  );
}
