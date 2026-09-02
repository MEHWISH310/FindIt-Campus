import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import ProtectedRoute from './components/ProtectedRoute';
import Header from './components/Header';
import ChatWidget from './components/ChatWidget';
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
        <ChatWidget /> 
        <Routes>
          {/* Public: only the auth pages themselves. Everything else --
              including the landing page -- requires login, so someone
              hitting "/" logged out is bounced straight to /login. */}
          <Route path="/login" element={<Login />} />
          <Route path="/request-access" element={<RequestAccess />} />
          <Route path="/forgot-password" element={<ForgotPassword />} />

          <Route
            path="/"
            element={
              <ProtectedRoute>
                <Landing />
              </ProtectedRoute>
            }
          />
          <Route
            path="/lost"
            element={
              <ProtectedRoute>
                <Dashboard reportType="lost" />
              </ProtectedRoute>
            }
          />
          <Route
            path="/found"
            element={
              <ProtectedRoute>
                <Dashboard reportType="found" />
              </ProtectedRoute>
            }
          />
          <Route
            path="/claimed"
            element={
              <ProtectedRoute>
                <ClaimedItems />
              </ProtectedRoute>
            }
          />
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