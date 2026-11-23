import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Cloud, LogOut, UserRound, ShieldCheck, ArrowLeft, RefreshCw, Layers3, Home, Settings2, Eye, EyeOff, LockKeyhole, ArrowRight, Server, ChartNoAxesCombined, CircleCheck, KeyRound, Database, Plus, Pencil, Trash2, HardDrive, CircleHelp } from "lucide-react";
import App from "./App";
import "./auth.css";
import "./auth-enterprise.css";

type Session = { authenticated: boolean; username?: string; must_change_password?: boolean };
type CloudAccount = { id: string; name: string; provider: string; account_id: string; role_arn: string; region: string; status: string; created_at: string };
type InventoryAsset = { id: string; type: string; name: string; state: string; size: string; region: string; recommendation: string };
type InventoryScan = { id: string; account_id: string; scanned_at: string; status: string; asset_count: number; truncated: boolean; assets: InventoryAsset[] };
type BillingScan = { id: string; scanned_at: string; period_start: string; period_end_exclusive: string; total_cost: number; currency: string; services: { service: string; amount: number; currency: string }[]; status: string };
type View = "dashboard" | "profile" | "cloud";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { credentials: "same-origin", headers: { Accept: "application/json", ...(init?.body ? { "Content-Type": "application/json" } : {}), ...init?.headers }, ...init });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof payload.message === "string" ? payload.message : `Request failed (${response.status})`);
  return payload as T;
}

