import { useEffect, useState } from "react";
import { api, STAGES } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer,
  LineChart, Line, PieChart, Pie, Cell, Legend
} from "recharts";

const PIE_COLORS = ["#2563EB", "#16A34A", "#7C3AED", "#EAB308", "#DC2626", "#0EA5E9", "#71717A"];

export default function Analytics() {
  const [data, setData] = useState(null);
  useEffect(() => { api.get("/analytics/overview").then((r) => setData(r.data)); }, []);

  if (!data) return <div className="p-8 text-zinc-500">Loading…</div>;

  const stageData = STAGES.map((s) => ({ name: s.label, value: data.stages[s.key] || 0 }));

  return (
    <div className="p-8 max-w-7xl mx-auto">
      <div className="mb-6">
        <h1 className="font-display font-bold text-3xl tracking-tight">Analytics</h1>
        <p className="text-sm text-zinc-500 mt-1">Funnel performance, sources & daily inflow.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <Card><CardContent className="p-5">
          <div className="text-xs uppercase tracking-wide text-zinc-500 font-semibold">Total Leads</div>
          <div className="font-display text-3xl font-bold mt-1.5" data-testid="analytics-total">{data.total_leads}</div>
        </CardContent></Card>
        <Card><CardContent className="p-5">
          <div className="text-xs uppercase tracking-wide text-zinc-500 font-semibold">Conversion Rate</div>
          <div className="font-display text-3xl font-bold mt-1.5 text-emerald-600">{data.conv_rate}%</div>
        </CardContent></Card>
        <Card><CardContent className="p-5">
          <div className="text-xs uppercase tracking-wide text-zinc-500 font-semibold">Win Rate</div>
          <div className="font-display text-3xl font-bold mt-1.5 text-blue-600">{data.win_rate}%</div>
        </CardContent></Card>
        <Card><CardContent className="p-5">
          <div className="text-xs uppercase tracking-wide text-zinc-500 font-semibold">Outreach</div>
          <div className="font-display text-3xl font-bold mt-1.5">{data.whatsapp_sent + data.ai_calls}</div>
          <div className="text-xs text-zinc-500 mt-1">{data.whatsapp_sent} WhatsApp · {data.ai_calls} calls</div>
        </CardContent></Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
        <Card className="lg:col-span-2">
          <CardContent className="p-6">
            <h2 className="font-display font-semibold mb-4">Leads per stage</h2>
            <div className="h-72" data-testid="chart-stages">
              <ResponsiveContainer>
                <BarChart data={stageData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#E4E4E7" />
                  <XAxis dataKey="name" stroke="#71717A" fontSize={11} angle={-15} textAnchor="end" height={60} />
                  <YAxis stroke="#71717A" fontSize={12} allowDecimals={false} />
                  <Tooltip />
                  <Bar dataKey="value" fill="#2563EB" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <h2 className="font-display font-semibold mb-4">Source breakdown</h2>
            <div className="h-72" data-testid="chart-sources">
              <ResponsiveContainer>
                <PieChart>
                  <Pie data={data.sources} dataKey="count" nameKey="source" cx="50%" cy="50%" outerRadius={80} label>
                    {data.sources.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                  </Pie>
                  <Legend />
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardContent className="p-6">
          <h2 className="font-display font-semibold mb-4">Daily new leads (last 14 days)</h2>
          <div className="h-72" data-testid="chart-daily">
            <ResponsiveContainer>
              <LineChart data={data.daily}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E4E4E7" />
                <XAxis dataKey="date" stroke="#71717A" fontSize={11} />
                <YAxis stroke="#71717A" fontSize={12} allowDecimals={false} />
                <Tooltip />
                <Line type="monotone" dataKey="count" stroke="#2563EB" strokeWidth={2} dot={{ r: 3 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
