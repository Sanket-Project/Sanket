import { AnimatePresence, motion } from "framer-motion";
import { ArrowLeft, LogOut } from "lucide-react";
import {
  useCallback,
  useMemo,
  useRef,
  useState,
  type ForwardRefExoticComponent,
  type RefAttributes,
} from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { onboardingApi } from "@/api/onboarding";
import { Button } from "@/components/ui/Button";
import { Stepper, type StepperItem } from "@/components/ui/Stepper";
import { useAuthStore } from "@/stores/auth";
import type { OnboardingStateUpdate, OnboardingStepKey } from "@/types/api";

import { StepBaseline } from "./StepBaseline";
import { StepCalendar } from "./StepCalendar";
import { StepData } from "./StepData";
import { StepIndustry } from "./StepIndustry";
import { StepTeam } from "./StepTeam";
import type { SaveProgress, StepHandle, StepProps } from "./types";

type StepComponent = ForwardRefExoticComponent<StepProps & RefAttributes<StepHandle>>;

interface StepDef extends StepperItem {
  key: OnboardingStepKey;
  cta: string;
  optional?: boolean;
  component: StepComponent;
  heading: string;
  subheading: string;
}

const STEPS: StepDef[] = [
  {
    key: "industry",
    label: "Industry",
    description: "Primary vertical",
    cta: "Continue",
    component: StepIndustry,
    heading: "Choose your industry",
    subheading: "This tunes forecasting horizons, demand signals, and compliance defaults.",
  },
  {
    key: "data",
    label: "Data",
    description: "Catalog & history",
    cta: "Continue",
    optional: true,
    component: StepData,
    heading: "Bring in your data",
    subheading: "Import your catalog and sales history, or connect a live source later.",
  },
  {
    key: "calendar",
    label: "Planning calendar",
    description: "Periods & rules",
    cta: "Save & continue",
    component: StepCalendar,
    heading: "Set your planning calendar",
    subheading: "Define how your planning cycle and forecasting rules work.",
  },
  {
    key: "team",
    label: "Team",
    description: "Invite colleagues",
    cta: "Continue",
    optional: true,
    component: StepTeam,
    heading: "Invite your team",
    subheading: "Bring in planners, ops, and reviewers. You can always do this later.",
  },
  {
    key: "baseline",
    label: "Baseline forecast",
    description: "First plan",
    cta: "Finish setup",
    component: StepBaseline,
    heading: "Generate your first plan",
    subheading: "Run a baseline forecast — the starting point for your team's planning.",
  },
];

const STEP_KEYS = STEPS.map((s) => s.key);

