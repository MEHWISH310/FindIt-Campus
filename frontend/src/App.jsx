import { BrowserRouter, Routes, Route, Link } from 'react-router-dom'

// Placeholder pages -- replace with real components in src/pages/ as you build them.
function Home() {
  return (
    <div style={{ padding: '2rem' }}>
      <h1>FindIt Campus</h1>
      <p>Report a lost or found item, or check for matches.</p>
      <nav>
        <Link to="/report/lost">Report Lost Item</Link> |{' '}
        <Link to="/report/found">Report Found Item</Link>
      </nav>
    </div>
  )
}

function ReportLost() {
  return <div style={{ padding: '2rem' }}>TODO: Lost item report form (see src/pages/)</div>
}

function ReportFound() {
  return <div style={{ padding: '2rem' }}>TODO: Found item report form (see src/pages/)</div>
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/report/lost" element={<ReportLost />} />
        <Route path="/report/found" element={<ReportFound />} />
      </Routes>
    </BrowserRouter>
  )
}