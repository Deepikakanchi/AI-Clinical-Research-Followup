/*
 * pages/LoginPage.jsx - The single login page for all staff.
 * Email + password -> POST /api/auth/login -> redirect to the backend's home_path
 * (coordinator dashboard or reviewer queue).
 */
import { useState } from 'react';
import { Navigate } from 'react-router-dom';
import { Activity, ArrowRight, FlaskConical, Loader2, ShieldCheck } from 'lucide-react';
import { api } from '@/api/client';
import { useAuth } from '@/components/common/AuthContext';
import { ErrorBanner, Field } from '@/components/common/ui';
import { Footer } from '@/components/common/Layout';

export default function LoginPage() {
  const { user, ready, signIn } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  if (!ready) return <div className="page-loading">Loading…</div>;
  if (user) return <Navigate to={user.home_path} replace />;

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      signIn(await api.login(email.trim(), password));
    } catch (err) {
      setError(err);
      setPassword('');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-page">
      <div className="login-top">
        <span className="brand">
          <span className="brand-mark"><Activity size={23} /></span>
          <div>Clinical Research<span>FOLLOW-UP PORTAL</span></div>
        </span>
        <span className="login-project">EY CAPSTONE PROJECT</span>
      </div>

      <div className="login-main">
        <section className="login-visual" aria-hidden="true">
          <div className="login-visual-copy">
            <span className="eyebrow">PRECISION. CONTINUITY. CARE.</span>
            <h1>Clinical Research<br />Follow-up Portal</h1>
            <p>Every visit documented.<br />Every draft human-reviewed.</p>
            <span><ShieldCheck size={16} /> Built for responsible research coordination</span>
          </div>
        </section>

        <section className="login-form-section">
          <span className="login-icon"><FlaskConical size={26} /></span>
          <span className="eyebrow">STAFF WORKSPACE</span>
          <h2>Welcome back.</h2>
          <p>Sign in to your study workspace.</p>

          <form onSubmit={submit} noValidate={false}>
            <Field label="Email" name="email" error={error}>
              <input type="email" required autoComplete="username" placeholder="you@example.org"
                value={email} onChange={e => setEmail(e.target.value)} />
            </Field>
            <Field label="Password" name="password" error={error}>
              <input type={showPassword ? 'text' : 'password'} required autoComplete="current-password"
                placeholder="Enter your password" value={password} onChange={e => setPassword(e.target.value)} />
            </Field>
            <label className="check-label">
              <input type="checkbox" checked={showPassword} onChange={e => setShowPassword(e.target.checked)} />
              Show password
            </label>

            <ErrorBanner error={error} />

            <button type="submit" className="btn btn-block" disabled={busy}>
              {busy ? <Loader2 className="spin" /> : null}
              {busy ? 'Signing in…' : 'Sign in'}
              {!busy && <ArrowRight size={17} />}
            </button>
            <small className="login-note">Demo login for fictional staff only.</small>
          </form>
        </section>
      </div>
      <Footer />
    </div>
  );
}