export default function AuthenticatedShell() {
  const [session, setSession] = useState<Session | null>(null);
  const [checking, setChecking] = useState(true);
  const [view, setView] = useState<View>("dashboard");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [signedOut, setSignedOut] = useState(false);

  const loadSession = useCallback(async () => {
    setChecking(true);
    try { setSession(await request<Session>("/api/auth/session")); }
    catch { setSession({ authenticated: false }); }
    finally { setChecking(false); }
  }, []);
  useEffect(() => { void loadSession(); }, [loadSession]);

  async function login(username: string, password: string) {
    setBusy(true);
    setError("");
    try {
      const response = await request<Session>("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      if (!response.authenticated) {
        throw new Error("The server did not confirm authentication.");
      }
      // A successful POST is insufficient if the browser drops Set-Cookie.
      // Verify the actual cookie-backed session before entering the app.
      const confirmed = await request<Session>("/api/auth/session");
      if (!confirmed.authenticated) {
        throw new Error(
          "Your password was accepted, but the session cookie was not retained. " +
          "Use the same dashboard address for login and browsing, allow site cookies, " +
          "and use HTTPS if FINOVAUNT_SECURE_COOKIES is enabled."
        );
      }
      setSession(confirmed);
      setSignedOut(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Login failed.");
    } finally {
      setBusy(false);
    }
  }
  async function logout() {
    setBusy(true); setError("");
    try { await request("/api/auth/logout", { method: "POST", body: "{}" }); setSession({ authenticated: false }); setView("dashboard"); setSignedOut(true); }
    catch (e) { setError(e instanceof Error ? e.message : "Sign out failed."); }
    finally { setBusy(false); }
  }

  if (checking) return <div className="fin-auth-loading fin-loading-new"><div className="fin-auth-mark"><Layers3 size={23}/></div><strong>Finovaunt</strong><span>Restoring your secure session…</span></div>;
  if (!session?.authenticated) return <LoginScreen onLogin={login} busy={busy} error={error} signedOut={signedOut}/>;
  if (session.must_change_password) return <PasswordScreen onDone={loadSession} busy={busy} setBusy={setBusy}/>;

  const current = view==="cloud"?"Cloud Accounts":"Settings & Profile";
  return <>
    {view==="dashboard" ? <div className="fin-dashboard-content"><App
      onOpenCloud={()=>setView("cloud")} onOpenProfile={()=>setView("profile")}
      onSignOut={()=>void logout()} username={session.username || "admin"}/></div> :
    <div className="fv-shell fv-account-shell">
      <aside className="sidebar fv-sidebar">
        <div className="brand fv-brand"><div className="brand-symbol fv-logo"><Layers3 size={23}/></div><div><strong>Finovaunt</strong><span>AWS FinOps Platform</span></div></div>
        <nav className="nav-list fv-nav" aria-label="Workspace navigation">
          <span className="fv-nav-label">WORKSPACE</span>
          <button type="button" className="nav-item" onClick={()=>setView("dashboard")}><Home size={18}/><span>Overview</span></button>
          <button type="button" className="nav-item" onClick={()=>setView("dashboard")}><ChartNoAxesCombined size={18}/><span>FinOps Dashboard</span></button>
          <span className="fv-nav-label fv-nav-label-secondary">ACCOUNT</span>
          <button type="button" className={"nav-item "+(view==="cloud"?"active":"")} aria-current={view==="cloud"?"page":undefined} onClick={()=>setView("cloud")}><Cloud size={18}/><span>Cloud Accounts</span></button>
          <button type="button" className={"nav-item "+(view==="profile"?"active":"")} aria-current={view==="profile"?"page":undefined} onClick={()=>setView("profile")}><Settings2 size={18}/><span>Settings & Profile</span></button>
        </nav>
        <div className="sidebar-bottom fv-sidebar-bottom"><div className="fv-workload-box"><span className="fv-workload-mark">aws</span><div><strong>AWS Only</strong><small>Read-only collector</small></div><ShieldCheck size={17}/></div><span className="version">FINOVAUNT · COST INTELLIGENCE</span></div>
      </aside>
      <main className="main fv-main">
        <header className="topbar fv-topbar fv-account-topbar">
          <div className="fv-account-breadcrumb"><span>Finovaunt</span><span>/</span><strong>{current}</strong></div>
          <div className="fv-toolbar-right"><span className="fv-readonly"><ShieldCheck size={15}/> Read-only AWS access</span>
            <button type="button" className="fv-avatar-button" title="Profile" onClick={()=>setView("profile")}><span className="fv-avatar">{(session.username || "AD").slice(0,2).toUpperCase()}</span><UserRound size={14}/></button>
            <button type="button" className="fv-icon-action" aria-label="Sign out" title="Sign out" disabled={busy} onClick={()=>void logout()}><LogOut size={17}/></button>
          </div>
        </header>
        <div className="fv-page fv-account-page">
          <section className="fv-page-heading">
            <div><span className="fv-page-kicker">ACCOUNT MANAGEMENT</span><h1>{current} <span className="fv-aws-tag">AWS</span></h1><p>{view==="cloud"?"Manage AWS connections and read-only collector evidence.":"Manage your Finovaunt administrator credentials and account security."}</p></div>
            <button type="button" className="fv-outline-button" onClick={()=>setView("dashboard")}><ArrowLeft size={16}/> Back To Dashboard</button>
          </section>
          {view==="profile"?<ProfileView username={session.username || "admin"} onPasswordChanged={loadSession}/>:<CloudView/>}
        </div>
      </main>
    </div>}
    {error && view!=="dashboard" && <div className="fin-toast" role="alert">{error}<button type="button" onClick={()=>setError("")}>Dismiss</button></div>}
  </>;
}

function LoginScreen({ onLogin, busy, error }: { onLogin: (u: string, p: string) => Promise<void>; busy: boolean; error: string }) {
  const [username, setUsername] = useState("admin"); const [password, setPassword] = useState("");
  function submit(e: FormEvent) { e.preventDefault(); void onLogin(username, password); }
  return <div className="fin-auth-page"><section className="fin-auth-card"><div className="fin-auth-mark"><ShieldCheck size={23}/></div><span className="fin-auth-kicker">AUTONOMOUS FINOPS</span><h1>Welcome to Finovaunt</h1><p>Sign in to your cloud cost intelligence workspace.</p><form onSubmit={submit}><label>Username<input autoComplete="username" value={username} onChange={e=>setUsername(e.target.value)} required/></label><label>Password<input type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} required/></label>{error && <div className="fin-form-error" role="alert">{error}</div>}<button className="fin-primary" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button></form><small>First login: username <code>admin</code> and the bootstrap password configured by the administrator.</small></section></div>;
}

