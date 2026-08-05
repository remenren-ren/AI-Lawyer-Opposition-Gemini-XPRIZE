# NIDO StrikeOver — Final Written Narrative

## The Missing First Step

Many people know that something has gone wrong before they know how to explain
it to a lawyer. They may have lost money, been treated unfairly or watched an
agreement break down, yet they do not know which facts matter, what evidence to
preserve or even what to ask. Some may have rights worth protecting without
recognising the issue as one that deserves professional attention.

The communication gap works in both directions. A lawyer receives an emotional,
fragmented story but may still not know what the client wants, what the other
side says or which documents exist. The difficulty is greater when English is
not the client's strongest language: literal words may be translated while
context, intention and implied meaning are lost. For people in regional or
remote communities, distance and limited access to a suitable lawyer can prevent
even this first conversation from happening.

A Reddit commenter identifying themselves as a lawyer described receiving
masses of client material that must be sorted to reconstruct the background
before substantive work begins. They called this costly and thought the concept
could help less sophisticated users. They had not tested it, and we did not
verify their identity, so this is qualitative evidence of the problem, not an
endorsement.

NIDO StrikeOver exists to make that first step possible. It does not tell people
to sue, declare that their rights were violated or replace legal advice. It
helps them describe what happened, organise what they have, identify unanswered
questions and prepare a matter that a qualified professional can understand.

## What the Client Sees

The public-facing reception is deliberately simple. A potential client arrives
through a law firm's website and begins an intake conversation. The system asks
focused questions only where information is missing. It does not interrogate;
it clarifies. As the client responds, the system organises the background,
separates both sides' positions and maps the evidence the client has mentioned.
It produces a structured report and, if the firm chooses, prepares a handoff
package for a lawyer. That next step might support early advice, evidence
preservation, negotiation, mediation, a complaint process or a decision that no
further action is appropriate; litigation is only one possible path.

## What Happens Behind the Page

Behind that reception page is a complete desktop workbench. It is privacy-first,
with offline preparation for sensitive material and authorised online analysis
when needed. The workbench reviews a matter across 18 dimensions, maps evidence
to claims and generates weakness cards that highlight where a case is thin. It
builds a whole-matter, two-sided attack and rebuttal structure, permits focused
single-point review and exports professional Markdown, PDF, DOCX and structured
data.

In the deployed application, Gemini performs live LLM calls for focused intake
follow-up, matter organisation, separation of positions from evidence and
controlled deeper review. The application runs on Google Cloud Run. The AI
prepares and highlights; it does not decide.

## Who Does What

The division of labour is deliberate. AI handles reconstruction: sorting,
sequencing, identifying gaps, organising evidence and drafting structured
analysis. A qualified lawyer handles judgment: verifying facts, checking
original evidence, confirming governing law, reviewing deadlines and citations,
and making final strategic decisions. The system is never the adviser. It is
the preparation.

This is also the day-to-day operating loop: the firm embeds the reception entry,
Gemini prepares incoming material, the lawyer reviews the organised dossier,
and the firm's own staff control follow-up and service delivery. Small firms can
spend less professional time on clerical reassembly and more on judgment.

The model can enable work beyond the founder by helping enquiries reach
professional review. Potential roles include solicitors, paralegals, intake
staff and private-deployment or security specialists. These are opportunities,
not current headcount.

## Privacy and Honest Limits

Privacy is central. The competition demonstration uses synthetic material only;
no real client case is included. The vendor does not need to retain client case
files. In production, retention and access decisions sit under the participating
law firm's control. The system does not decide whether a legal wrong occurred,
predict an outcome or recommend litigation. It prepares information so that the
user and a qualified lawyer can consider proportionate ways to protect the
user's interests.

## Building the Business

The business model is a law-firm-controlled deployment. A firm places the intake
entry on its own website, uses it as a free front door for potential clients,
and its own lawyers follow up. Planned commercial options include a firm
subscription, setup and integration fees, usage-based analysis and private
deployment support. These are planned model choices, not achieved sales.

Australia is the initial beachhead. At an illustrative A$99 monthly subscription,
serving 1% of its 16,793 private law practices would represent approximately
A$199,584 annually. This is a scenario, not a forecast or achieved revenue.

There is no confirmed competition-period customer revenue. The live page shows
21 visits and 17 matter-organisation runs, including synthetic demonstrations;
these are usage signals, not customers. A reproducible scan dated 1 August 2026
documented 15 public listings matching our workflow. This supports market
demand, not revenue, contracts or awards.

## Traction and Build

The competition-period business edition reused a pre-existing dual-line legal-
analysis framework. The new work added the Gemini-powered public reception, the
deployed workflow, professional outputs, market validation, a testing package
and the operating model. The 67-file English judge build passed six local
verification groups across compilation, reporting and workflow functions. This
is internal verification, not independent certification.

## The Five-Year Goal

Starting in Australia, NIDO StrikeOver's five-year goal is to become a globally
adaptable bridge between ordinary people and legal professionals. It aims to
address a longstanding gap: people often cannot explain a problem in a form a
lawyer can efficiently understand, while lawyers cannot act responsibly without
clear facts, objectives and evidence. The system should help cross that gap
across languages, regions and different legal-service settings, including
communities where professional access is limited. This is not about encouraging
more lawsuits. We will seek global partners—including law firms, legal-aid and
community organisations, and technology providers—to adapt the workflow across
jurisdictions. The goal is to make a person's
problem clear enough for an appropriate response and help professionals reach
people whose needs might otherwise remain unheard.
