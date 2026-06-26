import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AuthProvider } from "@/context/AuthContext";
import ProtectedRoute from "@/components/ProtectedRoute";
import Layout from "@/components/Layout";
import Login from "@/pages/Login";
import Register from "@/pages/Register";
import Dashboard from "@/pages/Dashboard";
import Leads from "@/pages/Leads";
import LeadDetail from "@/pages/LeadDetail";
import Pipeline from "@/pages/Pipeline";
import Analytics from "@/pages/Analytics";
import Inbox from "@/pages/Inbox";
import ContentStudio from "@/pages/ContentStudio";
import Followups from "@/pages/Followups";
import Team from "@/pages/Team";
import Settings from "@/pages/Settings";
import { Toaster } from "@/components/ui/sonner";

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route
            path="/"
            element={<ProtectedRoute><Layout><Dashboard /></Layout></ProtectedRoute>}
          />
          <Route
            path="/leads"
            element={<ProtectedRoute><Layout><Leads /></Layout></ProtectedRoute>}
          />
          <Route
            path="/leads/:id"
            element={<ProtectedRoute><Layout><LeadDetail /></Layout></ProtectedRoute>}
          />
          <Route
            path="/pipeline"
            element={<ProtectedRoute><Layout><Pipeline /></Layout></ProtectedRoute>}
          />
          <Route path="/analytics" element={<ProtectedRoute><Layout><Analytics /></Layout></ProtectedRoute>} />
          <Route path="/inbox" element={<ProtectedRoute><Layout><Inbox /></Layout></ProtectedRoute>} />
          <Route path="/content" element={<ProtectedRoute><Layout><ContentStudio /></Layout></ProtectedRoute>} />
          <Route path="/followups" element={<ProtectedRoute><Layout><Followups /></Layout></ProtectedRoute>} />
          <Route path="/team" element={<ProtectedRoute><Layout><Team /></Layout></ProtectedRoute>} />
          <Route path="/settings" element={<ProtectedRoute><Layout><Settings /></Layout></ProtectedRoute>} />
        </Routes>
      </BrowserRouter>
      <Toaster richColors position="top-right" />
    </AuthProvider>
  );
}

export default App;
