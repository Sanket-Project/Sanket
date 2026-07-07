import type { OnboardingState, OnboardingStateUpdate } from "@/types/api";

/** Persists a partial onboarding update and returns the new server state. */
export type SaveProgress = (body: OnboardingStateUpdate) => Promise<OnboardingState>;

export interface StepProps {
  /** key of the step that follows this one (undefined on the last step). */
  nextStep?: OnboardingState["current_step"];
  thisStep: OnboardingState["current_step"];
  save: SaveProgress;
  /** signals the controller whether the primary action is currently allowed. */
  onValidityChange?: (canContinue: boolean) => void;
}

/** Imperative handle the controller calls when the footer's primary CTA fires. */
export interface StepHandle {
  /** perform the step's work + persist progress; resolve true to advance. */
  submit: () => Promise<boolean>;
}
