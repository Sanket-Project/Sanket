import { Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import "@/styles/landing.css";

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
  <div className="landing-scope">
    <nav className="nav-scrolled">
      <div className="nav-in">
        <Link to="/" className="nav-logo">
          <svg className="nav-logo-mark" viewBox="0 0 64 64" fill="none">
            <rect width="64" height="64" rx="14" fill="#03363D" />
            <line x1="13" y1="46" x2="51" y2="46" stroke="#BDD9D7" strokeWidth="1.8" strokeLinecap="round" opacity="0.22" />
            <path d="M13 42 C22 42 24 23 32 21 C40 19 43 33 51 30" fill="none" stroke="#BDD9D7" strokeWidth="3.4" strokeLinecap="round" strokeLinejoin="round" />
            <circle cx="32" cy="21" r="3.4" fill="#ffffff" />
          </svg>
          <span>SANKET</span>
        </Link>
        <div className="nav-cta">
          <Link to="/" className="btn btn-ghost">
            <ArrowLeft size={14} /> Back to home
          </Link>
        </div>
      </div>
    </nav>

    <article className="legal">
      <header className="legal-hd">
        <div className="eyebrow violet">Legal</div>
        <h1 className="legal-ttl">{title}</h1>
        <p className="legal-sub">{subtitle}</p>
        <p className="legal-updated">Last updated: {LAST_UPDATED}</p>
      </header>

      <div className="legal-body">
        {sections.map((s, i) => (
          <section className="legal-section" key={i}>
            <h2 className="legal-h2">
              <span className="legal-num">{String(i + 1).padStart(2, "0")}</span>
              {s.heading}
            </h2>
            {s.body.map((p, j) => (
              <p className="legal-p" key={j}>
                {p}
              </p>
            ))}
          </section>
        ))}

        <div className="legal-contact">
          <p className="legal-p">
            Questions about this document? Contact us at{" "}
            <a href="mailto:legal@sanket.app" className="legal-link">
              legal@sanket.app
            </a>{" "}
            or write to SANKET Technologies, Inc., 500 Howard Street, San Francisco, CA 94105.
          </p>
          <div className="legal-xlinks">
            <Link to="/terms" className="legal-link">Terms of Service</Link>
            <Link to="/privacy" className="legal-link">Privacy Policy</Link>
            <Link to="/" className="legal-link">Home</Link>
          </div>
        </div>
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
