import axios from 'axios'

// Points to your local FastAPI backend (uvicorn app.main:app --port 8000)
const api = axios.create({
  baseURL: 'http://127.0.0.1:8000',
})

export const createReport = (payload) => api.post('/reports/', payload)
export const listReports = (reportType) =>
  api.get('/reports/', { params: reportType ? { report_type: reportType } : {} })
export const getReport = (id) => api.get(`/reports/${id}`)
export const findMatches = (reportId) => api.post(`/matches/find/${reportId}`)

export default api