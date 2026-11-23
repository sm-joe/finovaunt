import { FormEvent, useCallback, useEffect, useState } from "react";
import App from "./App";
import "./access.css";

type Session = { authenticated: boolean; username?: string; must_change_password?: boolean };
type CloudAccount = { id: string; name: string; provider: string; account_id: string; role_arn: string; region: string; status: string; created_at: string };
type BillingScan = { id: string; account_id: string; scanned_at: string; period_start: string; period_end_exclusive: string; total_cost: number; currency: string; services: { service: string; amount: number; currency: string }[]; status: string };

async function api<T>(path: string, body?: Record<string, unknown>): Promise<T> {
  const response = await fetch(path, { method: body ? "POST" : "GET", credentials: "same-origin", headers: { Accept: "application/json", ...(body ? { "Content-Type": "application/json" } : {}) }, ...(body ? { body: JSON.stringify(body) } : {}) });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof payload.message === "string" ? payload.message : `Request failed (${response.status})`);
  return payload as T;
}

export default function AccessGate() {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [accounts, setAccounts] = useState<CloudAccount[]>([]);
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [name, setName] = useState("");
  const [accountId, setAccountId] = useState("");
  const [roleArn, setRoleArn] = useState("");
  const [region, setRegion] = useState("us-east-1");
  const [externalId, setExternalId] = useState("");
  const [scanExternalIds, setScanExternalIds] = useState<Record<string, string>>({});
  const [scanning, setScanning] = useState("");
  const [latestScan, setLatestScan] = useState<BillingScan | null>(null);
  const [editing, setEditing] = useState<CloudAccount | null>(null);
  const [editReason, setEditReason] = useState("");
  const [accountMessage, setAccountMessage] = useState("");

  const refreshSession = useCallback(async () => {
    try {
      const result = await api<Session>("/api/auth/session");
      setSession(result.authenticated ? result : null);
    } catch { setSession(null); }
    finally { setLoading(false); }
  }, []);
  const refreshAccounts = useCallback(async () => {
    try { const result = await api<{ items: CloudAccount[] }>("/api/cloud-accounts"); setAccounts(result.items); }
    catch (e) { setError(e instanceof Error ? e.message : "Could not load cloud accounts."); }
  }, []);
  useEffect(() => { void refreshSession(); }, [refreshSession]);
  useEffect(() => { if (session?.authenticated && !session.must_change_password) void refreshAccounts(); }, [session, refreshAccounts]);

  async function submitLogin(event: FormEvent) {
    event.preventDefault(); setError("");
    try { const result = await api<Session>("/api/auth/login", { username, password }); setSession({ ...result, authenticated: true }); setPassword(""); }
    catch (e) { setError(e instanceof Error ? e.message : "Login failed."); }
  }
  async function submitPassword(event: FormEvent) {
    event.preventDefault(); setError("");
    try { await api("/api/auth/password", { current_password: currentPassword, new_password: newPassword }); setSession((s) => s ? { ...s, must_change_password: false } : s); setCurrentPassword(""); setNewPassword(""); }
    catch (e) { setError(e instanceof Error ? e.message : "Password change failed."); }
  }
  async function addAccount(event: FormEvent) {
    event.preventDefault(); setError("");
    try {
      const created = await api<CloudAccount>("/api/cloud-accounts", { name, provider: "aws", account_id: accountId, role_arn: roleArn, region, external_id: externalId });
      setScanExternalIds((previous) => ({ ...previous, [created.account_id]: externalId }));
      setName(""); setAccountId(""); setRoleArn(""); setExternalId(""); setShowOnboarding(false); await refreshAccounts();
    } catch (e) { setError(e instanceof Error ? e.message : "Account onboarding failed."); }
  }
  async function saveAccountChanges(event: FormEvent) {
    event.preventDefault();
    if (!editing) return;
    setError(""); setAccountMessage("");
    try {
      await api("/api/cloud-accounts/" + encodeURIComponent(editing.account_id) + "/configuration", {
        name: editing.name, region: editing.region, role_arn: editing.role_arn, reason: editReason.trim(),
      });
      setEditing(null); setEditReason("");
      setLatestScan(null);
      setAccountMessage("Collector configuration updated. Previous scans are retained as history. Collect fresh data for the new configuration.");
      await refreshAccounts();
    } catch (e) { setError(e instanceof Error ? e.message : "Collector configuration could not be updated."); }
  }
  async function runBillingScan(id: string) {
    setError(""); setScanning(id); setLatestScan(null);
    try { const result = await api<BillingScan>("/api/billing-scans", { account_id: id, external_id: scanExternalIds[id] || "" }); setLatestScan(result); }
    catch (e) { setError(e instanceof Error ? e.message : "Billing scan failed."); }
    finally { setScanning(""); }
  }
  async function logout() {
    try { await api("/api/auth/logout", {}); } catch { /* clear local UI even if session expired */ }
    setSession(null); setAccounts([]); setLatestScan(null);
  }

  if (loading) return <div className="access-screen"><div className="access-card">Loading Finovaunt…</div></div>;
  if (!session?.authenticated) return <div className="access-screen"><form className="access-card" onSubmit={submitLogin}>
    <div className="access-brand"><span>F</span><div><strong>finovaunt</strong><small>Autonomous FinOps</small></div></div>
    <h1>Sign in</h1><p>Sign in to access your cloud cost intelligence workspace.</p>
    {error && <div className="access-error" role="alert">{error}</div>}
    <label>Username<input autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required /></label>
    <label>Password<input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
    <button className="access-primary" type="submit">Sign in</button>
    <small className="access-hint">Initial username: admin. Use the administrator bootstrap password set during deployment.</small>
  </form></div>;

  if (session.must_change_password) return <div className="access-screen"><form className="access-card" onSubmit={submitPassword}>
    <div className="access-brand"><span>F</span><div><strong>finovaunt</strong><small>Account security</small></div></div>
    <h1>Change your password</h1><p>A new password is required before accessing the dashboard.</p>
    {error && <div className="access-error" role="alert">{error}</div>}
    <label>Current password<input type="password" autoComplete="current-password" value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} required /></label>
    <label>New password<input type="password" autoComplete="new-password" minLength={12} value={newPassword} onChange={(e) => setNewPassword(e.target.value)} required /><small>Use at least 12 characters.</small></label>
    <button className="access-primary" type="submit">Update password</button>
  </form></div>;

  return <div className="access-workspace"><div className="access-toolbar"><div><strong>Cloud account onboarding</strong><span>Connect AWS billing with a read-only IAM role.</span></div><div><button onClick={() => setShowOnboarding((v) => !v)}>{showOnboarding ? "Close form" : "Add cloud account"}</button><button className="access-logout" onClick={() => void logout()}>Sign out</button></div></div>
    {error && <div className="access-error access-inline-error" role="alert">{error}<button onClick={() => setError("")}>Dismiss</button></div>}
    {accountMessage && <p role="status">{accountMessage}</p>}
    {showOnboarding && <form className="access-onboard" onSubmit={addAccount}><h2>Onboard AWS account</h2><p>Use an IAM role configured for cross-account access. Finovaunt requests Cost Explorer billing data only.</p>
      <div className="access-fields"><label>Account display name<input value={name} onChange={(e) => setName(e.target.value)} required placeholder="Production AWS" /></label><label>AWS account ID<input value={accountId} onChange={(e) => setAccountId(e.target.value)} required inputMode="numeric" pattern="[0-9]{12}" placeholder="123456789012" /></label><label>IAM role ARN<input value={roleArn} onChange={(e) => setRoleArn(e.target.value)} required placeholder="arn:aws:iam::123456789012:role/FinovauntBillingReadOnly" /></label><label>AWS region<input value={region} onChange={(e) => setRegion(e.target.value)} required placeholder="us-east-1" /></label><label className="access-wide">External ID (if required)<input value={externalId} onChange={(e) => setExternalId(e.target.value)} placeholder="Optional; enter again when scanning if needed" /></label></div>
      <button className="access-primary" type="submit">Save account</button><small>Account metadata is stored locally. External ID is not persisted.</small>
    </form>}
    <section className="access-account-panel"><h2>Connected cloud accounts <span>{accounts.length}</span></h2>{accounts.length === 0 ? <p>No cloud accounts onboarded yet. Add an AWS account to run a billing scan.</p> : accounts.map((account) => <div className="access-account" key={account.id}><div><strong>{account.name}</strong><small>{account.account_id} · {account.region}</small><small>{account.role_arn}</small><input aria-label={`External ID for ${account.name}`} value={scanExternalIds[account.account_id] || ""} onChange={(e) => setScanExternalIds((previous) => ({ ...previous, [account.account_id]: e.target.value }))} placeholder="External ID (only if required)" /></div><div><button type="button" onClick={() => { setEditing({ ...account }); setEditReason(""); setAccountMessage(""); }}>Edit Collector</button><button disabled={!!scanning} onClick={() => void runBillingScan(account.account_id)}>{scanning === account.account_id ? "Scanning…" : "Scan billing"}</button></div></div>)}</section>
    {editing && <form className="access-onboard" onSubmit={(event) => void saveAccountChanges(event)}>
      <h2>Edit AWS Collector · {editing.account_id}</h2>
      <p>Update the role or region without deleting collected history. A changed collector scope requires a fresh scan before current dashboard evidence can be displayed.</p>
      <div className="access-fields">
        <label>Display Name<input required maxLength={120} value={editing.name} onChange={e => setEditing(v => v ? {...v, name:e.target.value} : v)}/></label>
        <label>IAM Role ARN<input required value={editing.role_arn} onChange={e => setEditing(v => v ? {...v, role_arn:e.target.value} : v)}/></label>
        <label>AWS Region<input required value={editing.region} onChange={e => setEditing(v => v ? {...v, region:e.target.value} : v)}/></label>
        <label className="access-wide">Reason For Change<textarea required minLength={10} maxLength={2000} value={editReason} onChange={e => setEditReason(e.target.value)} placeholder="Explain the role or region change for the local audit log."/></label>
      </div>
      <button className="access-primary" type="submit">Save Collector Configuration</button>
      <button type="button" onClick={() => setEditing(null)}>Cancel</button>
    </form>}
    {latestScan && <section className="access-account-panel"><h2>Billing scan result</h2><p>{latestScan.period_start} to {latestScan.period_end_exclusive} · {new Date(latestScan.scanned_at).toLocaleString()}</p><div className="access-total">{new Intl.NumberFormat("en-US", { style: "currency", currency: latestScan.currency || "USD" }).format(latestScan.total_cost)} <small>month-to-date service costs</small></div><div className="access-services">{latestScan.services.map((service) => <div key={service.service}><span>{service.service}</span><strong>{new Intl.NumberFormat("en-US", { style: "currency", currency: service.currency || "USD" }).format(service.amount)}</strong></div>)}</div></section>}
    <div className="access-dashboard"><div className="access-dashboard-heading"><strong>Cost intelligence dashboard</strong><span>Existing dashboard below is unchanged.</span></div><App onOpenCloud={() => setShowOnboarding(true)} /></div>
  </div>;
}
