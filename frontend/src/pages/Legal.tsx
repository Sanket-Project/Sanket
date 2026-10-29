import { Link } from "react-router-dom";
import { ArrowLeft } from "@/components/ui/icons";
import { LogoMark } from "@/components/ui/Logo";

const LAST_UPDATED = "June 1, 2026";

interface LegalSection {
  heading: string;
  body: string[];
}

const LegalShell = ({
  title,
  subtitle,
  sections,
}: {
  title: string;
  subtitle: string;
  sections: LegalSection[];
}) => (
  <div className="min-h-dvh bg-canvas text-content">
    <nav aria-label="Legal navigation" className="border-b border-line bg-surface">
      <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-4 px-6 py-5">
        <Link to="/" className="flex items-center gap-3 font-heading font-semibold"><LogoMark size={32} />SANKET</Link>
        <Link to="/" className="inline-flex items-center gap-2 text-sm text-content-muted hover:text-accent"><ArrowLeft size={14} /> Back to home</Link>
      </div>
    </nav>
    <article className="mx-auto max-w-3xl px-6 py-12 sm:py-16">
      <header className="border-b border-line pb-8">
        <p className="text-xs font-medium text-accent">Legal</p>
        <h1 className="mt-3 font-heading text-3xl font-semibold text-content">{title}</h1>
        <p className="mt-3 text-base leading-relaxed text-content-muted">{subtitle}</p>
        <p className="mt-4 text-xs text-content-subtle">Last updated: {LAST_UPDATED}</p>
      </header>
      <div className="mt-9 space-y-9">
        {sections.map((s, i) => (
          <section key={i} aria-labelledby={`legal-section-${i}`}>
            <h2 id={`legal-section-${i}`} className="flex items-baseline gap-3 font-heading text-lg font-semibold text-content">
              <span className="font-mono text-xs text-accent">{String(i + 1).padStart(2, "0")}</span>{s.heading}
            </h2>
            {s.body.map((p, j) => <p className="mt-3 text-sm leading-7 text-content-muted" key={j}>{p}</p>)}
          </section>
        ))}
        <footer className="rounded-2xl border border-line bg-surface p-5">
          <p className="text-sm leading-7 text-content-muted">
            Questions about this document? Contact us at{" "}<a href="mailto:legal@sanket.app" className="text-accent underline underline-offset-4">legal@sanket.app</a>{" "}
            or write to SANKET Technologies, Inc., 500 Howard Street, San Francisco, CA 94105.
          </p>
          <div className="mt-4 flex flex-wrap gap-5 text-sm font-medium text-accent">
            <Link to="/terms">Terms of Service</Link><Link to="/privacy">Privacy Policy</Link><Link to="/">Home</Link>
          </div>
        </footer>
      </div>
    </article>
  </div>
);

const TERMS_SECTIONS: LegalSection[] = [
  {
    heading: "Agreement to Terms",
    body: [
      "These Terms of Service (\"Terms\") govern your access to and use of the SANKET predictive analytics and supply chain optimization platform, including our websites, APIs, dashboards, and related services (collectively, the \"Service\"), provided by SANKET Technologies, Inc. (\"SANKET\", \"we\", \"us\").",
      "By accessing or using the Service, or by clicking to accept these Terms, you agree to be bound by them on behalf of yourself and the organization you represent. If you do not agree, you may not use the Service.",
    ],
  },
  {
    heading: "Accounts and Eligibility",
    body: [
      "You must be at least 18 years old and authorized to bind your organization to these Terms. You are responsible for maintaining the confidentiality of your account credentials and for all activity that occurs under your account.",
      "Access is provisioned on a per-tenant basis. You agree to notify us immediately of any unauthorized use of your account or any other breach of security.",
    ],
  },
  {
    heading: "Subscriptions and Billing",
    body: [
      "Paid plans are billed in advance on a recurring basis (monthly or annually) according to the tier you select. Fees are non-refundable except where required by law or expressly stated in an order form.",
      "We may change subscription fees upon reasonable prior notice. Continued use of the Service after a fee change constitutes acceptance of the new fees. Usage-based charges, where applicable, are metered and billed in arrears.",
    ],
  },
  {
    heading: "Acceptable Use",
    body: [
      "You agree not to misuse the Service, including by: reverse engineering or attempting to extract our models or source code; reselling or sublicensing access without authorization; uploading unlawful, infringing, or malicious content; or interfering with the integrity or performance of the Service.",
      "You are solely responsible for the data you submit and for ensuring you have the rights necessary to process it through the Service.",
    ],
  },
  {
    heading: "Customer Data and Intellectual Property",
    body: [
      "You retain all rights to the data you provide (\"Customer Data\"). You grant SANKET a limited license to process Customer Data solely to provide and improve the Service for you, consistent with our Privacy Policy.",
      "SANKET and its licensors retain all rights, title, and interest in the Service, including the underlying foundation models, software, and documentation. We do not use your Customer Data to train shared models without your explicit written consent.",
    ],
  },
  {
    heading: "Service Availability",
    body: [
      "We strive to maintain a 99.99% uptime target for production environments, subject to scheduled maintenance and events outside our reasonable control. Specific service level commitments, where offered, are set out in your order form or a separate SLA.",
      "Forecasts, optimizations, and recommendations produced by the Service are decision-support outputs. You remain responsible for the business decisions you make using them.",
    ],
  },
  {
    heading: "Disclaimers and Limitation of Liability",
    body: [
      "The Service is provided \"as is\" and \"as available\" without warranties of any kind, whether express or implied, to the maximum extent permitted by law.",
      "To the fullest extent permitted by law, SANKET's aggregate liability arising out of or relating to these Terms or the Service will not exceed the amounts you paid to us in the twelve months preceding the event giving rise to the claim.",
    ],
  },
  {
    heading: "Termination",
    body: [
      "You may stop using the Service at any time. We may suspend or terminate your access if you materially breach these Terms or if required to comply with law. Upon termination, your right to access the Service ceases and we will make Customer Data available for export for a limited period as described in our documentation.",
    ],
  },
  {
    heading: "Changes to These Terms",
    body: [
      "We may update these Terms from time to time. If we make material changes, we will provide notice through the Service or by email. Your continued use after the effective date constitutes acceptance of the revised Terms.",
    ],
  },
];

