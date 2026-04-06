import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { useApp } from '../context/AppContext'

const nav = [
  { to: '/', label: '📊 Dashboard', exact: true },
  { to: '/process', label: '📤 Process Invoice' },
  { to: '/history', label: '📋 Invoice History' },
  { to: '/settings', label: '⚙️ Settings' },
]

const s = {
  shell: { display: 'flex', minHeight: '100vh' },
  sidebar: { width: 220, background: '#1e293b', color: '#e2e8f0', display: 'flex', flexDirection: 'column', padding: '24px 0' },
  logo: { padding: '0 20px 24px', borderBottom: '1px solid #334155', marginBottom: 16 },
  logoTitle: { fontSize: 15, fontWeight: 700, color: '#fff', letterSpacing: 1 },
  logoSub: { fontSize: 11, color: '#64748b', marginTop: 2 },
  link: { display: 'block', padding: '10px 20px', color: '#94a3b8', textDecoration: 'none', fontSize: 14, borderLeft: '3px solid transparent' },
  activeLink: { color: '#fff', background: '#0f172a', borderLeft: '3px solid #1a56db' },
  logout: { marginTop: 'auto', padding: '10px 20px', color: '#64748b', cursor: 'pointer', fontSize: 14, background: 'none', border: 'none', textAlign: 'left' },
  main: { flex: 1, background: '#f8fafc', overflowY: 'auto', display: 'flex', flexDirection: 'column' },
  banner: { background: '#1a56db', color: '#fff', padding: '8px 24px', fontSize: 13, display: 'flex', alignItems: 'center', gap: 8 },
  content: { padding: 32, flex: 1 },
}

export default function Layout() {
  const navigate = useNavigate()
  const { processingState } = useApp()
  const name = localStorage.getItem('userName') || 'User'

  function logout() {
    localStorage.clear()
    navigate('/login')
  }

  return (
    <div style={s.shell}>
      <aside style={s.sidebar}>
        <div style={s.logo}>
          <div style={s.logoTitle}>🧾 Invoice AI</div>
          <div style={s.logoSub}>Processing System</div>
          <div style={{ marginTop: 12, fontSize: 12, color: '#475569' }}>👤 {name}</div>
        </div>
        {nav.map(n => (
          <NavLink key={n.to} to={n.to} end={n.exact}
            style={({ isActive }) => ({ ...s.link, ...(isActive ? s.activeLink : {}) })}>
            {n.label}
            {n.to === '/process' && processingState.phase === 'processing' && (
              <span style={{ marginLeft: 8, fontSize: 10, background: '#f59e0b', color: '#fff', padding: '1px 6px', borderRadius: 10 }}>●</span>
            )}
          </NavLink>
        ))}
        <button style={s.logout} onClick={logout}>🚪 Logout</button>
      </aside>
      <main style={s.main}>
        {processingState.phase === 'processing' && (
          <div style={s.banner}>
            <span style={{ animation: 'spin 1s linear infinite', display: 'inline-block' }}>⚙️</span>
            Processing invoice in background — you can navigate freely
          </div>
        )}
        {processingState.phase === 'done' && (
          <div style={{ ...s.banner, background: '#16a34a' }}>
            ✅ Invoice processed — <NavLink to="/process" style={{ color: '#fff', marginLeft: 4 }}>Review & Approve →</NavLink>
          </div>
        )}
        <div style={s.content}>
          <Outlet />
        </div>
      </main>
    </div>
  )
}
