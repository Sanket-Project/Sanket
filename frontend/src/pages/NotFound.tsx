import { Link } from "react-router-dom";
import { LogoMark } from "@/components/ui/Logo";

export const NotFoundPage = () => (
  <main className="grid min-h-dvh place-items-center bg-canvas px-6 py-12 text-content">
    <section className="w-full max-w-md rounded-2xl border border-line bg-surface p-8 text-center shadow-sm">
      <LogoMark size={40} className="mx-auto" />
      <p className="mt-8 font-mono text-sm font-medium text-accent">404 · Page unavailable</p>
      <h1 className="mt-3 font-heading text-[28px] font-semibold text-content">Page not found</h1>
      <p className="mt-3 text-sm leading-relaxed text-content-muted">The page you're looking for doesn't exist or has been moved.</p>
      <div className="mt-7 flex flex-wrap justify-center gap-3">
        <Link to="/" className="btn-secondary">Go home</Link>
        <Link to="/workspace" className="btn-primary">Dashboard</Link>
      </div>
    </section>
  </main>
);
