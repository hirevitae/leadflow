import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { LayoutDashboard, Users, KanbanSquare, BarChart3, Inbox, Sparkles, LogOut, GraduationCap } from "lucide-react";
import { Button } from "@/components/ui/button";

const navItems = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, exact: true, testid: "nav-dashboard" },
  { to: "/inbox", label: "Inbox", icon: Inbox, testid: "nav-inbox" },
  { to: "/content", label: "Content Studio", icon: Sparkles, testid: "nav-content" },
  { to: "/leads", label: "Leads", icon: Users, testid: "nav-leads" },
  { to: "/pipeline", label: "Pipeline", icon: KanbanSquare, testid: "nav-pipeline" },
  { to: "/analytics", label: "Analytics", icon: BarChart3, testid: "nav-analytics" },
];

export default function Layout({ children }) {
  const { user, logout } = useAuth();
  const nav = useNavigate();

  return (
    <div className="min-h-screen flex bg-zinc-50">
      <aside className="w-60 bg-white border-r border-zinc-200 flex flex-col" data-testid="app-sidebar">
        <div className="px-6 py-6 border-b border-zinc-200 flex items-center gap-2">
          <div className="w-8 h-8 rounded-md bg-blue-600 flex items-center justify-center">
            <GraduationCap className="w-5 h-5 text-white" strokeWidth={1.75} />
          </div>
          <div>
            <div className="font-display font-bold text-zinc-900 leading-tight">LeadFlow</div>
            <div className="text-xs text-zinc-500 leading-none mt-0.5">Student CRM</div>
          </div>
        </div>

        <nav className="flex-1 px-3 py-4 space-y-1">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.exact}
              data-testid={item.testid}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors ${
                  isActive
                    ? "bg-blue-600 text-white"
                    : "text-zinc-700 hover:bg-zinc-100"
                }`
              }
            >
              <item.icon className="w-4 h-4" strokeWidth={1.75} />
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-zinc-200 p-3">
          <div className="px-2 py-2 mb-1">
            <div className="text-sm font-medium text-zinc-900 truncate" data-testid="user-name">{user?.name}</div>
            <div className="text-xs text-zinc-500 truncate">{user?.email}</div>
          </div>
          <Button
            variant="ghost"
            className="w-full justify-start text-zinc-700"
            data-testid="logout-btn"
            onClick={async () => { await logout(); nav("/login"); }}
          >
            <LogOut className="w-4 h-4 mr-2" />
            Sign out
          </Button>
        </div>
      </aside>

      <main className="flex-1 overflow-auto">
        {children}
      </main>
    </div>
  );
}
