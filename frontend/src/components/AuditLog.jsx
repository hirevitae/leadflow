import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Table, TableHeader, TableRow, TableHead, TableBody, TableCell } from "@/components/ui/table";
import { toast } from "sonner";
import { ScrollText } from "lucide-react";

const ACTION_CLS = {
  update: "bg-blue-50 text-blue-700 border-blue-200",
  test: "bg-violet-50 text-violet-700 border-violet-200",
  rotate: "bg-amber-50 text-amber-700 border-amber-200",
  reset: "bg-rose-50 text-rose-700 border-rose-200",
  export: "bg-zinc-100 text-zinc-600 border-zinc-200",
  import: "bg-emerald-50 text-emerald-700 border-emerald-200",
};

export default function AuditLog() {
  const [logs, setLogs] = useState([]);

  useEffect(() => {
    api.get("/admin/integrations/audit").then((r) => setLogs(r.data)).catch(() => toast.error("Could not load audit logs"));
  }, []);

  return (
    <div className="space-y-4" data-testid="audit-log">
      <h2 className="font-display font-semibold text-lg flex items-center gap-2"><ScrollText className="w-5 h-5 text-blue-600" /> Audit Logs</h2>
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
                <TableRow><TableCell colSpan={7} className="text-center text-zinc-500 py-10">No audit activity yet.</TableCell></TableRow>
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
    </div>
  );
}
