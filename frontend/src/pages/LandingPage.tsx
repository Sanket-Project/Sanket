import React, { useEffect, useRef, useState, useCallback } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  motion,
  AnimatePresence,
  useScroll,
  useInView,
  useTransform,
  useSpring,
} from "framer-motion";
import axios from "axios";
import toast from "react-hot-toast";
import {
  X,
  ArrowRight,
  Check,
  RefreshCw,
  Shirt,
  AlertCircle,
  Menu,
} from "@/components/ui/icons";
import { useAuthStore } from "@/stores/auth";
import { LogoMark } from "@/components/ui/Logo";
import { getErrorMessage } from "@/utils/errors";
import { LiveConsoleLanding } from "./landing/LiveConsoleLanding";



const inputCls =
  "w-full rounded-none border-0 border-b border-white/15 bg-transparent px-0 py-2.5 text-sm text-white placeholder-white/25 outline-none transition focus:border-[#DEDBC8]/60 focus:ring-0";

/** Tracks the user's `prefers-reduced-motion` setting (live). When true we skip
 * the particle canvas, the intro loader, and autoplaying video. */
const usePrefersReducedMotion = (): boolean => {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(mq.matches);
    const onChange = (e: MediaQueryListEvent) => setReduced(e.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return reduced;
};


// ─────────────────────────────────────────────────────────────────────────────
// UPGRADE 1 · Cinematic Intro Loader
// ─────────────────────────────────────────────────────────────────────────────
const IntroLoader = ({ onDone }: { onDone: () => void }) => {
  useEffect(() => {
    // Marketing page: keep the intro under a second so content isn't gated.
    const t = setTimeout(onDone, 900);
    return () => clearTimeout(t);
  }, [onDone]);

  return (
    <motion.div
      onClick={onDone}
      role="button"
      tabIndex={0}
      aria-label="Skip intro"
      className="fixed inset-0 z-[200] flex items-center justify-center bg-black cursor-pointer"
      exit={{ opacity: 0 }}
      transition={{ duration: 0.4, ease: [0.76, 0, 0.24, 1] }}
    >
      {/* Horizontal wipe curtains */}
      <motion.div
        className="absolute inset-0 bg-black origin-left"
        initial={{ scaleX: 1 }}
        animate={{ scaleX: 0 }}
        transition={{ duration: 0.7, ease: [0.76, 0, 0.24, 1], delay: 1.4 }}
      />
      {/* Logo */}
      <div className="relative flex flex-col items-center gap-4">
        <motion.div
          initial={{ opacity: 0, scale: 0.8, y: 12 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
        >
          <LogoMark
            size={56}
            variant="bare"
            curveColor="#E8E5D0"
            className="mb-1"
          />
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 20, letterSpacing: "0.6em" }}
          animate={{ opacity: 1, y: 0, letterSpacing: "0.35em" }}
          transition={{ duration: 0.9, ease: [0.16, 1, 0.3, 1], delay: 0.2 }}
          style={{ fontFamily: "'DM Serif Display', serif" }}
          className="text-5xl sm:text-7xl font-light text-[#E8E5D0]"
        >
          SANKET
        </motion.div>
        <motion.div
          initial={{ scaleX: 0 }}
          animate={{ scaleX: 1 }}
          transition={{ duration: 0.9, ease: [0.16, 1, 0.3, 1], delay: 0.55 }}
          className="h-px w-24 bg-[#DEDBC8]/30 origin-left"
        />
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.6, delay: 0.9 }}
          className="font-mono text-[9px] tracking-[0.4em] text-[#DEDBC8]/30 uppercase"
        >
          Predictive Intelligence
        </motion.p>
      </div>
    </motion.div>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// UPGRADE 3 · Scroll Progress Bar
// ─────────────────────────────────────────────────────────────────────────────
const ScrollProgress = () => {
  const { scrollYProgress } = useScroll();
  const scaleX = useSpring(scrollYProgress, { stiffness: 100, damping: 30 });
  return (
    <motion.div
      style={{ scaleX, transformOrigin: "left" }}
      className="fixed top-0 left-0 right-0 h-[1.5px] z-[150] bg-gradient-to-r from-[#DEDBC8]/60 via-[#DEDBC8] to-[#DEDBC8]/60"
    />
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// LIVE TICKER
// ─────────────────────────────────────────────────────────────────────────────
const LiveTicker = () => {
  const actions = [
    "Synced 1,420 new sales — inventory positions updated across all locations.",
    "Refreshed demand forecasts for 8,200 SKUs ahead of next week's planning.",
    "Shortage alert: SKU-8820 is down to 4 days of cover — reorder ready to approve.",
  ];
  const [idx, setIdx] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setIdx((p) => (p + 1) % actions.length), 4500);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="absolute bottom-0 left-0 right-0 z-30 flex items-center gap-4 border-t border-white/[0.06] bg-black/50 backdrop-blur-xl px-6 md:px-10 py-3">
      <div className="flex items-center gap-2 shrink-0">
        <span className="relative flex h-1.5 w-1.5">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
          <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-500" />
        </span>
        <span className="font-mono text-xs tracking-[0.2em] text-[#DEDBC8]/80 uppercase">Live activity</span>
      </div>
      <div className="w-px h-3 bg-white/10 shrink-0" />
      <div className="flex-1 overflow-hidden relative h-3.5">
        <AnimatePresence mode="wait">
          <motion.span
            key={idx}
            initial={{ y: 10, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: -10, opacity: 0 }}
            transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
            className="absolute left-0 font-mono text-xs text-white/75 tracking-wide truncate w-full"
          >
            {actions[idx]}
          </motion.span>
        </AnimatePresence>
      </div>
    </div>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// PULL UP WORDS
// ─────────────────────────────────────────────────────────────────────────────
const PullUp = ({
  text, className = "", delay = 0, showAsterisk = false, color = "#E8E5D0",
}: { text: string; className?: string; delay?: number; showAsterisk?: boolean; color?: string }) => {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true });
  const words = text.split(" ");
  return (
    <span ref={ref} className={`inline-flex flex-wrap ${className}`}>
      {words.map((word, i) => {
        const isLast = i === words.length - 1;
        return (
          <span key={i} className="overflow-hidden inline-block mr-[0.22em] last:mr-0">
            <motion.span
              className="inline-block relative"
              style={{ color }}
              initial={{ y: "110%", opacity: 0 }}
              animate={inView ? { y: "0%", opacity: 1 } : {}}
              transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1], delay: delay + i * 0.07 }}
            >
              {word}
              {isLast && showAsterisk && (
                <sup className="absolute top-[0.7em] -right-[0.25em] text-[0.28em] font-light opacity-60">*</sup>
              )}
            </motion.span>
          </span>
        );
      })}
    </span>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// FLOATING PARTICLES (Hero Canvas)
