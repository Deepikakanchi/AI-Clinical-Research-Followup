/*
 * App.jsx - All routes and role guards
 *
 * One login page for everyone. After login the backend's home_path decides:
 *   COORDINATOR -> /coordinator/dashboard     REVIEWER -> /reviewer/queue
 * RequireRole sends a user who opens the other role's pages to /not-allowed.
 * The backend still checks the role on every request; these guards only decide
 * which screens are shown.
 */
import { Navigate, Route, Routes } from 'react-router-dom';
import { RequireRole, useAuth } from './components/common/AuthContext.jsx';
import Layout from './components/common/Layout.jsx';
import LoginPage from './pages/LoginPage.jsx';
import NotAllowedPage from './pages/NotAllowedPage.jsx';
import DashboardPage from './pages/coordinator/DashboardPage.jsx';
import StudiesPage from './pages/coordinator/StudiesPage.jsx';
import ParticipantsPage from './pages/coordinator/ParticipantsPage.jsx';
import ParticipantProfilePage from './pages/coordinator/ParticipantProfilePage.jsx';
import VisitsPage from './pages/coordinator/VisitsPage.jsx';
import VisitDetailPage from './pages/coordinator/VisitDetailPage.jsx';
import FollowUpsPage from './pages/coordinator/FollowUpsPage.jsx';
import ReviewQueuePage from './pages/reviewer/ReviewQueuePage.jsx';
import SummaryReviewPage from './pages/reviewer/SummaryReviewPage.jsx';

function HomeRedirect() {
  const { user, ready } = useAuth();
  if (!ready) return <div className="page-loading">Loading workspace…</div>;
  return <Navigate to={user ? user.home_path : '/login'} replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<HomeRedirect />} />
      <Route path="/login" element={<LoginPage />} />

      {/* Coordinator screens */}
      <Route element={<RequireRole role="COORDINATOR"><Layout /></RequireRole>}>
        <Route path="/coordinator/dashboard" element={<DashboardPage />} />
        <Route path="/coordinator/studies" element={<StudiesPage />} />
        <Route path="/coordinator/participants" element={<ParticipantsPage />} />
        <Route path="/coordinator/participants/:id" element={<ParticipantProfilePage />} />
        <Route path="/coordinator/visits" element={<VisitsPage />} />
        <Route path="/coordinator/visits/:id" element={<VisitDetailPage />} />
        <Route path="/coordinator/follow-ups" element={<FollowUpsPage />} />
      </Route>

      {/* Reviewer screens */}
      <Route element={<RequireRole role="REVIEWER"><Layout /></RequireRole>}>
        <Route path="/reviewer/queue" element={<ReviewQueuePage />} />
        <Route path="/reviewer/summaries/:id" element={<SummaryReviewPage />} />
      </Route>

      {/* Any signed-in user */}
      <Route element={<RequireRole><Layout /></RequireRole>}>
        <Route path="/not-allowed" element={<NotAllowedPage />} />
      </Route>

      <Route path="*" element={<HomeRedirect />} />
    </Routes>
  );
}