import axios from "axios";

export const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export const api = axios.create({
  baseURL: API,
  withCredentials: true,
});

// Token fallback (in case cookies are blocked)
api.interceptors.request.use((config) => {
  const t = localStorage.getItem("lf_token");
  if (t && !config.headers.Authorization) {
    config.headers.Authorization = `Bearer ${t}`;
  }
  return config;
});

export function formatApiError(detail) {
  if (detail == null) return "Something went wrong.";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail.map((e) => (e && typeof e.msg === "string" ? e.msg : JSON.stringify(e))).join(" ");
  if (detail && typeof detail.msg === "string") return detail.msg;
  return String(detail);
}

export const STAGES = [
  { key: "new",             label: "New",             tint: "bg-zinc-100 text-zinc-700 border-zinc-200" },
  { key: "contacted",       label: "Contacted",       tint: "bg-blue-50 text-blue-700 border-blue-200" },
  { key: "interested",      label: "Interested",      tint: "bg-indigo-50 text-indigo-700 border-indigo-200" },
  { key: "demo_scheduled",  label: "Demo Scheduled",  tint: "bg-violet-50 text-violet-700 border-violet-200" },
  { key: "negotiation",     label: "Negotiation",     tint: "bg-amber-50 text-amber-800 border-amber-200" },
  { key: "enrolled",        label: "Enrolled",        tint: "bg-emerald-50 text-emerald-700 border-emerald-200" },
  { key: "lost",            label: "Lost",            tint: "bg-rose-50 text-rose-700 border-rose-200" },
];

export const stageMeta = (key) => STAGES.find((s) => s.key === key) || STAGES[0];
