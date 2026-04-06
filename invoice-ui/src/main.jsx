import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AppProvider } from './context/AppContext'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import ProcessInvoice from './pages/ProcessInvoice'
import InvoiceHistory from './pages/InvoiceHistory'
import Settings from './pages/Settings'
import Layout from './components/Layout'

function PrivateRoute({ children }) {
  return localStorage.getItem('token') ? children : <Navigate to="/login" />
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <BrowserRouter>
    <AppProvider>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/" element={<PrivateRoute><Layout /></PrivateRoute>}>
          <Route index element={<Dashboard />} />
          <Route path="process" element={<ProcessInvoice />} />
          <Route path="history" element={<InvoiceHistory />} />
          <Route path="settings" element={<Settings />} />
        </Route>
      </Routes>
    </AppProvider>
  </BrowserRouter>
)
