import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { login, register } from '../api'

const s = {
  page: { minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#f8fafc' },
  card: { background: '#fff', borderRadius: 12, padding: 40, width: 380, boxShadow: '0 4px 24px rgba(0,0,0,0.08)', border: '1px solid #e2e8f0' },
  title: { fontSize: 22, fontWeight: 700, color: '#1a56db', marginBottom: 4 },
  sub: { fontSize: 13, color: '#64748b', marginBottom: 28 },
  label: { display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 6 },
  input: { width: '100%', padding: '10px 12px', border: '1px solid #d1d5db', borderRadius: 8, fontSize: 14, outline: 'none', marginBottom: 16 },
  btn: { width: '100%', padding: '11px', background: '#1a56db', color: '#fff', border: 'none', borderRadius: 8, fontSize: 14, fontWeight: 600, cursor: 'pointer', marginBottom: 12 },
  toggle: { textAlign: 'center', fontSize: 13, color: '#64748b' },
  toggleLink: { color: '#1a56db', cursor: 'pointer', fontWeight: 600 },
  error: { background: '#fef2f2', color: '#dc2626', padding: '10px 12px', borderRadius: 8, fontSize: 13, marginBottom: 16 },
}

export default function Login() {
  const [mode, setMode] = useState('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  async function submit(e) {
    e.preventDefault()
    setError(''); setLoading(true)
    try {
      if (mode === 'login') {
        const data = await login(email, password)
        localStorage.setItem('token', data.access_token)
        localStorage.setItem('userName', data.name)
        navigate('/')
      } else {
        await register(email, password, name)
        setMode('login')
        setError('')
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={s.page}>
      <div style={s.card}>
        <div style={s.title}>🧾 Invoice AI</div>
        <div style={s.sub}>{mode === 'login' ? 'Sign in to your account' : 'Create a new account'}</div>
        {error && <div style={s.error}>{error}</div>}
        <form onSubmit={submit}>
          {mode === 'register' && (
            <>
              <label style={s.label}>Full Name</label>
              <input style={s.input} value={name} onChange={e => setName(e.target.value)} placeholder="Your name" required />
            </>
          )}
          <label style={s.label}>Email</label>
          <input style={s.input} type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="you@company.com" required />
          <label style={s.label}>Password</label>
          <input style={s.input} type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="••••••••" required />
          <button style={s.btn} type="submit" disabled={loading}>
            {loading ? 'Please wait...' : mode === 'login' ? 'Sign In' : 'Create Account'}
          </button>
        </form>
        <div style={s.toggle}>
          {mode === 'login' ? "Don't have an account? " : 'Already have an account? '}
          <span style={s.toggleLink} onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError('') }}>
            {mode === 'login' ? 'Register' : 'Sign In'}
          </span>
        </div>
      </div>
    </div>
  )
}