function PasswordScreen({ onDone, busy, setBusy }: { onDone: () => Promise<void>; busy: boolean; setBusy: (v: boolean) => void }) {
  const [current, setCurrent] = useState(""); const [next, setNext] = useState(""); const [confirm, setConfirm] = useState(""); const [error, setError] = useState("");
  async function submit(e: FormEvent) { e.preventDefault(); setError(""); if (next.length < 12) { setError("Use at least 12 characters for your new password."); return; } if (next !== confirm) { setError("The new passwords do not match."); return; } setBusy(true); try { await request("/api/auth/password", { method: "POST", body: JSON.stringify({ current_password: current, new_password: next }) }); await onDone(); } catch (err) { setError(err instanceof Error ? err.message : "Password change failed."); } finally { setBusy(false); } }
  return <div className="fin-auth-page"><section className="fin-auth-card"><div className="fin-auth-mark"><ShieldCheck size={23}/></div><span className="fin-auth-kicker">ACCOUNT SECURITY</span><h1>Change your password</h1><p>Before continuing, replace your initial password with a secure password of at least 12 characters. You will remain signed in after the change.</p><form onSubmit={submit}><label>Current password<input type="password" autoComplete="current-password" value={current} onChange={e=>setCurrent(e.target.value)} required/></label><label>New password<input type="password" autoComplete="new-password" minLength={12} value={next} onChange={e=>setNext(e.target.value)} required/></label><label>Confirm new password<input type="password" autoComplete="new-password" minLength={12} value={confirm} onChange={e=>setConfirm(e.target.value)} required/></label>{error && <div className="fin-form-error" role="alert">{error}</div>}<button className="fin-primary" disabled={busy}>{busy ? "Saving…" : "Change password"}</button></form></section></div>;
}

function ProfileView({ username, onPasswordChanged }: { username: string; onPasswordChanged: () => Promise<void> }) {
  const [current, setCurrent] = useState(""); const [next, setNext] = useState(""); const [confirm, setConfirm] = useState(""); const [message, setMessage] = useState(""); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent) { e.preventDefault(); setError(""); setMessage(""); if (next.length < 12) { setError("New password must contain at least 12 characters."); return; } if (next !== confirm) { setError("The new passwords do not match."); return; } setBusy(true); try { await request("/api/auth/password", { method: "POST", body: JSON.stringify({ current_password: current, new_password: next }) }); setMessage("Password updated successfully."); setCurrent(""); setNext(""); setConfirm(""); await onPasswordChanged(); } catch (e) { setError(e instanceof Error ? e.message : "Password update failed."); } finally { setBusy(false); } }
  return <section className="fin-settings-card"><span className="fin-auth-kicker">ACCOUNT SETTINGS</span><h1>Profile settings</h1><p>Manage your Finovaunt sign-in credentials.</p><div className="fin-profile-row"><span>Username</span><strong>{username}</strong></div><form onSubmit={submit} className="fin-settings-form"><h2>Change password</h2><label>Current password<input type="password" autoComplete="current-password" value={current} onChange={e=>setCurrent(e.target.value)} required/></label><label>New password<input type="password" autoComplete="new-password" minLength={12} value={next} onChange={e=>setNext(e.target.value)} required/></label><label>Confirm new password<input type="password" autoComplete="new-password" minLength={12} value={confirm} onChange={e=>setConfirm(e.target.value)} required/></label>{error && <div className="fin-form-error">{error}</div>}{message && <div className="fin-form-success">{message}</div>}<button className="fin-primary" disabled={busy}>{busy ? "Saving…" : "Update password"}</button></form></section>;
}