export const OnboardingPage = () => {
  const navigate = useNavigate();
  const onboarding = useAuthStore((s) => s.onboarding);
  const setOnboarding = useAuthStore((s) => s.setOnboarding);
  const logout = useAuthStore((s) => s.logout);

  // Resume at the server's current step (clamped to a real step).
  const initialKey: OnboardingStepKey = useMemo(() => {
    const k = onboarding?.current_step;
    return k && STEP_KEYS.includes(k) ? k : "industry";
  }, [onboarding?.current_step]);

  const [activeKey, setActiveKey] = useState<OnboardingStepKey>(initialKey);
  const [busy, setBusy] = useState(false);
  const [canContinue, setCanContinue] = useState(true);
  const stepRef = useRef<StepHandle>(null);

  const save: SaveProgress = useCallback(
    async (body: OnboardingStateUpdate) => {
      const next = await onboardingApi.updateState(body);
      setOnboarding(next);
      return next;
    },
    [setOnboarding],
  );

  // Already set up (or legacy/demo tenant) — nothing to onboard.
  if (!onboarding || onboarding.status === "complete" || onboarding.status === "skipped") {
    return <Navigate to="/workspace" replace />;
  }

  const activeIndex = STEPS.findIndex((s) => s.key === activeKey);
  const active = STEPS[activeIndex];
  const nextStep = STEPS[activeIndex + 1]?.key;
  const completed = new Set(
    STEP_KEYS.filter((k) => (onboarding.steps?.[k]?.done ? true : false)),
  );
  const progress = Math.round((completed.size / STEPS.length) * 100);

  const ActiveComponent = active.component;

  const handleContinue = async () => {
    setBusy(true);
    try {
      const ok = await stepRef.current?.submit();
      if (!ok) return;
      if (!nextStep) {
        navigate("/workspace", { replace: true });
        return;
      }
      setActiveKey(nextStep);
      setCanContinue(true);
    } finally {
      setBusy(false);
    }
  };

  const handleSkipStep = async () => {
    if (!nextStep) return;
    setBusy(true);
    try {
      await save({ current_step: nextStep });
      setActiveKey(nextStep);
      setCanContinue(true);
    } finally {
      setBusy(false);
    }
  };

  const handleSkipAll = async () => {
    setBusy(true);
    try {
      await save({ status: "skipped" });
      navigate("/workspace", { replace: true });
    } finally {
      setBusy(false);
    }
  };

  const goBack = () => {
    const prev = STEPS[activeIndex - 1]?.key;
    if (prev) {
      setActiveKey(prev);
      setCanContinue(true);
    }
  };

  return (
    <div className="flex min-h-screen bg-canvas">
      {/* ── Rail ── */}
      <aside className="hidden w-[320px] shrink-0 flex-col justify-between border-r border-line bg-surface px-8 py-9 lg:flex">
        <div>
          <div className="mb-9 flex items-center gap-2.5">
            <div className="grid h-9 w-9 place-items-center rounded-xl bg-accent">
              <span className="font-heading text-lg font-bold text-accent-fg">P</span>
            </div>
            <span className="font-heading text-lg font-bold tracking-tight text-content">SANKET</span>
          </div>

          <p className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-content-subtle">
            Set up your workspace
          </p>
          <p className="mb-7 text-sm leading-relaxed text-content-muted">
            A few steps to your first plan.
          </p>

          <Stepper
            steps={STEPS}
            current={activeKey}
            completed={completed}
            onStepClick={(k) => {
              const key = k as OnboardingStepKey;
              if (completed.has(key) || key === activeKey) setActiveKey(key);
            }}
          />
        </div>

        <button
          type="button"
          onClick={() => logout()}
          className="inline-flex items-center gap-2 text-xs font-medium text-content-subtle tactile-press hover:text-content"
        >
          <LogOut size={14} aria-hidden="true" />
          Sign out
        </button>
      </aside>

      {/* ── Main ── */}
      <main className="flex min-w-0 flex-1 flex-col">
        {/* progress meter */}
        <div className="h-1 w-full bg-surface-3">
          <div
            className="h-full bg-accent transition-[width] duration-500 ease-out"
            style={{ width: `${progress}%` }}
            role="progressbar"
            aria-valuenow={progress}
            aria-valuemin={0}
            aria-valuemax={100}
          />
        </div>

        <div className="mx-auto flex w-full max-w-2xl flex-1 flex-col px-6 py-10 sm:px-8">
          {/* header */}
          <div className="mb-7">
            <div className="mb-2 flex items-center justify-between">
              <span className="font-mono text-xs text-content-subtle">
                Step {activeIndex + 1} of {STEPS.length}
              </span>
              <button
                type="button"
                onClick={handleSkipAll}
                disabled={busy}
                className="text-xs font-medium text-content-subtle tactile-press hover:text-content"
              >
                Skip setup for now
              </button>
            </div>
            <h1 className="font-heading text-2xl font-bold tracking-tight text-content">
              {active.heading}
            </h1>
            <p className="mt-1.5 text-sm leading-relaxed text-content-muted">{active.subheading}</p>
          </div>

          {/* active step */}
          <div className="flex-1">
            <AnimatePresence mode="wait">
              <motion.div
                key={activeKey}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
              >
                <ActiveComponent
                  ref={stepRef}
                  thisStep={activeKey}
                  nextStep={nextStep}
                  save={save}
                  onValidityChange={setCanContinue}
                />
              </motion.div>
            </AnimatePresence>
          </div>

          {/* footer */}
          <div className="mt-9 flex items-center justify-between border-t border-line pt-5">
            <Button
              variant="ghost"
              onClick={goBack}
              disabled={activeIndex === 0 || busy}
              icon={<ArrowLeft size={15} aria-hidden="true" />}
            >
              Back
            </Button>
            <div className="flex items-center gap-2.5">
              {active.optional && nextStep && (
                <Button variant="secondary" onClick={handleSkipStep} disabled={busy}>
                  Skip
                </Button>
              )}
              <Button onClick={handleContinue} loading={busy} disabled={busy || !canContinue}>
                {active.cta}
              </Button>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
};
