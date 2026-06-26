import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, STAGES } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import AddLeadDialog from "@/components/AddLeadDialog";
import BulkImportDialog from "@/components/BulkImportDialog";
import BulkOutreachDialog from "@/components/BulkOutreachDialog";
import StageBadge from "@/components/StageBadge";
import { Table, TableHeader, TableRow, TableHead, TableBody, TableCell } from "@/components/ui/table";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Search } from "lucide-react";

export default function Leads() {
  const [leads, setLeads] = useState([]);
  const [q, setQ] = useState("");
  const [stage, setStage] = useState("all");

  const load = async () => {
    const params = {};
    if (q) params.q = q;
    if (stage !== "all") params.stage = stage;
    const { data } = await api.get("/leads", { params });
    setLeads(data);
  };

  useEffect(() => {
    const t = setTimeout(load, 200);
    return () => clearTimeout(t);
    // eslint-disable-next-line
  }, [q, stage]);

  const counts = useMemo(() => {
    const c = { all: leads.length };
    STAGES.forEach((s) => (c[s.key] = leads.filter((l) => l.stage === s.key).length));
    return c;
  }, [leads]);

  return (
    <div className="p-8 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="font-display font-bold text-3xl tracking-tight">Leads</h1>
          <p className="text-sm text-zinc-500 mt-1">All your student leads with filters & search.</p>
        </div>
        <div className="flex items-center gap-2">
          <BulkOutreachDialog onDone={load} />
          <BulkImportDialog onDone={load} />
          <AddLeadDialog onCreated={load} />
        </div>
      </div>

      <Card className="mb-4">
        <CardContent className="p-4 flex items-center gap-3">
          <div className="relative flex-1">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400" />
            <Input
              placeholder="Search by name, phone, email, course…"
              className="pl-9"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              data-testid="leads-search-input"
            />
          </div>
          <Select value={stage} onValueChange={setStage}>
            <SelectTrigger className="w-52" data-testid="leads-stage-filter"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All stages ({counts.all})</SelectItem>
              {STAGES.map((s) => (
                <SelectItem key={s.key} value={s.key}>{s.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-0">
          <Table data-testid="leads-table">
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Phone</TableHead>
                <TableHead>Course</TableHead>
                <TableHead>Source</TableHead>
                <TableHead>Language</TableHead>
                <TableHead>Stage</TableHead>
                <TableHead>Owner</TableHead>
                <TableHead>Interest</TableHead>
                <TableHead>Added</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {leads.length === 0 && (
                <TableRow><TableCell colSpan={9} className="text-center text-zinc-500 py-12">No leads match your filters.</TableCell></TableRow>
              )}
              {leads.map((l) => (
                <TableRow key={l.id} className="cursor-pointer hover:bg-zinc-50" data-testid={`lead-row-${l.id}`}>
                  <TableCell className="font-medium">
                    <Link to={`/leads/${l.id}`} className="hover:text-blue-600">{l.name}</Link>
                  </TableCell>
                  <TableCell className="mono text-sm">{l.phone}</TableCell>
                  <TableCell>{l.course || "—"}</TableCell>
                  <TableCell className="capitalize">{l.source}</TableCell>
                  <TableCell className="capitalize">{l.language}</TableCell>
                  <TableCell><StageBadge stage={l.stage} /></TableCell>
                  <TableCell className="text-sm text-zinc-600">{l.owner_name || "—"}</TableCell>
                  <TableCell>
                    {l.interest_score != null ? (
                      <span className={`mono text-sm px-2 py-0.5 rounded ${
                        l.interest_score >= 70 ? "bg-emerald-50 text-emerald-700" :
                        l.interest_score >= 40 ? "bg-amber-50 text-amber-700" :
                        "bg-zinc-100 text-zinc-500"
                      }`}>{l.interest_score}</span>
                    ) : <span className="text-zinc-400 text-xs">—</span>}
                  </TableCell>
                  <TableCell className="text-sm text-zinc-500">{new Date(l.created_at).toLocaleDateString()}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