function CloudView() {
  const [accounts, setAccounts] = useState<CloudAccount[]>([]); const [selected, setSelected] = useState(""); const [history, setHistory] = useState<BillingScan[]>([]); const [busy, setBusy] = useState(false); const [error, setError] = useState(""); const [message, setMessage] = useState("");
  const [inventory, setInventory] = useState<InventoryScan | null>(null);
  const [name, setName] = useState(""); const [accountId, setAccountId] = useState(""); const [roleArn, setRoleArn] = useState(""); const [region, setRegion] = useState("us-east-1"); const [externalId, setExternalId] = useState("");
  const refresh = useCallback(async () => { try { const data = await request<{items: CloudAccount[]}>("/api/cloud-accounts"); setAccounts(data.items); if (!selected && data.items.length) setSelected(data.items[0].account_id); } catch (e) { setError(e instanceof Error ? e.message : "Could not load cloud accounts."); } }, [selected]);
  const loadHistory = useCallback(async (id: string) => { if (!id) { setHistory([]); return; } try { const data = await request<{items: BillingScan[]}>(`/api/billing-scans/${encodeURIComponent(id)}`); setHistory([...data.items].reverse()); } catch (e) { setError(e instanceof Error ? e.message : "Could not load billing history."); } }, []);
  useEffect(() => { void refresh(); }, [refresh]); useEffect(() => { void loadHistory(selected); }, [selected, loadHistory]);
  const loadInventory = useCallback(async (id: string) => {
    if (!id) { setInventory(null); return; }
    try {
      const data = await request<{latest: InventoryScan | null}>(`/api/inventory-scans/${encodeURIComponent(id)}`);
      setInventory(data.latest);
    } catch (e) { setError(e instanceof Error ? e.message : "Could not load cloud inventory."); }
  }, []);
  useEffect(() => { void loadInventory(selected); }, [selected, loadInventory]);
  async function scanInventory() {
    if (!selected) return;
    setBusy(true); setError(""); setMessage("");
    try {
      const result = await request<InventoryScan>("/api/inventory-scans", {
        method: "POST",
        body: JSON.stringify({ account_id: selected, external_id: externalId }),
      });
      setInventory(result);
      setMessage(`Inventory complete: ${result.asset_count} assets. No AWS resources were modified.`);
    } catch (e) {
      // The reverse proxy may close a slow request after AWS inventory was
      // saved. Read the latest persisted snapshot before reporting a failure.
      try {
        const saved = await request<{ latest: InventoryScan | null }>(
          `/api/inventory-scans/${encodeURIComponent(selected)}`
        );
        if (saved.latest) {
          setInventory(saved.latest);
          setMessage(`Latest stored inventory: ${saved.latest.asset_count} assets. If the collection connection timed out, check the snapshot timestamp before retrying.`);
        } else {
          setError(e instanceof Error ? e.message : "Inventory scan failed.");
        }
      } catch {
        setError(e instanceof Error ? e.message : "Inventory scan failed.");
      }
    } finally { setBusy(false); }
  }
  async function onboard(e: FormEvent) { e.preventDefault(); setBusy(true); setError(""); setMessage(""); try { const created = await request<CloudAccount>("/api/cloud-accounts", { method: "POST", body: JSON.stringify({ name, provider: "aws", account_id: accountId, role_arn: roleArn, region, external_id: externalId }) }); setAccounts(old => [...old, created]); setSelected(created.account_id); setName(""); setAccountId(""); setRoleArn(""); setMessage("AWS account onboarded. Keep the external ID available if the role trust policy requires it for billing scans."); } catch (e) { setError(e instanceof Error ? e.message : "Account onboarding failed."); } finally { setBusy(false); } }
  async function scan() { if (!selected) return; setBusy(true); setError(""); setMessage(""); try { await request("/api/billing-scans", { method: "POST", body: JSON.stringify({ account_id: selected, external_id: externalId }) }); await loadHistory(selected); setMessage("Read-only billing scan completed."); } catch (e) { setError(e instanceof Error ? e.message : "Billing scan failed."); } finally { setBusy(false); } }
  async function removeSelectedAccount() {
    if (!selected || busy) return;
    const account = accounts.find(item => item.account_id === selected);
    if (!window.confirm(`Remove ${account?.name || selected} from Finovaunt? Its saved billing history will also be deleted. AWS resources will not be changed.`)) return;
    setBusy(true); setError(""); setMessage("");
    try {
      await request(`/api/cloud-accounts/${encodeURIComponent(selected)}`, { method: "DELETE" });
      const remaining = accounts.filter(item => item.account_id !== selected);
      setAccounts(remaining);
      setSelected(remaining[0]?.account_id || "");
      setHistory([]);
      setMessage("AWS account and locally saved billing history removed. AWS resources were not changed.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not remove cloud account.");
    } finally {
      setBusy(false);
    }
  }
  const latest = history[0];
  return <section className="fin-settings-card fin-cloud-card"><span className="fin-auth-kicker">CLOUD CONNECTIONS</span><h1>Cloud accounts & billing</h1><p>Onboard an AWS account and retrieve read-only Cost Explorer billing data.</p><div className="fin-cloud-grid"><form onSubmit={onboard} className="fin-settings-form"><h2><Cloud size={17}/> Onboard AWS account</h2><label>Account display name<input value={name} onChange={e=>setName(e.target.value)} required/></label><label>AWS account ID<input inputMode="numeric" pattern="[0-9]{12}" maxLength={12} value={accountId} onChange={e=>setAccountId(e.target.value)} placeholder="12-digit account ID" required/></label><label>IAM role ARN<input value={roleArn} onChange={e=>setRoleArn(e.target.value)} placeholder="arn:aws:iam::123456789012:role/FinovauntReadOnly" required/></label><label>Default region<select value={region} onChange={e=>setRegion(e.target.value)}>{["us-east-1","us-east-2","us-west-1","us-west-2","eu-central-1","eu-west-1","ap-south-1","ap-southeast-1"].map(r=><option key={r}>{r}</option>)}</select></label><label>External ID (optional)<input value={externalId} onChange={e=>setExternalId(e.target.value)} autoComplete="off"/></label><button className="fin-primary" disabled={busy}>{busy ? "Saving…" : "Add AWS account"}</button></form><div className="fin-account-panel"><h2>Onboarded accounts</h2>{accounts.length === 0 ? <p className="fin-muted">No cloud accounts have been onboarded.</p> : <><label>Select account<select value={selected} onChange={e=>setSelected(e.target.value)}>{accounts.map(a=><option key={a.account_id} value={a.account_id}>{a.name} · {a.account_id}</option>)}</select></label><div className="fin-profile-row"><span>Provider</span><strong>AWS</strong></div><div className="fin-profile-row"><span>Region</span><strong>{accounts.find(a=>a.account_id===selected)?.region || "—"}</strong></div><div className="fin-profile-row"><span>Status</span><strong>{accounts.find(a=>a.account_id===selected)?.status || "—"}</strong></div><button className="fin-primary" onClick={()=>void scan()} disabled={busy || !selected}><RefreshCw size={15}/> {busy ? "Scanning…" : "Run read-only billing scan"}</button><button type="button" className="fin-back" onClick={()=>void scanInventory()} disabled={busy || !selected}>Scan AWS Inventory</button><button type="button" className="fin-back" onClick={()=>void removeSelectedAccount()} disabled={busy || !selected}>Remove Account</button></>}<p className="fin-muted">Requires source AWS credentials that can assume the configured role, plus Cost Explorer read permissions.</p></div></div>{error && <div className="fin-form-error" role="alert">{error}</div>}{message && <div className="fin-form-success" role="status">{message}</div>}<div className="fin-billing-history"><h2>Latest inventory</h2>{!inventory ? <p className="fin-muted">Scan an onboarded AWS account to discover EC2, RDS and EBS resources.</p> : <><p className="fin-muted">{inventory.asset_count} assets · {inventory.status} · {new Date(inventory.scanned_at).toLocaleString()}{inventory.truncated ? " · Limited to configured cap" : ""}. No savings estimated.</p><div className="fin-service-list">{inventory.assets.map(asset=><div key={asset.type + asset.id}><span>{asset.name} · {asset.type.toUpperCase()} · {asset.region}</span><strong>{asset.state} · {asset.size}</strong></div>)}</div></>}</div><div className="fin-billing-history"><h2>Latest billing result</h2>{!latest ? <p className="fin-muted">No billing scans are available for this account yet.</p> : <><div className="fin-billing-total"><span>Month-to-date total</span><strong>{new Intl.NumberFormat("en-US", { style: "currency", currency: latest.currency || "USD" }).format(latest.total_cost || 0)}</strong><small>{latest.period_start} to {latest.period_end_exclusive} · {new Date(latest.scanned_at).toLocaleString()}</small></div><div className="fin-service-list">{latest.services.map(row=><div key={row.service}><span>{row.service}</span><strong>{new Intl.NumberFormat("en-US", { style: "currency", currency: row.currency || latest.currency || "USD" }).format(row.amount || 0)}</strong></div>)}</div></>}</div></section>;
}
