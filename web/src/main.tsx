import React from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';

function App() {
  const [health, setHealth] = React.useState<Record<string, string> | null>(null);
  const [error, setError] = React.useState(false);
  React.useEffect(() => {
    fetch('/health/ready').then(async r => {
      if (![200, 503].includes(r.status)) throw new Error();
      setHealth(await r.json());
    }).catch(() => setError(true));
  }, []);
  return <div className="layout">
    <aside><a className="brand" href="/">r<span>Reconcile</span></a><div className="workspace">FINANCE WORKSPACE</div><div className="nav active">◫ <span>Overview</span></div><div className="aside-note">Accounts payable<br/><b>Every decision, explained.</b></div></aside>
    <main><header><span>Workspace / Overview</span><span className="badge">Development build</span></header>
      <section className="intro"><p className="eyebrow">INVOICE INTELLIGENCE</p><h1>Clarity before approval.</h1><p>Turn invoice PDFs into traceable checks against your purchase orders.<br/>Review the evidence. Make the call.</p></section>
      <section className="welcome"><div className="icon"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="M5 19 19 5M5 5h14v14"/></svg></div><div><h2>Your review workspace is taking shape</h2><p>The application foundation is running. Invoice upload, live processing,<br/>and approval will appear here as they are implemented.</p><span className="status">Implementation in progress</span></div></section>
      <section className="checks"><h2>Service status</h2><p>Live checks from this instance</p>{error ? <p role="alert">Unable to reach the API. Refresh to try again.</p> : !health ? <p>Checking services…</p> : <div className="grid">{[['Database', 'db'], ['OCR engine', 'ocr'], ['Processing worker', 'worker']].map(([label,key]) => <div className="check" key={key}><span>{label}</span><b className={health[key] === 'ok' ? 'ok' : ''}>{health[key] === 'ok' ? 'Available' : health[key] === 'not_implemented' ? 'Not implemented yet' : 'Not configured'}</b></div>)}</div>}</section>
      <footer>Evidence first. Human approval always. <span>Reconcile never executes payment.</span></footer>
    </main>
  </div>;
}
createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);
