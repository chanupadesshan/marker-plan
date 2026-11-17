import React, { useState } from 'react';
import { AlertTriangle, ReceiptText, ScanText, Scissors } from 'lucide-react';
import { authApi, authToken } from './api.js';

/**
 * Purpose: Check the sign-in form before it is sent.
 * Input: form - { email, password }.
 * Output: an object of messages keyed by field name; empty when the form is fine.
 */
export function validateAuthForm(form) {
  const errors = {};
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(form.email.trim())) errors.email = 'Enter a valid email address';
  if (!form.password) errors.password = 'Enter your password';
  return errors;
}

/**
 * Purpose: The sign-in page, shown until a person is signed in. Accounts are created by an admin, so there is
 * no register form. On success the token is saved and the app is told who signed in.
 * Input: onSignedIn - called with the user once the server accepts the form.
 * Output: the page.
 */
export default function AuthPage({ onSignedIn }) {
  const [form, setForm] = useState({ email: '', password: '' });
  const [errors, setErrors] = useState({});
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  /** Purpose: Keep one form field up to date and clear its message. Input: key - field name. Output: a change handler. */
  const field = key => event => {
    setForm(previous => ({ ...previous, [key]: event.target.value }));
    setErrors(previous => ({ ...previous, [key]: undefined }));
  };

  /**
   * Purpose: Validate and send the form; on success save the token and enter the app.
   * Input: event - the form submit.
   * Output: a promise that finishes when the server has answered; a refusal is shown above the button.
   */
  async function submit(event) {
    event.preventDefault();
    const found = validateAuthForm(form);
    setErrors(found); setError('');
    if (Object.keys(found).length) return;
    setBusy(true);
    try {
      const { token, user } = await authApi.login(form);
      authToken.set(token);
      onSignedIn(user);
    } catch (e) { setError(e.message); setBusy(false); }
  }

  /** Purpose: One labelled input with its message. Input: key, label, type, autoComplete. Output: the markup. */
  const input = (key, label, type, autoComplete) => <div className="field">
    <label htmlFor={`login-${key}`}>{label}</label>
    <input id={`login-${key}`} type={type} value={form[key]} onChange={field(key)} autoComplete={autoComplete} disabled={busy}
      aria-invalid={!!errors[key]} aria-describedby={errors[key] ? `auth-${key}-error` : undefined} />
    {errors[key] && <small id={`auth-${key}-error`} className="auth-field-error">{errors[key]}</small>}
  </div>;

  return <div id="loginScreen">
    <aside className="login-hero">
      <div className="brand"><span className="brand-mark brand-logo" aria-hidden="true"><img src="/guston-logo.png" alt=""/></span><strong className="brand-name">Marker Plan</strong></div>
      <div className="login-hero-content">
        <h2>From Tech Pack to <span>cutting plan,</span> faster.</h2>
        <p>Read Tech Packs and purchase orders, check the numbers against the source PDF, and build marker plans in one place.</p>
      </div>
      <div className="feature-list">
        <div className="feature"><span className="feature-icon">◈</span>Extract Wovens and Knits materials from Tech Pack PDFs</div>
        <div className="feature"><span className="feature-icon">▤</span>Turn purchase orders into size and quantity tables</div>
        <div className="feature"><span className="feature-icon">✂</span>Generate cutting plans for the materials you choose</div>
      </div>
      <div className="login-hero-art" aria-hidden="true">
        <span className="login-orb login-orb-ring"/>
        <span className="login-orb login-orb-main"/>
        <span className="login-orb login-orb-small"/>
      </div>
    </aside>
    <div className="login-panel">
      <form className="login-card" onSubmit={submit} noValidate>
        <h1>Welcome back</h1>
        <p className="auth-lead">Sign in to continue to your workspace.</p>
        {error && <div className="alert error" role="alert"><AlertTriangle size={18}/><span>{error}</span></div>}
        {input('email', 'Email', 'email', 'email')}
        {input('password', 'Password', 'password', 'current-password')}
        <button className="btn btn-primary btn-block" type="submit" disabled={busy}><span>{busy ? 'Please wait…' : 'Sign in'}</span> <span aria-hidden="true">→</span></button>
        <div className="login-help">Need an account? Ask an administrator to create one for you.</div>
      </form>
    </div>
  </div>;
}
