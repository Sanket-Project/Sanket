import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  type ReactNode,
} from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { planningApi } from "@/api/onboarding";
import type { StepHandle, StepProps } from "./types";

const schema = z.object({
  calendar: z.object({
    fiscal_year_start_month: z.number().int().min(1).max(12),
    period: z.enum(["weekly", "monthly"]),
    week_start: z.enum(["monday", "sunday"]),
    horizon_weeks: z.number().int().min(1).max(104),
  }),
  rules: z.object({
    min_history_weeks: z.number().int().min(0).max(520),
    default_service_level: z.number().min(0.5).max(0.999),
    review_cadence: z.enum(["weekly", "biweekly", "monthly"]),
  }),
});

type FormValues = z.infer<typeof schema>;

const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

const Field = ({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) => (
  <div>
    <label className="label">{label}</label>
    {children}
    {hint && <p className="mt-1 text-[11px] text-content-subtle">{hint}</p>}
  </div>
);

export const StepCalendar = forwardRef<StepHandle, StepProps>(function StepCalendar(
  { nextStep, thisStep, save },
  ref,
) {
  const { data } = useQuery({ queryKey: ["planning", "config"], queryFn: planningApi.getConfig });

  const { register, handleSubmit, reset } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      calendar: { fiscal_year_start_month: 1, period: "weekly", week_start: "monday", horizon_weeks: 13 },
      rules: { min_history_weeks: 8, default_service_level: 0.95, review_cadence: "weekly" },
    },
  });

  useEffect(() => {
    if (data) reset(data as FormValues);
  }, [data, reset]);

  useImperativeHandle(ref, () => ({
    submit: () =>
      new Promise<boolean>((resolve) => {
        void handleSubmit(
          async (vals) => {
            try {
              await planningApi.updateConfig(vals);
              await save({
                mark_step: thisStep,
                current_step: nextStep,
                step_meta: { horizon_weeks: vals.calendar.horizon_weeks },
              });
              resolve(true);
            } catch {
              resolve(false);
            }
          },
          () => resolve(false),
        )();
      }),
  }));

  return (
    <form className="space-y-6" onSubmit={(e) => e.preventDefault()}>
      <section>
        <h3 className="mb-3 font-heading text-sm font-semibold tracking-tight text-content">
          Calendar
        </h3>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Fiscal year starts">
            <select className="input" {...register("calendar.fiscal_year_start_month", { valueAsNumber: true })}>
              {MONTHS.map((m, i) => (
                <option key={m} value={i + 1}>{m}</option>
              ))}
            </select>
          </Field>
          <Field label="Planning period">
            <select className="input" {...register("calendar.period")}>
              <option value="weekly">Weekly</option>
              <option value="monthly">Monthly</option>
            </select>
          </Field>
          <Field label="Week starts on">
            <select className="input" {...register("calendar.week_start")}>
              <option value="monday">Monday</option>
              <option value="sunday">Sunday</option>
            </select>
          </Field>
          <Field label="Forecast horizon (weeks)" hint="How far ahead each plan looks">
            <input type="number" min={1} max={104} className="input" {...register("calendar.horizon_weeks", { valueAsNumber: true })} />
          </Field>
        </div>
      </section>

      <section>
        <h3 className="mb-3 font-heading text-sm font-semibold tracking-tight text-content">
          Planning rules
        </h3>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Min. history (weeks)" hint="Minimum data before forecasting a SKU">
            <input type="number" min={0} max={520} className="input" {...register("rules.min_history_weeks", { valueAsNumber: true })} />
          </Field>
          <Field label="Service level" hint="Target fill rate (0.50–0.999)">
            <input
              type="number"
              step="0.01"
              min={0.5}
              max={0.999}
              className="input"
              {...register("rules.default_service_level", { valueAsNumber: true })}
            />
          </Field>
          <Field label="Review cadence">
            <select className="input" {...register("rules.review_cadence")}>
              <option value="weekly">Weekly</option>
              <option value="biweekly">Bi-weekly</option>
              <option value="monthly">Monthly</option>
            </select>
          </Field>
        </div>
      </section>
    </form>
  );
});