// ─────────────────────────────────────────────────────────────────────────────
const FloatingParticles = () => {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animationFrameId: number;
    const particles: Array<{
      x: number;
      y: number;
      size: number;
      speedX: number;
      speedY: number;
      opacity: number;
    }> = [];

    const resize = () => {
      canvas.width = canvas.parentElement?.clientWidth || window.innerWidth;
      canvas.height = canvas.parentElement?.clientHeight || window.innerHeight;
    };

    resize();
    window.addEventListener("resize", resize);

    const particleCount = 25;
    for (let i = 0; i < particleCount; i++) {
      particles.push({
        x: Math.random() * canvas.width,
        y: Math.random() * canvas.height,
        size: Math.random() * 1.5 + 0.5,
        speedX: (Math.random() - 0.5) * 0.12,
        speedY: (Math.random() - 0.5) * 0.12 - 0.08,
        opacity: Math.random() * 0.4 + 0.1,
      });
    }

    const draw = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      particles.forEach((p) => {
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(222, 219, 200, ${p.opacity})`;
        ctx.fill();

        p.x += p.speedX;
        p.y += p.speedY;

        if (p.x < 0) p.x = canvas.width;
        if (p.x > canvas.width) p.x = 0;
        if (p.y < 0) p.y = canvas.height;
        if (p.y > canvas.height) p.y = 0;
      });

      animationFrameId = requestAnimationFrame(draw);
    };

    draw();

    return () => {
      window.removeEventListener("resize", resize);
      cancelAnimationFrame(animationFrameId);
    };
  }, []);

  return <canvas ref={canvasRef} className="absolute inset-0 pointer-events-none w-full h-full z-0 opacity-50" />;
};

// ─────────────────────────────────────────────────────────────────────────────
// PLATFORM TOUR
// ─────────────────────────────────────────────────────────────────────────────

// ─────────────────────────────────────────────────────────────────────────────
// MAIN PAGE
// ─────────────────────────────────────────────────────────────────────────────
export const LandingPage = () => {
  const navigate = useNavigate();
  const loginSandbox = useAuthStore((s) => s.loginSandbox);

  const [modal, setModal] = useState<null | "book" | "sandbox">(null);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [formLoading, setFormLoading] = useState(false);
  const [formSuccess, setFormSuccess] = useState(false);
  const [launching, setLaunching] = useState(false);
  const [sandboxError, setSandboxError] = useState<string | null>(null);
  const [showLoader, setShowLoader] = useState(() => !sessionStorage.getItem("sanket_visited"));
  const [lead, setLead] = useState({
    name: "", email: "", company: "", industry: "fashion", tier: "growth", message: "",
  });

  const reducedMotion = usePrefersReducedMotion();
  const modalRef = useRef<HTMLDivElement>(null);
  const isModalOpen = modal !== null;


  // Hero parallax: the background video drifts down and zooms slightly as the
  // hero scrolls out, so foreground copy appears to float above it.
  const heroRef = useRef(null);
  const { scrollYProgress: heroProg } = useScroll({
    target: heroRef,
    offset: ["start start", "end start"],
    layoutEffect: false,
  });
  const heroY = useTransform(heroProg, [0, 1], [0, 110]);
  const heroScale = useTransform(heroProg, [0, 1], [1, 1.15]);
  const heroContentOpacity = useTransform(heroProg, [0, 0.75], [1, 0.15]);

  const handleLoaderDone = useCallback(() => {
    sessionStorage.setItem("sanket_visited", "1");
    setShowLoader(false);
  }, []);

  // Respect reduced-motion: never gate content behind the intro animation.
  useEffect(() => {
    if (reducedMotion && showLoader) handleLoaderDone();
  }, [reducedMotion, showLoader, handleLoaderDone]);

  useEffect(() => {
    if (!isModalOpen) return;

    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const focusTimer = window.setTimeout(() => {
      modalRef.current?.querySelector<HTMLElement>("[data-modal-initial]")?.focus();
    }, 0);

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setModal(null);
        return;
      }

      if (event.key !== "Tab" || !modalRef.current) return;
      const focusable = Array.from(
        modalRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href]',
        ),
      );
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];

      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      window.clearTimeout(focusTimer);
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
      previousFocus?.focus();
    };
  }, [isModalOpen]);


  const submitDemo = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormLoading(true);
    try {
      await axios.post("/api/v1/demo-requests", lead);
      setFormSuccess(true);
      toast.success("Demo request submitted!");
      setLead({ name: "", email: "", company: "", industry: "fashion", tier: "growth", message: "" });
    } catch { toast.error("Failed to submit. Please try again."); }
    finally { setFormLoading(false); }
  };

  const launchSandbox = async () => {
    setLaunching(true);
    setSandboxError(null);
    try {
      // Auth runs server-side via /auth/sandbox-session — no demo credentials
      // are shipped in the client bundle. The industry comes back on the
      // session; the visitor no longer picks one, because the old picker only
      // set client state while every visitor landed in the same workspace.
      await loginSandbox();
      toast.success(`Sandbox launched!`);
      setModal(null);
      navigate("/workspace", { replace: true });
    } catch (error) {
      const message = getErrorMessage(
        error,
        "Sandbox is temporarily unavailable. Please try again shortly.",
      );
      setSandboxError(message);
      toast.error(message);
    }
    finally { setLaunching(false); }
  };

  const goToSection = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });
    setMobileMenuOpen(false);
  };
  // Every id here must exist as a section on the page. The Pricing link that
  // used to sit in this list pointed at #pricing, which was the id on a
  // statistics band — it had been written for a legacy page that did have
  // pricing and stopped rendering when that went behind a flag.
  const sectionLinks = [
    { label: "Platform", id: "platform" },
    { label: "Industries", id: "industries" },
    { label: "How It Works", id: "how-it-works" },
  ];

  return (
    <div className="landing-root bg-[#060606] min-h-screen overflow-x-hidden relative">

      <style>{`
        ::selection { background: rgba(222,219,200,0.12); color: #E8E5D0; }
        .grid-bg {
          background-image:
            linear-gradient(to right, rgba(222,219,200,0.025) 1px, transparent 1px),
            linear-gradient(to bottom, rgba(222,219,200,0.025) 1px, transparent 1px);
          background-size: 80px 80px;
        }
        .glow-line { background: linear-gradient(90deg, transparent, rgba(222,219,200,0.3), transparent); }
        @keyframes marquee {
          from { transform: translateX(0); }
          to { transform: translateX(-50%); }
        }
        .trust-marquee:hover .marquee-row { animation-play-state: paused !important; }
        @keyframes auroraDrift {
          0%   { transform: translate3d(0, 0, 0) scale(1); }
          50%  { transform: translate3d(-2%, 1.5%, 0) scale(1.06); }
          100% { transform: translate3d(0, 0, 0) scale(1); }
        }
        .aurora-layer { animation: auroraDrift 26s ease-in-out infinite; }
        html { scroll-behavior: smooth; }
        @media (prefers-reduced-motion: reduce) {
          *, *::before, *::after {
            animation-duration: 0.001ms !important;
            animation-iteration-count: 1 !important;
            transition-duration: 0.001ms !important;
            scroll-behavior: auto !important;
          }
          .aurora-layer { animation: none !important; }
        }
        ::-webkit-scrollbar { width: 3px; background: #060606; }
        ::-webkit-scrollbar-thumb { background: rgba(222,219,200,0.12); border-radius: 10px; }
        ::-webkit-scrollbar-thumb:hover { background: rgba(222,219,200,0.25); }
      `}</style>

      {/* ── Ambient page background (aurora glows + masked grid) ── */}
      <div className="fixed inset-0 -z-10 pointer-events-none overflow-hidden">
        <div
          className="aurora-layer absolute inset-[-15%]"
          style={{
            background:
              "radial-gradient(38% 30% at 16% 6%, rgba(222,219,200,0.08) 0%, transparent 60%)," +
              "radial-gradient(44% 34% at 86% 18%, rgba(99,102,241,0.10) 0%, transparent 60%)," +
              "radial-gradient(42% 34% at 12% 46%, rgba(124,58,237,0.07) 0%, transparent 60%)," +
              "radial-gradient(48% 40% at 88% 64%, rgba(8,145,178,0.07) 0%, transparent 60%)," +
              "radial-gradient(46% 40% at 30% 90%, rgba(222,219,200,0.06) 0%, transparent 60%)",
          }}
        />
        <div
          className="grid-bg absolute inset-0 opacity-100"
          style={{
            maskImage: "linear-gradient(to bottom, transparent 0%, #000 6%, #000 94%, transparent 100%)",
            WebkitMaskImage: "linear-gradient(to bottom, transparent 0%, #000 6%, #000 94%, transparent 100%)",
          }}
        />
      </div>

      {/* ── Loader ── */}
      <AnimatePresence>
        {showLoader && !reducedMotion && <IntroLoader onDone={handleLoaderDone} />}
      </AnimatePresence>

      {/* ── Scroll Progress ── */}
      <ScrollProgress />

      {/* ══════════════════════ NAV ══════════════════════ */}
      <header className="fixed top-0 left-0 right-0 z-50 flex flex-col items-center pt-5">
        <motion.nav
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1], delay: showLoader ? 1.0 : 0 }}
          className="flex items-center gap-1 bg-[#090F0E]/85 backdrop-blur-2xl border border-white/[0.10] rounded-full px-2 py-2 shadow-[0_10px_32px_rgba(0,0,0,0.16)]"
        >
          <span className="font-mono text-xs tracking-[0.3em] text-[#DEDBC8]/80 uppercase px-4">SANKET</span>
          <div className="w-px h-3 bg-white/10 mx-1" />

          {/* Desktop section links */}
          {sectionLinks.map((l) => (
            <button
              key={l.id}
              onClick={() => goToSection(l.id)}
              className="hidden md:inline-block px-4 py-1.5 rounded-full text-xs font-medium tracking-wide text-white/65 hover:text-white hover:bg-white/[0.05] transition-all duration-200"
            >
              {l.label}
            </button>
          ))}

          {/* The four public entry points: sandbox, self-service signup,
              enterprise demo, sign in. Sandbox lives in the hero and the
              pricing table; the other three are here. */}
          <button
            onClick={() => navigate("/login")}
            className="hidden md:inline-block px-4 py-1.5 rounded-full text-xs font-medium tracking-wide text-white/65 hover:text-white hover:bg-white/[0.05] transition-all duration-200"
          >
            Sign In
          </button>

          <button
            onClick={() => navigate("/login?mode=signup")}
            className="hidden md:inline-block px-4 py-1.5 rounded-full text-xs font-medium tracking-wide text-white/65 hover:text-white hover:bg-white/[0.05] transition-all duration-200"
          >
            Create Workspace
          </button>

          {/* Primary CTA */}
          <button
            onClick={() => setModal("book")}
            className="px-4 py-1.5 rounded-full text-xs font-medium tracking-wide bg-[#DEDBC8] text-black hover:bg-[#E8E5D0] ml-1 transition-all duration-200 active:scale-95 hover:shadow-[0_4px_20px_-4px_rgba(222,219,200,0.5)]"
          >
            Request Enterprise Demo
          </button>

          {/* Mobile menu toggle */}
          <button
            onClick={() => setMobileMenuOpen((o) => !o)}
            aria-label={mobileMenuOpen ? "Close menu" : "Open menu"}
            aria-expanded={mobileMenuOpen}
            className="md:hidden w-8 h-8 rounded-full flex items-center justify-center text-white/70 hover:text-white hover:bg-white/[0.06] transition-all duration-200 ml-1"
          >
            {mobileMenuOpen ? <X size={16} /> : <Menu size={16} />}
          </button>
        </motion.nav>

        {/* Mobile dropdown menu */}
        <AnimatePresence>
          {mobileMenuOpen && (
            <motion.div
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.2 }}
              className="md:hidden mt-2 w-[min(92vw,320px)] flex flex-col bg-[#0A0A0A]/95 backdrop-blur-2xl border border-white/[0.08] rounded-2xl p-2 shadow-2xl"
            >
              {sectionLinks.map((l) => (
                <button
                  key={l.id}
                  onClick={() => goToSection(l.id)}
                  className="text-left px-4 py-3 rounded-xl text-sm font-medium text-white/80 hover:text-white hover:bg-white/[0.05] transition-all duration-200"
                >
                  {l.label}
                </button>
              ))}
              <button
                onClick={() => { setMobileMenuOpen(false); navigate("/login"); }}
                className="text-left px-4 py-3 rounded-xl text-sm font-medium text-white/80 hover:text-white hover:bg-white/[0.05] transition-all duration-200"
              >
                Sign In
              </button>
              <button
                onClick={() => { setMobileMenuOpen(false); navigate("/login?mode=signup"); }}
                className="text-left px-4 py-3 rounded-xl text-sm font-medium text-white/80 hover:text-white hover:bg-white/[0.05] transition-all duration-200"
              >
                Create Workspace
              </button>
              <button
                onClick={() => { setMobileMenuOpen(false); setModal("sandbox"); }}
                className="text-left px-4 py-3 rounded-xl text-sm font-medium text-white/80 hover:text-white hover:bg-white/[0.05] transition-all duration-200"
              >
                Try Live Sandbox
              </button>
              <button
                onClick={() => { setMobileMenuOpen(false); setModal("book"); }}
                className="mt-1 text-center px-4 py-3 rounded-xl text-sm font-semibold bg-[#DEDBC8] text-black hover:bg-[#E8E5D0] transition-all duration-200"
              >
                Request Enterprise Demo
              </button>
            </motion.div>
          )}
        </AnimatePresence>
      </header>

      {/* ══════════════════════ HERO ══════════════════════ */}
      <section id="hero" ref={heroRef} className="relative h-screen p-3 md:p-5">
        <div className="relative h-full rounded-2xl md:rounded-3xl overflow-hidden flex flex-col justify-end">
          {reducedMotion ? (
            <img
              src={`${import.meta.env.BASE_URL}assets/predictive_model.png`}
              alt=""
              className="absolute inset-0 w-full h-full object-cover"
            />
          ) : (
            <>
              <motion.div style={{ y: heroY, scale: heroScale }} className="absolute inset-0">
                <video
                  src="https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260405_170732_8a9ccda6-5cff-4628-b164-059c500a2b41.mp4"
                  autoPlay loop muted playsInline
                  poster={`${import.meta.env.BASE_URL}assets/predictive_model.png`}
                  preload="metadata"
                  className="absolute inset-0 w-full h-full object-cover"
                />
              </motion.div>
              <FloatingParticles />
            </>
          )}
          <div className="absolute inset-0 bg-gradient-to-t from-black via-black/25 to-black/45" />
          <div className="absolute inset-0 bg-gradient-to-r from-black/70 via-transparent to-transparent" />
          <div className="noise-overlay opacity-[0.5] mix-blend-overlay pointer-events-none absolute inset-0" />

          <motion.div
            style={reducedMotion ? undefined : { opacity: heroContentOpacity }}
            className="relative z-10 p-6 sm:p-10 md:p-16 pb-20 sm:pb-24"
          >
            <motion.div
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.8, delay: showLoader ? 2.3 : 0.2 }}
              className="flex items-center gap-3 mb-8"
            >
              <div className="w-6 h-px bg-[#DEDBC8]/50" />
              <span className="font-mono text-xs tracking-[0.3em] text-[#DEDBC8]/70 uppercase">
                AI Demand Forecasting for Supply Chains
              </span>
            </motion.div>

            <div className="mb-10 max-w-4xl">
              <h1 className="font-light leading-[0.95] tracking-[-0.02em]"
                style={{
                  fontFamily: "'DM Serif Display', serif",
                  fontSize: "clamp(2.5rem, 7vw, 5.5rem)",
                  color: "#E8E5D0",
                }}>
                <PullUp text="Stop guessing demand." delay={showLoader ? 1.3 : 0.1} color="#E8E5D0"
                  className="text-[length:inherit] leading-[inherit] tracking-[inherit]" />
                <br />
                <span className="italic opacity-70">
                  <PullUp text="Forecast every SKU." delay={showLoader ? 1.45 : 0.25} color="#E8E5D0"
                    className="text-[length:inherit] leading-[inherit] tracking-[inherit]" />
                </span>
              </h1>
            </div>

            <div className="flex flex-col sm:flex-row items-start sm:items-end gap-6 sm:gap-12">
              <motion.p
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1], delay: showLoader ? 1.7 : 0.6 }}
                className="max-w-md text-base font-light tracking-wide leading-relaxed"
                style={{ color: "rgba(232,229,208,0.9)" }}
              >
                One focused planning workspace, configured for your industry from
                day one. SANKET turns your sales, inventory, and live market
                signals into one forecasting engine — so you order the right
                stock, cut markdowns, and never get caught short.
              </motion.p>

              <motion.button
                onClick={() => setModal("sandbox")}
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1], delay: showLoader ? 1.85 : 0.75 }}
                className="group flex items-center gap-0 overflow-hidden border border-[#DEDBC8]/25 hover:border-[#DEDBC8]/60 transition-all duration-500 rounded-full bg-black/20 backdrop-blur-sm"
              >
                <span className="px-6 py-3 text-xs font-medium tracking-widest uppercase text-[#E8E5D0]/85 group-hover:text-[#E8E5D0] transition-colors duration-300">
                  Try Live Sandbox
                </span>
                <div className="w-10 h-10 rounded-full border-l border-[#DEDBC8]/15 flex items-center justify-center group-hover:bg-[#DEDBC8]/15 transition-all duration-300">
                  <ArrowRight className="w-3.5 h-3.5 text-[#E8E5D0]/50 group-hover:text-[#E8E5D0] group-hover:translate-x-0.5 transition-all duration-300" />
                </div>
              </motion.button>
            </div>
          </motion.div>
          <LiveTicker />
        </div>
      </section>

      <LiveConsoleLanding
        onBook={() => setModal("book")}
        onSandbox={() => setModal("sandbox")}
      />

      {/* ══════════════════════ FOOTER ══════════════════════ */}
      <footer className="bg-[#060606] border-t border-white/[0.05] py-16 px-8">
        <div className="max-w-6xl mx-auto">
          <div className="grid grid-cols-2 md:grid-cols-5 gap-10 md:gap-8">
            {/* Brand */}
            <div className="col-span-2 md:col-span-1">
              <div className="flex items-center gap-2.5">
                <LogoMark size={28} variant="bare" curveColor="#BDD9D7" />
                <span className="font-mono text-xs tracking-[0.35em] text-white/70 uppercase">SANKET</span>
              </div>
              <p className="text-sm text-white/55 leading-relaxed mt-3 max-w-[180px]">
                Demand forecasting for supply chain teams.
              </p>
            </div>

            {/* Product */}
            <div>
              <h3 className="font-mono text-[11px] tracking-[0.25em] text-white/45 uppercase mb-4">Product</h3>
              <ul className="flex flex-col gap-2.5 text-sm text-white/65">
                <li><button onClick={() => goToSection("features")} className="hover:text-[#DEDBC8] transition-colors">Platform</button></li>
                <li><button onClick={() => goToSection("how-it-works")} className="hover:text-[#DEDBC8] transition-colors">How it works</button></li>
                <li><button onClick={() => goToSection("pricing")} className="hover:text-[#DEDBC8] transition-colors">Pricing</button></li>
                <li><button onClick={() => setModal("sandbox")} className="hover:text-[#DEDBC8] transition-colors">Try the sandbox</button></li>
              </ul>
            </div>

            {/* Resources */}
            <div>
              <h3 className="font-mono text-[11px] tracking-[0.25em] text-white/45 uppercase mb-4">Resources</h3>
              <ul className="flex flex-col gap-2.5 text-sm text-white/65">
                <li><button onClick={() => goToSection("architecture")} className="hover:text-[#DEDBC8] transition-colors">Architecture</button></li>
                <li><button onClick={() => goToSection("testimonials")} className="hover:text-[#DEDBC8] transition-colors">Customers</button></li>
                <li><button onClick={() => setModal("book")} className="hover:text-[#DEDBC8] transition-colors">Book a demo</button></li>
                <li><button onClick={() => navigate("/login")} className="hover:text-[#DEDBC8] transition-colors">Sign in</button></li>
              </ul>
            </div>

            {/* Security & Compliance */}
            <div>
              <h3 className="font-mono text-[11px] tracking-[0.25em] text-white/45 uppercase mb-4">Security &amp; Compliance</h3>
              <ul className="flex flex-col gap-2.5 text-sm text-white/65">
                <li><button onClick={() => goToSection("architecture")} className="hover:text-[#DEDBC8] transition-colors">Security overview</button></li>
                <li><span className="text-white/45">Tenant data isolation</span></li>
                <li><span className="text-white/45">GxP audit trails</span></li>
                <li><Link to="/privacy" className="hover:text-[#DEDBC8] transition-colors">Privacy policy</Link></li>
              </ul>
            </div>

            {/* Company */}
            <div>
              <h3 className="font-mono text-[11px] tracking-[0.25em] text-white/45 uppercase mb-4">Company</h3>
              <ul className="flex flex-col gap-2.5 text-sm text-white/65">
                <li><button onClick={() => goToSection("about")} className="hover:text-[#DEDBC8] transition-colors">About</button></li>
                <li><button onClick={() => setModal("book")} className="hover:text-[#DEDBC8] transition-colors">Contact</button></li>
                <li><Link to="/terms" className="hover:text-[#DEDBC8] transition-colors">Terms of service</Link></li>
                <li><Link to="/privacy" className="hover:text-[#DEDBC8] transition-colors">Privacy</Link></li>
              </ul>
            </div>
          </div>

          <div className="mt-14 pt-8 border-t border-white/[0.05] flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
            <div className="font-mono text-[10px] text-white/45 tracking-[0.2em] uppercase">© 2026 SANKET Technologies — All rights reserved</div>
            <div className="font-mono text-[10px] text-white/40 tracking-[0.2em] uppercase">Built for Fashion · Electronics · Pharma · Hardware · Agrocenter</div>
          </div>
        </div>
      </footer>

      {/* ══════════════════════ MODAL ══════════════════════ */}
      <AnimatePresence>
        {modal && (
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            onClick={() => setModal(null)}
            className="fixed inset-0 z-[120] flex items-center justify-center bg-black/70 p-4 backdrop-blur-xl"
          >
            <motion.div
              ref={modalRef}
              role="dialog"
              aria-modal="true"
              aria-labelledby="landing-modal-title"
              initial={{ opacity: 0, y: 20, scale: 0.97 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 20, scale: 0.97 }}
              transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
              onClick={(e) => e.stopPropagation()}
              className="relative w-full max-w-md border border-white/[0.08] bg-[#0A0A0A] rounded-2xl p-7 shadow-2xl"
            >
              <button onClick={() => setModal(null)} aria-label="Close dialog" data-modal-initial
                className="absolute right-4 top-4 w-10 h-10 rounded-full border border-white/[0.08] flex items-center justify-center text-white/50 hover:text-white/80 hover:border-white/20 transition-all outline-none focus-visible:ring-2 focus-visible:ring-[#BDD9D7]/70">
                <X size={14} />
              </button>

              <div className="flex gap-4 mb-7 pb-5 border-b border-white/[0.06]">
                {(["book", "sandbox"] as const).map((t) => (
                  <button key={t} onClick={() => setModal(t)}
                    className={`font-mono text-[10px] tracking-[0.2em] uppercase transition-colors ${modal === t ? "text-[#DEDBC8]/80" : "text-white/45 hover:text-white/40"}`}>
                    {t === "book" ? "Book Demo" : "Sandbox"}
                  </button>
                ))}
              </div>

              {modal === "book" ? (
                formSuccess ? (
                  <div className="py-8 text-center">
                    <div className="w-12 h-12 rounded-full border border-[#DEDBC8]/20 flex items-center justify-center mx-auto mb-5 text-[#DEDBC8]/60"><Check size={20} /></div>
                    <h3 id="landing-modal-title" className="text-base font-light text-white/80 mb-2" style={{ fontFamily: "'DM Serif Display', serif" }}>Request Received</h3>
                    <p className="text-xs text-white/65 leading-relaxed">A specialist will reach out within one business day.</p>
                    <button onClick={() => setModal(null)} className="mt-6 w-full border border-white/[0.08] hover:border-white/20 text-white/30 hover:text-white/60 font-mono text-[10px] tracking-widest uppercase py-3 rounded-lg transition-all outline-none">Dismiss</button>
                  </div>
                ) : (
                  <form onSubmit={submitDemo} className="flex flex-col gap-5">
                    <h3 id="landing-modal-title" className="text-lg font-light text-white/80" style={{ fontFamily: "'DM Serif Display', serif" }}>Schedule a Technical Briefing</h3>
                    <div className="grid gap-5 sm:grid-cols-2">
                      <label className="block">
                        <span className="font-mono text-[9px] tracking-[0.2em] text-white/45 uppercase block mb-2">Full Name</span>
                        <input required value={lead.name} onChange={(e) => setLead({ ...lead, name: e.target.value })} className={inputCls} placeholder="Jane Doe" />
                      </label>
                      <label className="block">
                        <span className="font-mono text-[9px] tracking-[0.2em] text-white/45 uppercase block mb-2">Work Email</span>
                        <input type="email" required value={lead.email} onChange={(e) => setLead({ ...lead, email: e.target.value })} className={inputCls} placeholder="jane@company.com" />
                      </label>
                    </div>
                    <label className="block">
                      <span className="font-mono text-[9px] tracking-[0.2em] text-white/45 uppercase block mb-2">Company</span>
                      <input required value={lead.company} onChange={(e) => setLead({ ...lead, company: e.target.value })} className={inputCls} placeholder="Acme Corp" />
                    </label>
                    <label className="block">
                      <span className="font-mono text-[9px] tracking-[0.2em] text-white/45 uppercase block mb-2">Target Industry</span>
                      <select value={lead.industry} onChange={(e) => setLead({ ...lead, industry: e.target.value })} className={inputCls}>
                        <option value="fashion">Apparel & Fashion</option>
                        <option value="electronics">Consumer Electronics</option>
                        <option value="pharma">Pharmaceuticals</option>
                        <option value="agrocenter">Agrocenter & Farm Inputs</option>
                        <option value="hardware">Tools & Hardware</option>
                      </select>
                    </label>
                    <label className="block">
                      <span className="font-mono text-[9px] tracking-[0.2em] text-white/45 uppercase block mb-2">Message</span>
                      <textarea value={lead.message} onChange={(e) => setLead({ ...lead, message: e.target.value })} className={`${inputCls} h-14 resize-none`} placeholder="Your forecasting challenges..." />
                    </label>
                    <button type="submit" disabled={formLoading}
                      className="mt-1 w-full bg-[#DEDBC8] hover:bg-[#E8E5D0] text-black font-medium text-xs tracking-widest uppercase py-3.5 rounded-lg flex items-center justify-center gap-2 disabled:opacity-50 transition-all outline-none">
                      {formLoading ? "Sending…" : "Submit Request"} <ArrowRight size={12} />
                    </button>
                  </form>
                )
              ) : (
                <div className="flex flex-col gap-3">
                  <h3 id="landing-modal-title" className="text-lg font-light text-white/80 mb-1" style={{ fontFamily: "'DM Serif Display', serif" }}>Explore a Live Sandbox</h3>
                  <p className="font-mono text-[10px] tracking-wide text-white/45 mb-3">
                    A read-only Fashion &amp; Apparel workspace with sample data.
                    Your own workspace is scoped to the industry you choose when
                    you create it.
                  </p>
                  <button onClick={() => launchSandbox()} disabled={launching}
                    className="flex items-center justify-between border border-white/[0.06] hover:border-[#DEDBC8]/20 rounded-lg px-4 py-3 text-xs text-white/40 hover:text-white/70 transition-all disabled:opacity-40 outline-none">
                    <span className="flex items-center gap-3"><Shirt size={14} className="text-[#DEDBC8]/30" />Launch the sandbox</span>
                    <ArrowRight size={12} className="text-white/15" />
                  </button>
                  {launching && (
                    <div className="flex items-center justify-center gap-2 mt-2 text-[11px] font-mono text-[#DEDBC8]/40">
                      <RefreshCw size={12} className="animate-spin" /> Authenticating…
                    </div>
                  )}
                  {sandboxError && (
                    <div role="alert" className="flex items-start gap-2 rounded-lg border border-rose-400/20 bg-rose-400/[0.06] px-3 py-2.5 text-xs leading-relaxed text-rose-200/80">
                      <AlertCircle size={14} className="mt-0.5 shrink-0" aria-hidden="true" />
                      <span>{sandboxError}</span>
                    </div>
                  )}
                </div>
              )}

              <div className="mt-6 pt-4 border-t border-white/[0.06] flex items-center justify-between text-[10px] font-mono tracking-wider">
                <button onClick={() => { setModal(null); navigate("/login?mode=signup"); }} className="text-white/30 hover:text-white/60 transition-all uppercase outline-none">
                  Create Workspace
                </button>
                <div className="w-px h-2 bg-white/10" />
                <button onClick={() => { setModal(null); navigate("/login"); }} className="text-[#DEDBC8]/60 hover:text-[#DEDBC8] transition-all uppercase font-medium outline-none">
                  Existing customer? Sign in
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};
