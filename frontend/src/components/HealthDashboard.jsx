import { useEffect, useState } from "react";
import { api, formatApiError } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Table, TableHeader, TableRow, TableHead, TableBody, TableCell } from "@/components/ui/table";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { toast } from "sonner";
import { Activity, RefreshCw, Loader2 } from "lucide-react";

const STATUS = {
  connected: { dot: "🟢", label: "Connected", cls: "bg-emerald-50 text-emerald-700 border-emerald-200" },
  needs_verification: { dot: "🟡", label: "Needs Verification", cls: "bg-amber-50 text-amber-700 border-amber-200" },
  invalid: { dot: "🔴", label: "Invalid", cls: "bg-rose-50 text-rose-700 border-rose-200" },
  not_configured: { dot: "⚪", label: "Not Configured", cls: "bg-zinc-100 text-zinc-500 border-zinc-200" },
};
const ago = (iso) => (iso ? new Date(iso).toLocaleString() : "—");

export default function HealthDashboard() {
  const [rows, setRows] = useState([]);
  const [history, setHistory] = useState([]);
  const [running, setRunning] = useState(false);

  const load = async () => {
    try {
      const [h, hist] = await Promise.all([
        api.get("/admin/integrations/health"),
        api.get("/admin/integrations/history?limit=50"),
      ]);
      setRows(h.data);
      setHistory(h_to_chart(hist.data));
    } catch (e) { toast.error("Could not load health data"); }
  };
  useEffect(() => { load(); }, []);

  const h_to_chart = (hist) =>
    hist.map((d) => ({
      t: new Date(d.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      ms: d.response_time_ms || 0,
      provider: d.provider,
    }));

  const runAll = async () => {
    setRunning(true);
    const configured = rows.filter((r) => r.status !== "not_configured");
    for (const r of configured) {
      try { await api.post("/admin/integrations/test", { provider: r.provider }); } catch { /* graceful */ }
    }
    await load();
    setRunning(false);
    toast.success(`Tested ${configured.length} integration(s)`);
  };

  return (
    <div className="space-y-4" data-testid="health-dashboard">
      <div className="flex items-center justify-between">
        <h2 className="font-display font-semibold text-lg flex items-center gap-2"><Activity className="w-5 h-5 text-blue-600" /> Integration Health</h2>
        <Button variant="outline" size="sm" onClick={runAll} disabled={running} data-testid="run-all-tests-btn">
          {running ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <RefreshCw className="w-4 h-4 mr-1" />} Run all tests
        </Button>
      </div>

      <Card>
        <CardContent className="p-0">
          <Table data-testid="health-table">
            <TableHeader>
              <TableRow>
                <TableHead>Integration</TableHead><TableHead>Status</TableHead>
                <TableHead>Last Verified</TableHead><TableHead>Response Time</TableHead><TableHead>Last Error</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((r) => {
                const st = STATUS[r.status] || STATUS.not_configured;
                return (
                  <TableRow key={r.provider} data-testid={`health-row-${r.provider}`}>
                    <TableCell className="font-medium">{r.label}</TableCell>
                    <TableCell><Badge className={st.cls}>{st.dot} {st.label}</Badge></TableCell>
                    <TableCell className="text-sm text-zinc-600">{ago(r.last_verified_at)}</TableCell>
                    <TableCell className="text-sm text-zinc-600">{r.response_time_ms ? `${r.response_time_ms} ms` : "—"}</TableCell>
                    <TableCell className="text-sm text-rose-500 max-w-[220px] truncate" title={r.last_error || ""}>{r.last_error || "—"}</TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-5">
          <div className="text-sm font-medium text-zinc-700 mb-3">Response time (recent tests)</div>
          {history.length === 0 ? (
            <div className="text-sm text-zinc-500 py-10 text-center">No connection tests yet. Run a test to see response times.</div>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={history} margin={{ top: 5, right: 10, left: -10, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                <XAxis dataKey="t" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} unit="ms" />
                <Tooltip formatter={(v, n, p) => [`${v} ms`, p.payload.provider]} />
                <Line type="monotone" dataKey="ms" stroke="#2563eb" strokeWidth={2} dot={{ r: 3 }} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
