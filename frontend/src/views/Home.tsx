'use client'

import Link from 'next/link'
import { LazyMotion, MotionConfig, domAnimation, m } from 'motion/react'
import {
  ArrowRight, BookOpenCheck, CheckCircle2, Database, FileSearch, Fingerprint,
  GitBranch, Landmark, LockKeyhole, ScanText, Scale, SearchCheck, ShieldCheck, UserCheck,
} from 'lucide-react'

import { useAuth } from '@/contexts/AuthContext'

const EVIDENCE_FLOW = [
  { title: 'Acquire', body: 'Archive official legislation and its source identity.', icon: Landmark },
  { title: 'Extract', body: 'Route native, complex and scanned pages without hiding uncertainty.', icon: ScanText },
  { title: 'Structure', body: 'Preserve sections, conditions, exceptions and legal hierarchy.', icon: FileSearch },
  { title: 'Map', body: 'Connect exact legal predicates to the applicable RDTII indicator.', icon: GitBranch },
  { title: 'Verify', body: 'Check source, status, citation, span alignment and counter-evidence.', icon: SearchCheck },
  { title: 'Approve', body: 'Record named, role-separated human decisions before export.', icon: UserCheck },
]

const SAFEGUARDS = [
  ['Official-source eligibility', 'Bills, drafts, commentary and unsupported instruments are quarantined before retrieval.'],
  ['Currentness evidence', 'An in-force claim requires an official fact; unknown or conflicting status blocks export.'],
  ['Source-exact quotation', 'Normalization may locate evidence, but the exported characters come from the archived source span.'],
  ['Independent review stages', 'Citation, mapping and status decisions remain attributed and append-only.'],
  ['Fail-closed release', 'Pending review, incomplete proof or unresolved alignment cannot enter deterministic replay.'],
]

const DEMO = [
  ['01', 'Open one finding', 'Start from the mapped evidence row and its indicator rationale.'],
  ['02', 'Inspect Source Match', 'Compare the exact quotation with its official archived context.'],
  ['03', 'Read the proof chain', 'Verify currentness, source hash, citation anchor and gate results.'],
  ['04', 'Review the decision', 'See who approved each stage and whether the engine accepted the receipt.'],
]

export default function Home() {
  const { isAuthenticated } = useAuth()
  const workspaceHref = isAuthenticated ? '/dashboard' : '/login?redirect=/dashboard'
  return <LazyMotion features={domAnimation}><MotionConfig reducedMotion="user">
    <div id="overview" className="public-home">
      <section className="public-hero">
        <div className="public-hero-grid" aria-hidden="true" />
        <div className="public-hero-inner">
          <m.div className="public-hero-copy" initial={{ y: 16 }} animate={{ y: 0 }} transition={{ duration: .45 }}>
            <span className="public-kicker"><Scale size={15} /> UN AI Hackathon · legal evidence assurance</span>
            <h1>A reproducible proof for every exported legal row.</h1>
            <p>ClauseChain turns official digital-trade legislation into reviewable RDTII evidence—without asking a judge to trust an uncited model answer.</p>
            <div className="public-hero-actions"><Link href={workspaceHref}>Open the evidence workspace <ArrowRight size={17} /></Link><Link href="/#evidence-flow">See the proof chain</Link></div>
            <div className="public-trust-line"><span><CheckCircle2 /> Official sources</span><span><CheckCircle2 /> Exact quotations</span><span><CheckCircle2 /> Named approvals</span></div>
          </m.div>
          <m.div className="public-proof-card" initial={{ scale: .98 }} animate={{ scale: 1 }} transition={{ duration: .45, delay: .08 }}>
            <header><span>EXPORT ELIGIBILITY</span><strong>Mechanical, not rhetorical</strong></header>
            <div className="public-proof-row"><Fingerprint /><span><b>Source identity</b><small>Official URL · SHA-256 · access time</small></span><em>required</em></div>
            <div className="public-proof-row"><BookOpenCheck /><span><b>Citation proof</b><small>Exact span · hierarchy · page or anchor</small></span><em>required</em></div>
            <div className="public-proof-row"><ShieldCheck /><span><b>Legal status</b><small>Evidence-backed currentness resolution</small></span><em>required</em></div>
            <div className="public-proof-row"><UserCheck /><span><b>Human decision</b><small>Named reviewer · immutable receipt</small></span><em>required</em></div>
            <footer><LockKeyhole size={15} /> Missing proof blocks release.</footer>
          </m.div>
        </div>
      </section>

      <section className="public-thesis"><div><span>THE PROBLEM</span><h2>Legal AI fails when confidence outruns provenance.</h2></div><p>Digital-trade rules live across consolidated statutes, amendments, scanned schedules and official portals. ClauseChain treats acquisition, legal status, document structure and human review as parts of the answer—not supporting details hidden behind it.</p></section>

      <section id="evidence-flow" className="public-section">
        <div className="public-section-heading"><span>EVIDENCE FLOW</span><h2>From official instrument to approved indicator evidence</h2><p>One bounded route, with an explicit failure state at every stage.</p></div>
        <div className="public-flow">{EVIDENCE_FLOW.map(({ title, body, icon: Icon }, index) => <m.article key={title} initial={{ y: 12 }} whileInView={{ y: 0 }} viewport={{ once: true, amount: .25 }} transition={{ delay: index * .04 }}><span>{String(index + 1).padStart(2, '0')}</span><Icon /><h3>{title}</h3><p>{body}</p></m.article>)}</div>
      </section>

      <section id="verification" className="public-verification">
        <div className="public-verification-inner"><div><span className="public-dark-kicker">CHAMPION SAFEGUARDS</span><h2>The system is designed to abstain before it embarrasses.</h2><p>Every safeguard is visible in the judge-facing workspace. A failed gate is a blocker or review state—not a confidence score painted green.</p></div><div className="public-safeguards">{SAFEGUARDS.map(([title, body]) => <article key={title}><ShieldCheck /><div><h3>{title}</h3><p>{body}</p></div></article>)}</div></div>
      </section>

      <section id="architecture" className="public-section public-architecture">
        <div className="public-section-heading"><span>ARCHITECTURE</span><h2>Authoritative files, immutable snapshots, optional mirrors</h2><p>The judged path remains reproducible even when an external graph or model is unavailable.</p></div>
        <div className="public-architecture-map"><div><Landmark /><b>Official sources</b><small>HTML · PDF · OCR</small></div><i /><div><Database /><b>Immutable snapshot</b><small>Artifacts · spans · hashes</small></div><i /><div><Scale /><b>Review domains</b><small>Citation · mapping · status</small></div><i /><div><LockKeyhole /><b>Submission replay</b><small>Approved rows only</small></div></div>
        <p className="public-graph-note"><GitBranch size={16} /><span><strong>Neo4j is a provenance mirror.</strong> ClauseChain does not claim GraphRAG retrieval lift without a measured A/B result.</span></p>
      </section>

      <section className="public-demo"><div className="public-section-heading"><span>JUDGE DEMO</span><h2>Four steps from claim to proof</h2></div><div>{DEMO.map(([number, title, body]) => <article key={number}><span>{number}</span><h3>{title}</h3><p>{body}</p></article>)}</div></section>

      <section className="public-final-cta"><div><span>CLAUSECHAIN</span><h2>Inspect the evidence. Challenge the mapping. Trust the receipt.</h2></div><Link href={workspaceHref}>Enter the workspace <ArrowRight size={17} /></Link></section>
    </div>
  </MotionConfig></LazyMotion>
}
