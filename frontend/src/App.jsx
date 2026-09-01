import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import ProtectedRoute from './components/ProtectedRoute';
import Header from './components/Header';
import NotificationToast from './components/NotificationToast';
import Landing from './pages/Landing';
import Dashboard from './pages/Dashboard';
import ReportForm from './pages/ReportForm';
import Matches from './pages/Matches';
import ClaimedItems from './pages/ClaimedItems';
import Login from './pages/Login';
import RequestAccess from './pages/RequestAccess';
import ForgotPassword from './pages/ForgotPassword';
import SetPassword from './pages/SetPassword';
import ChangePassword from './pages/ChangePassword';
import './styles/global.css';

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Header />
        <NotificationToast />
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/lost" element={<Dashboard reportType="lost" />} />
          <Route path="/found" element={<Dashboard reportType="found" />} />
          <Route path="/claimed" element={<ClaimedItems />} />

          <Route path="/login" element={<Login />} />
          <Route path="/request-access" element={<RequestAccess />} />
          <Route path="/forgot-password" element={<ForgotPassword />} />
          <Route
            path="/set-password"
            element={
              <ProtectedRoute>
                <SetPassword />
              </ProtectedRoute>
            }
          />
          <Route
            path="/change-password"
            element={
              <ProtectedRoute>
                <ChangePassword />
              </ProtectedRoute>
            }
          />

          {/* Reporting and viewing matches both need to know who the
              logged-in user is (reporter_id gets stamped server-side,
              and contact-reveal gating needs the JWT), so both are
              behind ProtectedRoute. */}
          <Route
            path="/report/:type"
            element={
              <ProtectedRoute>
                <ReportForm />
              </ProtectedRoute>
            }
          />
          <Route
            path="/matches/:reportId"
            element={
              <ProtectedRoute>
                <Matches />
              </ProtectedRoute>
            }
          />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}