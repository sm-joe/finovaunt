import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { Activity, BarChart3, Boxes, Cloud, LogOut, ShieldCheck, RefreshCw, Layers3, Home, Settings2, Eye, EyeOff, ArrowRight, CircleCheck, KeyRound, Plus, Pencil, Trash2, HardDrive, CircleHelp, Zap } from "lucide-react";
import App, { type Tab } from "./App";
import "./auth-enterprise.css";

type Session = { authenticated: boolean; username?: string; must_change_password?: boolean };
type CloudAccount = { id: string; name: string; provider: string; account_id: string; role_arn: string; region: string; status: string; created_at: string; config_revision?: number };
type InventoryAsset = { id: string; type: string; name: string; state: string; size: string; region: string; recommendation: string };
type InventoryScan = { id: string; account_id: string; scanned_at: string; status: string; asset_count: number; truncated: boolean; config_revision?: number; assets: InventoryAsset[] };
type BillingScan = { id: string; scanned_at: string; period_start: string; period_end_exclusive: string; total_cost: number; currency: string; services: { service: string; amount: number; currency: string }[]; status: string; config_revision?: number };
type View = Tab | "profile" | "cloud";

const workspaceLinks = [
  ["Overview", Home, "Overview"],
  ["Cost Breakdown", BarChart3, "Cost Explorer"],
  ["Assets", Boxes, "Resources"],
  ["Review Candidates", Zap, "Recommendations"],
  ["AWS FinOps", Layers3, "Allocation & EKS"],
  ["Scan History", Activity, "Scan history"],
] as const;

const accountLinks = [
  ["cloud", Cloud, "AWS accounts"],
  ["profile", Settings2, "Admin settings"],
] as const;

function WorkspaceNavigation({ view, onNavigate }: { view: View; onNavigate: (view: View) => void }) {
  return <aside className="sidebar fv-sidebar">
    <div className="brand fv-brand">
      <div className="brand-symbol fv-logo"><Layers3 size={20}/></div>
      <div><strong>Finovaunt</strong><span>AWS FinOps</span></div>
    </div>
    <nav className="nav-list fv-nav" aria-label="Workspace navigation">
      {([["Workspace", workspaceLinks], ["Administration", accountLinks]] as const).map(([group, links]) =>
        <div className="fv-nav-group" key={group}>
          <span className="fv-nav-label">{group}</span>
          {links.map(([id, Icon, label]) =>
            <button type="button" key={id} className="nav-item" aria-current={view === id ? "page" : undefined}
              aria-label={label} title={label} onClick={() => onNavigate(id)}>
              <Icon size={18}/><span>{label}</span>
            </button>
          )}
        </div>
      )}
    </nav>
    <div className="fv-sidebar-status"><ShieldCheck size={16}/> Read-only AWS collector</div>
  </aside>;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { credentials: "same-origin", headers: { Accept: "application/json", ...(init?.body ? { "Content-Type": "application/json" } : {}), ...init?.headers }, ...init });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof payload.message === "string" ? payload.message : `Request failed (${response.status})`);
  return payload as T;
}