const PRIVACY_SECTIONS: LegalSection[] = [
  {
    heading: "Overview",
    body: [
      "This Privacy Policy explains how SANKET Technologies, Inc. (\"SANKET\", \"we\", \"us\") collects, uses, discloses, and safeguards information when you use our predictive analytics and supply chain optimization platform (the \"Service\").",
      "We are committed to processing personal data lawfully and transparently, and to giving you meaningful control over your information.",
    ],
  },
  {
    heading: "Information We Collect",
    body: [
      "Account information: name, work email, company, role, and authentication identifiers used to provision and secure your tenant.",
      "Customer Data: the operational data you upload or connect (for example, product catalogs, sales history, inventory, and integration feeds) so the Service can generate forecasts and recommendations.",
      "Usage and device data: log data, IP address, browser type, and interaction events collected automatically to operate, secure, and improve the Service.",
    ],
  },
  {
    heading: "How We Use Information",
    body: [
      "We use information to provide and maintain the Service, authenticate users, generate forecasts and optimizations, meter usage for billing, provide support, and detect and prevent fraud or abuse.",
      "We use aggregated and de-identified data to monitor performance and improve our products. We do not use your Customer Data to train models shared with other customers without your explicit written consent.",
    ],
  },
  {
    heading: "Legal Bases for Processing",
    body: [
      "Where the GDPR or similar laws apply, we process personal data on the basis of contract performance, our legitimate interests in operating and securing the Service, your consent (where required), and compliance with legal obligations.",
    ],
  },
  {
    heading: "Sharing and Disclosure",
    body: [
      "We share information with subprocessors who provide infrastructure, hosting, analytics, and payment processing under contractual confidentiality and data protection obligations.",
      "We may disclose information to comply with applicable law, enforce our agreements, or protect the rights, safety, and security of SANKET, our customers, and the public. In a merger or acquisition, information may be transferred subject to this Policy.",
      "We do not sell personal data.",
    ],
  },
  {
    heading: "Data Security",
    body: [
      "We maintain administrative, technical, and physical safeguards designed to protect information, including encryption in transit and at rest, tenant isolation, access controls, and audit logging. Our practices align with SOC 2 Type II and ISO 27001, and HIPAA/GxP-eligible deployments are available for regulated workloads.",
      "No method of transmission or storage is completely secure, but we work continuously to protect your information and to respond promptly to any incident.",
    ],
  },
  {
    heading: "Data Retention",
    body: [
      "We retain personal data for as long as your account is active or as needed to provide the Service, comply with our legal obligations, resolve disputes, and enforce our agreements. Upon termination, Customer Data is available for export for a limited period and is then deleted or anonymized in accordance with our documentation.",
    ],
  },
  {
    heading: "Your Rights",
    body: [
      "Depending on your location, you may have the right to access, correct, delete, or port your personal data, to restrict or object to processing, and to withdraw consent. To exercise these rights, contact us using the details below. We will respond consistent with applicable law.",
    ],
  },
  {
    heading: "International Transfers",
    body: [
      "We operate globally and may transfer information to countries other than your own. Where required, we rely on appropriate safeguards such as Standard Contractual Clauses to protect personal data during cross-border transfers. Single-region data residency is available on eligible plans.",
    ],
  },
  {
    heading: "Changes to This Policy",
    body: [
      "We may update this Privacy Policy from time to time. We will post the updated version with a revised \"Last updated\" date and, for material changes, provide additional notice through the Service or by email.",
    ],
  },
];

export const TermsPage = () => (
  <LegalShell
    title="Terms of Service"
    subtitle="The terms that govern your access to and use of the SANKET platform."
    sections={TERMS_SECTIONS}
  />
);

export const PrivacyPolicyPage = () => (
  <LegalShell
    title="Privacy Policy"
    subtitle="How SANKET collects, uses, and protects your information."
    sections={PRIVACY_SECTIONS}
  />
);
