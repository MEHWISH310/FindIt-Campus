import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Header from './components/Header';
import NotificationToast from './components/NotificationToast';
import Landing from './pages/Landing';
import Dashboard from './pages/Dashboard';
import ReportForm from './pages/ReportForm';
import Matches from './pages/Matches';
import ClaimedItems from './pages/ClaimedItems';
import './styles/global.css';

export default function App() {
  return (
    <BrowserRouter>
      <Header />
      <NotificationToast />
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/lost" element={<Dashboard reportType="lost" />} />
        <Route path="/found" element={<Dashboard reportType="found" />} />
        <Route path="/report/:type" element={<ReportForm />} />
        <Route path="/matches/:reportId" element={<Matches />} />
        <Route path="/claimed" element={<ClaimedItems />} />
      </Routes>
    </BrowserRouter>
  );
}