export default function AuthenticatedShell() {
  const [session, setSession] = useState<Session | null>(null);
  const [checking, setChecking] = useState(true);
  const [view, setView] = useState<View>("Overview");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [signedOut, setSignedOut] = useState(false);
  const workspaceReady = Boolean(session?.authenticated && !session.must_change_password);

  useEffect(() => {
    if (workspaceReady) document.getElementById("main-content")?.focus();
  }, [workspaceReady]);

  const loadSession = useCallback(async () => {
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
    try { await request("/api/auth/logout", { method: "POST", body: "{}" }); setSession({ authenticated: false }); setView("Overview"); setSignedOut(true); }
    catch (e) { setError(e instanceof Error ? e.message : "Sign out failed."); }
    finally { setBusy(false); }
  }

  if (checking) return <main className="fv-session-loading" role="status"><Layers3 size={24}/> Checking your session?</main>;
  if (!session?.authenticated) return <LoginScreen onLogin={login} busy={busy} error={error} signedOut={signedOut}/>;
  if (session.must_change_password) return <PasswordScreen onDone={loadSession} busy={busy} setBusy={setBusy}/>;

  const current = view === "cloud" ? "AWS accounts" : "Admin settings";
  return <div className="fv-shell">
    <a className="fv-skip-link" href="#main-content">Skip to content</a>
    <WorkspaceNavigation view={view} onNavigate={setView}/>
    {view !== "profile" && view !== "cloud" ? <App
      onOpenCloud={() => setView("cloud")} onOpenProfile={() => setView("profile")}
      onSignOut={() => void logout()} signingOut={busy} username={session.username || "admin"}
      tab={view} onNavigate={setView}/> :
      <main className="main fv-main" id="main-content" tabIndex={-1}>
        <header className="topbar fv-topbar fv-account-topbar">
          <div className="fv-toolbar-right">
            <button type="button" className="fv-avatar-button" title="Profile" aria-label="Open profile" onClick={()=>setView("profile")}><span className="fv-avatar">{(session.username || "AD").slice(0,2).toUpperCase()}</span></button>
            <button type="button" className="fv-icon-action" aria-label="Sign out" title="Sign out" disabled={busy} onClick={()=>void logout()}><LogOut size={17}/></button>
          </div>
        </header>
        <div className="fv-page fv-account-page">
          <section className="fv-page-heading">
            <h1>{current}</h1>
          </section>
          {view==="profile"?<ProfileView username={session.username || "admin"} onPasswordChanged={loadSession}/>:<CloudView/>}
        </div>
      </main>}
    {error && <div className="fin-toast" role="alert">{error}<button type="button" onClick={()=>setError("")}>Dismiss</button></div>}
  </div>;
}

function AuthExperience({ children, title, description }: {
  children: React.ReactNode; title: string; description: string;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { heading.current?.focus(); }, [title]);

  return <main className="fv-auth-experience">
    <div className="fv-auth-layout">
      <header className="fv-auth-logo"><span><Layers3 size={23}/></span><strong>Finovaunt</strong></header>
      <div className="fv-auth-form-area">
        <div className="fv-auth-form-inner">
          <h1 ref={heading} tabIndex={-1}>{title}</h1>
          <p className="fv-auth-description">{description}</p>
          {children}
        </div>
      </div>
      <footer className="fv-auth-trust"><ShieldCheck size={16}/> Read-only AWS collection</footer>
    </div>
    <aside className="fv-auth-art" aria-hidden="true">
      <div className="fv-auth-geometry"><i/><i/><i/><i/><i/><i/></div>
    </aside>
  </main>;
}

function LoginScreen({onLogin,busy,error,signedOut}:{onLogin:(u:string,p:string)=>Promise<void>;busy:boolean;error:string;signedOut:boolean}) {
  const [username,setUsername]=useState("admin");
  const [password,setPassword]=useState("");
  const [visible,setVisible]=useState(false);
  function submit(event:FormEvent) {event.preventDefault();void onLogin(username,password);}
  return <AuthExperience title={signedOut ? "You’re signed out" : "Sign in"} description={signedOut ? "Sign in again to return to your workspace." : "Use your Finovaunt credentials to open the workspace."}>
    {error && <div className="fv-auth-message error" role="alert">{error}</div>}
    <form onSubmit={submit} className="fv-auth-form">
      <label htmlFor="fv-login-username">Username<input id="fv-login-username" autoComplete="username" required value={username} onChange={event=>setUsername(event.target.value)}/></label>
      <label htmlFor="fv-login-password">Password<div className="fv-password-control"><input id="fv-login-password" type={visible?"text":"password"} autoComplete="current-password" required value={password} onChange={event=>setPassword(event.target.value)}/>
        <button type="button" className="fv-password-visibility" title={visible?"Hide password":"Show password"} aria-label={visible?"Hide password":"Show password"} onClick={()=>setVisible(v=>!v)}>{visible?<EyeOff size={18}/>:<Eye size={18}/>}</button></div>
      </label>
      <button className="fv-primary-button fv-auth-submit" disabled={busy} type="submit">{busy?"Signing In…":"Sign in"} <ArrowRight size={17}/></button>
    </form>
    <div className="fv-auth-instructions"><CircleHelp size={16}/><p>First-time access uses the <strong>admin</strong> username and the bootstrap password configured for this deployment.</p></div>
  </AuthExperience>;
}

function PasswordScreen({onDone,busy,setBusy}:{onDone:()=>Promise<void>;busy:boolean;setBusy:(value:boolean)=>void}) {
  const [current,setCurrent]=useState("");
  const [next,setNext]=useState("");
  const [confirm,setConfirm]=useState("");
  const [error,setError]=useState("");
  async function submit(event:FormEvent) {
    event.preventDefault();setError("");
    if(next.length<12){setError("Use at least 12 characters for your new password.");return;}
    if(next!==confirm){setError("The new passwords do not match.");return;}
    setBusy(true);
    try {await request("/api/auth/password",{method:"POST",body:JSON.stringify({current_password:current,new_password:next})});await onDone();}
    catch(err){setError(err instanceof Error?err.message:"Password change failed.");}
    finally{setBusy(false);}
  }
  return <AuthExperience title="Set a new password" description="Replace your bootstrap password to continue to Finovaunt.">
    {error&&<div className="fv-auth-message error" role="alert">{error}</div>}
    <form onSubmit={submit} className="fv-auth-form">
      <label>Current Password<input type="password" autoComplete="current-password" required value={current} onChange={event=>setCurrent(event.target.value)}/></label>
      <label>New Password<input type="password" autoComplete="new-password" minLength={12} required value={next} onChange={event=>setNext(event.target.value)}/><small>Use at least 12 characters.</small></label>
      <label>Confirm New Password<input type="password" autoComplete="new-password" minLength={12} required value={confirm} onChange={event=>setConfirm(event.target.value)}/></label>
      <button className="fv-primary-button fv-auth-submit" type="submit" disabled={busy}>{busy?"Updating Password…":"Update password"} <ArrowRight size={17}/></button>
    </form>
  </AuthExperience>;
}

function ProfileView({ username, onPasswordChanged }: { username: string; onPasswordChanged: () => Promise<void> }) {
  const [current, setCurrent] = useState(""); const [next, setNext] = useState(""); const [confirm, setConfirm] = useState(""); const [message, setMessage] = useState(""); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent) { e.preventDefault(); setError(""); setMessage(""); if (next.length < 12) { setError("New password must contain at least 12 characters."); return; } if (next !== confirm) { setError("The new passwords do not match."); return; } setBusy(true); try { await request("/api/auth/password", { method: "POST", body: JSON.stringify({ current_password: current, new_password: next }) }); setMessage("Password updated successfully."); setCurrent(""); setNext(""); setConfirm(""); await onPasswordChanged(); } catch (e) { setError(e instanceof Error ? e.message : "Password update failed."); } finally { setBusy(false); } }
  return <section className="fv-settings-grid fv-settings-focused">
    <article className="fv-account-card">
      <div className="fv-card-headline"><KeyRound size={19}/><div><h2>Change password</h2><p>Signed in as {username}</p></div></div>
      <form onSubmit={submit} className="fv-managed-form">
        <label>Current Password<input type="password" autoComplete="current-password" required value={current} onChange={e=>setCurrent(e.target.value)}/></label>
        <label>New Password<input type="password" autoComplete="new-password" minLength={12} required value={next} onChange={e=>setNext(e.target.value)}/><small>Use at least 12 characters.</small></label>
        <label>Confirm New Password<input type="password" autoComplete="new-password" minLength={12} required value={confirm} onChange={e=>setConfirm(e.target.value)}/></label>
        {error&&<div className="fv-auth-message error" role="alert">{error}</div>}
        {message&&<div className="fv-auth-message success" role="status"><CircleCheck size={16}/>{message}</div>}
        <button type="submit" className="fv-primary-button" disabled={busy}>{busy?"Saving…":"Update password"} <ArrowRight size={16}/></button>
      </form>
    </article>
  </section>;
}
function CloudView() {
  const [accounts, setAccounts] = useState<CloudAccount[]>([]); const [selected, setSelected] = useState(""); const [history, setHistory] = useState<BillingScan[]>([]); const [busy, setBusy] = useState(false); const [error, setError] = useState(""); const [message, setMessage] = useState("");
  const [inventory, setInventory] = useState<InventoryScan | null>(null);
  const [editing, setEditing] = useState<CloudAccount | null>(null);
  const [editReason, setEditReason] = useState("");
  const [showOnboard, setShowOnboard] = useState(false);
  const [name, setName] = useState(""); const [accountId, setAccountId] = useState(""); const [roleArn, setRoleArn] = useState(""); const [region, setRegion] = useState("us-east-1"); const [externalId, setExternalId] = useState("");
  const historyRequest = useRef(0);
  const inventoryRequest = useRef(0);
  const editButton = useRef<HTMLButtonElement>(null);
  const editName = useRef<HTMLInputElement>(null);
  const restoreEditFocus = useRef(false);

  const isEditing = editing !== null;
  useEffect(() => {
    if (isEditing) editName.current?.focus();
  }, [isEditing]);
  useEffect(() => {
    if (!isEditing && !busy && restoreEditFocus.current) {
      restoreEditFocus.current = false;
      editButton.current?.focus();
    }
  }, [isEditing, busy]);

  function selectAccount(id: string) {
    historyRequest.current++;
    inventoryRequest.current++;
    setSelected(id);
    setHistory([]);
    setInventory(null);
    setEditing(null);
    setExternalId("");
    setError("");
    setMessage("");
  }

  const refresh = useCallback(async () => {
    try {
      const data = await request<{items: CloudAccount[]}>("/api/cloud-accounts");
      setAccounts(data.items);
      setSelected(current => current || data.items[0]?.account_id || "");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load cloud accounts.");
    }
  }, []);

  const loadHistory = useCallback(async (id: string) => {
    const requestId = ++historyRequest.current;
    if (!id) return;
    try {
      const data = await request<{items: BillingScan[]}>(`/api/billing-scans/${encodeURIComponent(id)}`);
      if (requestId === historyRequest.current) setHistory([...data.items].reverse());
    } catch (e) {
      if (requestId === historyRequest.current) setError(e instanceof Error ? e.message : "Could not load billing history.");
    }
  }, []);

  const loadInventory = useCallback(async (id: string) => {
    const requestId = ++inventoryRequest.current;
    if (!id) return;
    try {
      const data = await request<{latest: InventoryScan | null}>(`/api/inventory-scans/${encodeURIComponent(id)}`);
      if (requestId === inventoryRequest.current) setInventory(data.latest);
    } catch (e) {
      if (requestId === inventoryRequest.current) setError(e instanceof Error ? e.message : "Could not load cloud inventory.");
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    void loadHistory(selected);
    void loadInventory(selected);
    return () => {
      historyRequest.current++;
      inventoryRequest.current++;
    };
  }, [selected, loadHistory, loadInventory]);

  async function scanInventory() {
    if (!selected || busy) return;
    inventoryRequest.current++;
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
  async function onboard(e: FormEvent) { e.preventDefault(); if (busy) return; setBusy(true); setError(""); setMessage(""); try { const created = await request<CloudAccount>("/api/cloud-accounts", { method: "POST", body: JSON.stringify({ name, provider: "aws", account_id: accountId, role_arn: roleArn, region, external_id: externalId }) }); setAccounts(old => [...old, created]); selectAccount(created.account_id); setExternalId(externalId); setName(""); setAccountId(""); setRoleArn(""); setShowOnboard(false); setMessage("AWS account onboarded. Keep the external ID available if the role trust policy requires it for scans."); } catch (e) { setError(e instanceof Error ? e.message : "Account onboarding failed."); } finally { setBusy(false); } }
  async function scan() { if (!selected || busy) return; historyRequest.current++; setBusy(true); setError(""); setMessage(""); try { await request("/api/billing-scans", { method: "POST", body: JSON.stringify({ account_id: selected, external_id: externalId }) }); await loadHistory(selected); setMessage("Read-only billing scan completed."); } catch (e) { setError(e instanceof Error ? e.message : "Billing scan failed."); } finally { setBusy(false); } }
  async function updateCollector(event: FormEvent) {
    event.preventDefault();
    if (!editing || busy) return;
    setBusy(true);setError("");setMessage("");
    try {
      await request("/api/cloud-accounts/"+encodeURIComponent(editing.account_id)+"/configuration",{
        method:"POST",body:JSON.stringify({name:editing.name,role_arn:editing.role_arn,region:editing.region,reason:editReason.trim()}),
      });
      const target=editing.account_id;
      historyRequest.current++;
      inventoryRequest.current++;
      restoreEditFocus.current = true;
      setEditing(null);setEditReason("");
      setInventory(null);setHistory([]);
      setMessage("Collector configuration saved. Historical scans are retained. Collect fresh evidence for the updated role or region.");
      const results=await request<{items:CloudAccount[]}>("/api/cloud-accounts");
      setAccounts(results.items);
      await Promise.all([loadHistory(target), loadInventory(target)]);
    } catch(err) {setError(err instanceof Error?err.message:"Unable to update collector.");}
    finally{setBusy(false);}
  }
  async function removeSelectedAccount() {
    if (!selected || busy) return;
    const account = accounts.find(item => item.account_id === selected);
    if (!window.confirm(`Remove ${account?.name || selected} from Finovaunt? Its saved billing history will also be deleted. AWS resources will not be changed.`)) return;
    setBusy(true); setError(""); setMessage("");
    try {
      await request(`/api/cloud-accounts/${encodeURIComponent(selected)}`, { method: "DELETE" });
      const remaining = accounts.filter(item => item.account_id !== selected);
      setAccounts(remaining);
      selectAccount(remaining[0]?.account_id || "");
      setMessage("AWS account and locally saved billing history removed. AWS resources were not changed.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not remove cloud account.");
    } finally {
      setBusy(false);
    }
  }
  const active = accounts.find(account=>account.account_id===selected);
  const currentRevision = active?.config_revision ?? 1;
  const latest = history.find(item=>(item.config_revision ?? 1)===currentRevision);
  const currentInventory = inventory && (inventory.config_revision ?? 1)===currentRevision?inventory:null;
  const formatted = (amount:number,unit="USD") => new Intl.NumberFormat("en-US",{style:"currency",currency:unit,maximumFractionDigits:2}).format(amount);
  return <div className="fv-cloud-workspace">
    {error&&<div className="fv-auth-message error" role="alert">{error}<button type="button" className="fv-inline-dismiss" onClick={()=>setError("")}>Dismiss</button></div>}
    {message&&<div className="fv-auth-message success" role="status"><CircleCheck size={17}/>{message}</div>}
    {!showOnboard && accounts.length > 0 && <div className="fv-cloud-toolbar">
      <button type="button" className="fv-outline-button" disabled={busy} onClick={() => { setShowOnboard(true); setEditing(null); }}><Plus size={16}/> Add AWS account</button>
    </div>}
    {showOnboard&&<article className="fv-account-card">
      <div className="fv-card-headline"><Plus size={19}/><div><h2>Onboard AWS Account</h2><p>Register an existing read-only collector role.</p></div></div>
      <form onSubmit={onboard} className="fv-managed-form fv-form-columns">
        <label>Account Display Name<input required maxLength={120} value={name} onChange={e=>setName(e.target.value)} placeholder="Production AWS"/></label>
        <label>AWS Account ID<input required inputMode="numeric" pattern="[0-9]{12}" maxLength={12} value={accountId} onChange={e=>setAccountId(e.target.value)} placeholder="12-digit AWS account ID"/></label>
        <label className="fv-field-wide">IAM Role ARN<input required value={roleArn} onChange={e=>setRoleArn(e.target.value)} placeholder="arn:aws:iam::123456789012:role/FinovauntReadOnly"/></label>
        <label>Default AWS Region<select value={region} onChange={e=>setRegion(e.target.value)}>{["us-east-1","us-east-2","us-west-1","us-west-2","eu-central-1","eu-west-1","ap-south-1","ap-southeast-1"].map(r=><option key={r} value={r}>{r}</option>)}</select></label>
        <label>External ID (Optional)<input type="password" autoComplete="off" value={externalId} onChange={e=>setExternalId(e.target.value)} placeholder="Required only for some trust policies"/></label>
        <div className="fv-form-actions fv-field-wide"><button type="submit" className="fv-primary-button" disabled={busy}>{busy?"Connecting…":"Connect AWS Account"} <ArrowRight size={16}/></button><button type="button" className="fv-outline-button" onClick={()=>setShowOnboard(false)}>Cancel</button></div>
      </form><p className="fv-help-text"><ShieldCheck size={16}/> Onboarding stores account metadata locally. External IDs are not persisted and no AWS resources are changed.</p>
    </article>}
    {!showOnboard && <div className="fv-cloud-grid">
      <section className="fv-account-card">
        <h2>Connections</h2>
        {accounts.length===0?<div className="fv-cloud-empty"><Cloud size={29}/><strong>No AWS accounts connected</strong><p>Connect an account to begin collecting AWS billing and inventory evidence.</p><button className="fv-outline-button" onClick={()=>setShowOnboard(true)}>Add Your First Account <ArrowRight size={15}/></button></div>:
        <div className="fv-account-list">{accounts.map(account=><button type="button" key={account.account_id}
          className={"fv-account-list-item"+(selected===account.account_id?" selected":"")} aria-pressed={selected===account.account_id} disabled={busy}
          onClick={()=>{if (account.account_id !== selected) selectAccount(account.account_id);}}>
          <span className="fv-provider-symbol"><Layers3 size={19}/></span><span className="fv-account-list-info"><strong>{account.name}</strong><small>{account.account_id} · {account.region}</small></span>
          {selected===account.account_id?<CircleCheck size={17} className="fv-selected-icon"/>:<ArrowRight size={16}/>}
        </button>)}</div>}
      </section>
      {active && <section className="fv-account-card">
        <h2>{active.name}</h2>
        <div className="fv-cloud-actions">
          <button type="button" className="fv-primary-button" disabled={busy} onClick={()=>void scan()}><RefreshCw size={16}/>{busy?"Processing…":"Collect Billing"}</button>
          <button type="button" className="fv-outline-button" disabled={busy} onClick={()=>void scanInventory()}><HardDrive size={16}/> Collect Inventory</button>
        </div>
        <details className="fv-disclosure" key={active.account_id}>
          <summary>Collector settings</summary>
          <div className="fv-cloud-details">
            <div><span>Account ID</span><strong>{active.account_id}</strong></div>
            <div><span>AWS Region</span><strong>{active.region}</strong></div>
            <div className="fv-detail-full"><span>IAM Role ARN</span><code>{active.role_arn}</code></div>
          </div>
          <label className="fv-form-compact">External ID for scans (if required)<input type="password" autoComplete="off" value={externalId} onChange={e=>setExternalId(e.target.value)} placeholder="Not saved"/></label>
          <div className="fv-cloud-actions">
            <button type="button" className="fv-outline-button" ref={editButton} disabled={busy} onClick={()=>{setEditing({...active});setEditReason("");}}><Pencil size={16}/> Edit Collector</button>
            <button type="button" className="fv-danger-link" disabled={busy} onClick={()=>void removeSelectedAccount()}><Trash2 size={15}/> Remove AWS Account</button>
          </div>
        </details>
      </section>}
    </div>}
    {editing&&<article className="fv-account-card">
      <div className="fv-card-headline"><Pencil size={19}/><div><h2>Edit Collector · {editing.account_id}</h2><p>Change the configured role or region without deleting historical evidence.</p></div></div>
      <form className="fv-managed-form fv-form-columns" onSubmit={e=>void updateCollector(e)}>
        <label>Display Name<input ref={editName} value={editing.name} maxLength={120} required onChange={e=>setEditing(v=>v?{...v,name:e.target.value}:v)}/></label>
        <label>AWS Region<select value={editing.region} required onChange={e=>setEditing(v=>v?{...v,region:e.target.value}:v)}>{["us-east-1","us-east-2","us-west-1","us-west-2","eu-central-1","eu-west-1","ap-south-1","ap-southeast-1"].map(r=><option key={r} value={r}>{r}</option>)}</select></label>
        <label className="fv-field-wide">Collector Role ARN<input required value={editing.role_arn} onChange={e=>setEditing(v=>v?{...v,role_arn:e.target.value}:v)}/></label>
        <label className="fv-field-wide">Reason For Change<textarea required rows={3} minLength={10} maxLength={2000} value={editReason} onChange={e=>setEditReason(e.target.value)} placeholder="Describe why the role or region is changing (minimum 10 characters)."/></label>
        <div className="fv-form-actions fv-field-wide"><button type="submit" className="fv-primary-button" disabled={busy}>{busy?"Saving…":"Save Collector Configuration"}</button><button type="button" className="fv-outline-button" disabled={busy} onClick={()=>{restoreEditFocus.current = true; setEditing(null);}}>Cancel</button></div>
      </form><p className="fv-help-text"><ShieldCheck size={16}/> Role or region changes require a fresh collection. Historical evidence remains preserved.</p>
    </article>}
    {active && !showOnboard && <div className="fv-account-evidence">
      <details className="fv-disclosure">
        <summary>Inventory evidence{currentInventory ? ` · ${currentInventory.asset_count.toLocaleString()} resources` : " · Not collected"}</summary>
        {!currentInventory?<p>Collect inventory to see resources in the selected region.</p>:<>
          <div className="fv-evidence-summary"><strong>{currentInventory.asset_count.toLocaleString()}</strong><span>Observed resources · {currentInventory.status}{currentInventory.truncated?" · Partial inventory":""}</span></div>
          <div className="fv-evidence-table">{currentInventory.assets.slice(0,12).map(asset=><div key={asset.type+asset.id}><span><strong>{asset.name}</strong><small>{asset.type.toUpperCase()} · {asset.region}</small></span><span>{asset.state}</span></div>)}</div>
          {currentInventory.assets.length>12&&<p className="fv-help-text">Showing 12 of {currentInventory.assets.length} resources. See the dashboard for details.</p>}
        </>}
      </details>
      <details className="fv-disclosure">
        <summary>Billing evidence{latest ? ` · ${formatted(latest.total_cost, latest.currency)}` : " · Not collected"}</summary>
        {!latest?<p>Collect billing to see AWS service spending.</p>:<>
          <div className="fv-evidence-summary"><strong>{formatted(latest.total_cost,latest.currency)}</strong><span>Month-to-date · {latest.period_start} through {latest.period_end_exclusive} (exclusive)</span></div>
          <div className="fv-evidence-table">{[...latest.services].sort((a,b)=>b.amount-a.amount).slice(0,9).map(service=><div key={service.service}><span>{service.service}</span><strong>{formatted(service.amount,service.currency)}</strong></div>)}</div>
          <p className="fv-help-text">Provisional AWS costs, not resource-level attribution.</p>
        </>}
      </details>
    </div>}
  </div>;
}
