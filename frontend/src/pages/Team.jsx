import { useEffect, useState } from "react";
import { api, formatApiError } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableHeader, TableRow, TableHead, TableBody, TableCell } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { UserPlus, Trash2, Shield, User } from "lucide-react";

export default function Team() {
  const [users, setUsers] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", email: "", password: "", role: "counsellor" });

  const load = async () => {
    try { const { data } = await api.get("/users"); setUsers(data); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail) || "Could not load users"); }
  };
  useEffect(() => { load(); }, []);

  const create = async () => {
    try {
      await api.post("/users", form);
      toast.success(`${form.name} added`);
      setOpen(false); setForm({ name: "", email: "", password: "", role: "counsellor" });
      load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail) || "Create failed"); }
  };

  const remove = async (u) => {
    if (!confirm(`Remove ${u.name}?`)) return;
    try { await api.delete(`/users/${u.id}`); toast.success("User removed"); load(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail) || "Delete failed"); }
  };

  return (
    <div className="p-8 max-w-5xl mx-auto" data-testid="team-page">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="font-display font-bold text-3xl tracking-tight">Team</h1>
          <p className="text-sm text-zinc-500 mt-1">Manage counsellors and admins. Counsellors see only their assigned leads.</p>
        </div>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button className="bg-blue-600 hover:bg-blue-700" data-testid="add-user-btn"><UserPlus className="w-4 h-4 mr-1.5" /> Add member</Button>
          </DialogTrigger>
          <DialogContent data-testid="add-user-dialog">
            <DialogHeader><DialogTitle className="font-display">Add team member</DialogTitle></DialogHeader>
            <div className="space-y-3">
              <Input placeholder="Full name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="user-name-input" />
              <Input placeholder="Email" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} data-testid="user-email-input" />
              <Input placeholder="Password (min 6 chars)" type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} data-testid="user-password-input" />
              <Select value={form.role} onValueChange={(v) => setForm({ ...form, role: v })}>
                <SelectTrigger data-testid="user-role-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="counsellor">Counsellor</SelectItem>
                  <SelectItem value="admin">Admin</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
              <Button onClick={create} disabled={!form.name || !form.email || form.password.length < 6} className="bg-blue-600 hover:bg-blue-700" data-testid="submit-user-btn">Add member</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      <Card>
        <CardContent className="p-0">
          <Table data-testid="team-table">
            <TableHeader>
              <TableRow><TableHead>Name</TableHead><TableHead>Email</TableHead><TableHead>Role</TableHead><TableHead className="text-right">Actions</TableHead></TableRow>
            </TableHeader>
            <TableBody>
              {users.map((u) => (
                <TableRow key={u.id} data-testid={`user-row-${u.id}`}>
                  <TableCell className="font-medium">{u.name}</TableCell>
                  <TableCell className="text-sm text-zinc-600">{u.email}</TableCell>
                  <TableCell>
                    <Badge variant="outline" className={u.role === "admin" ? "text-blue-700 border-blue-200 bg-blue-50" : "text-zinc-600"}>
                      {u.role === "admin" ? <Shield className="w-3 h-3 mr-1" /> : <User className="w-3 h-3 mr-1" />}{u.role}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right">
                    <Button variant="ghost" size="sm" className="text-rose-600" onClick={() => remove(u)} data-testid={`delete-user-${u.id}`}>
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
