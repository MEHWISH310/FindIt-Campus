import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Header from './components/Header';
import Landing from './pages/Landing';
import Dashboard from './pages/Dashboard';
import ReportForm from './pages/ReportForm';
import Matches from './pages/Matches';
import './styles/global.css';

export default function App() {
  return (
    <BrowserRouter>
      <Header />
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/lost" element={<Dashboard reportType="lost" />} />
        <Route path="/found" element={<Dashboard reportType="found" />} />
        <Route path="/report/:type" element={<ReportForm />} />
        <Route path="/matches/:reportId" element={<Matches />} />
      </Routes>
    </BrowserRouter>
  );
}