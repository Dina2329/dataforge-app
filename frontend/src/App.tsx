import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Toaster } from "./components/ui/Toaster";
import { AppLayout } from "./components/shared/AppLayout";
import { ProtectedRoute } from "./components/shared/ProtectedRoute";
import { LoginPage } from "./routes/LoginPage";
import { WorkspacesPage } from "./routes/WorkspacesPage";
import { BasesPage } from "./routes/BasesPage";
import { TablesPage } from "./routes/TablesPage";
import { TableGridPage } from "./routes/TableGridPage";
import { DataSourcesPage } from "./routes/DataSourcesPage";
import { MembersPage } from "./routes/MembersPage";
import { DashboardsListPage } from "./routes/DashboardsListPage";
import { DashboardBuilderPage } from "./routes/DashboardBuilderPage";
import { AutomationsPage } from "./routes/AutomationsPage";
import { PublicDashboardPage } from "./routes/PublicDashboardPage";
import { PublicFormPage } from "./routes/PublicFormPage";
import { AuditLogPage } from "./routes/AuditLogPage";
import { PrerequestPage } from "./routes/PrerequestPage";
import { PendingSyncChangesPage } from "./routes/PendingSyncChangesPage";

export function App() {
  return (
    <BrowserRouter>
      <Toaster />
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/share/dashboards/:token" element={<PublicDashboardPage />} />
        <Route path="/share/forms/:token" element={<PublicFormPage />} />
        <Route
          element={
            <ProtectedRoute>
              <AppLayout />
            </ProtectedRoute>
          }
        >
          <Route path="/" element={<WorkspacesPage />} />
          <Route path="/workspaces/:workspaceId" element={<BasesPage />} />
          <Route path="/workspaces/:workspaceId/data-sources" element={<DataSourcesPage />} />
          <Route path="/workspaces/:workspaceId/members" element={<MembersPage />} />
          <Route path="/workspaces/:workspaceId/audit-log" element={<AuditLogPage />} />
          <Route path="/workspaces/:workspaceId/prerequest" element={<PrerequestPage />} />
          <Route path="/workspaces/:workspaceId/pending-sync-changes" element={<PendingSyncChangesPage />} />
          <Route path="/workspaces/:workspaceId/dashboards" element={<DashboardsListPage />} />
          <Route path="/dashboards/:dashboardId" element={<DashboardBuilderPage />} />
          <Route path="/bases/:baseId" element={<TablesPage />} />
          <Route path="/tables/:tableId" element={<TableGridPage />} />
          <Route path="/tables/:tableId/automations" element={<AutomationsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
