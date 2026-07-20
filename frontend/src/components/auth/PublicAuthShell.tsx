import { BookOpenCheck, Fingerprint, ShieldCheck, UserCheck } from 'lucide-react'

export default function PublicAuthShell({ mode, children }: { mode: 'login' | 'register'; children: React.ReactNode }) {
  return <div className="public-auth-page"><div className="public-auth-shell">
    <aside>
      <span className="public-kicker">{mode === 'login' ? 'AUTHORITATIVE REVIEW ACCESS' : 'JOIN THE REVIEW WORKSPACE'}</span>
      <h1>{mode === 'login' ? 'Continue the proof chain.' : 'Create your ClauseChain account.'}</h1>
      <p>{mode === 'login' ? 'Review exact legal evidence, record role-separated decisions and inspect the immutable receipt.' : 'Your account identity is attached to every legal decision you make in the workspace.'}</p>
      <div className="public-auth-proof"><span><BookOpenCheck /><b>Exact evidence</b><small>Official source context</small></span><span><Fingerprint /><b>Immutable identity</b><small>Hashes and snapshot provenance</small></span><span><ShieldCheck /><b>Fail-closed gates</b><small>Incomplete proof cannot ship</small></span><span><UserCheck /><b>Named review</b><small>Attributable decisions</small></span></div>
      <blockquote>“A reproducible proof for every exported legal row.”</blockquote>
    </aside>
    <section>{children}</section>
  </div></div>
}
