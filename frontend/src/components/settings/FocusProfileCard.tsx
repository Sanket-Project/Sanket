import { useEffect, useState, type KeyboardEvent } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Save, X, Target, Plus } from "lucide-react";
import toast from "react-hot-toast";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { industryApi } from "@/api/industry";
import { useIndustryStore } from "@/stores/industry";

/** A small tag input: type a term, press Enter (or comma) to add; click × to remove. */
const TagInput = ({
  id,
  label,
  placeholder,
  values,
  onChange,
}: {
  id: string;
  label: string;
  placeholder: string;
  values: string[];
  onChange: (next: string[]) => void;
}) => {
  const [draft, setDraft] = useState("");

  const add = (raw: string) => {
    const v = raw.trim().toLowerCase();
    if (!v || values.includes(v)) return;
    onChange([...values, v]);
    setDraft("");
  };

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      add(draft);
    } else if (e.key === "Backspace" && !draft && values.length) {
      onChange(values.slice(0, -1));
    }
  };

  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
        {label}
      </label>
      <div className="flex flex-wrap gap-1.5 rounded-xl border border-slate-200/60 dark:border-line bg-white/70 dark:bg-surface-2 p-2.5 focus-within:ring-2 focus-within:ring-violet-500/40">
        {values.map((v) => (
          <Badge key={v} variant="primary" className="flex items-center gap-1 text-xs">
            {v}
            <button
              type="button"
              onClick={() => onChange(values.filter((x) => x !== v))}
              className="hover:text-rose-500"
              aria-label={`Remove ${v}`}
            >
              <X size={11} aria-hidden="true" />
            </button>
          </Badge>
        ))}
        <input
          id={id}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
          onBlur={() => add(draft)}
          placeholder={values.length ? "" : placeholder}
          className="flex-1 min-w-[8rem] bg-transparent text-sm text-content outline-none placeholder:text-slate-400"
        />
      </div>
    </div>
  );
};

export const FocusProfileCard = () => {
  const activeIndustry = useIndustryStore((s) => s.activeIndustry);
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["industry-profile", activeIndustry],
    queryFn: industryApi.profile,
  });

  const [keywords, setKeywords] = useState<string[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [horizon, setHorizon] = useState<string>("");

  // Sync local editor state when the server config (re)loads.
  useEffect(() => {
    if (!data) return;
    setKeywords(data.focus.keywords);
    setCategories(data.focus.categories);
    setHorizon(String(data.effective_horizon));
  }, [data]);

  const mutation = useMutation({
    mutationFn: industryApi.updateProfile,
    onSuccess: (updated) => {
      queryClient.setQueryData(["industry-profile", activeIndustry], updated);
      queryClient.invalidateQueries({ queryKey: ["industry-context"] });
      toast.success("Focus profile saved");
    },
    onError: (err) =>
      toast.error((err as { message?: string })?.message ?? "Failed to save focus profile"),
  });

  const horizonNum = Number(horizon);
  const horizonValid = Number.isInteger(horizonNum) && horizonNum >= 1 && horizonNum <= 52;

  const save = () => {
    if (!horizonValid) {
      toast.error("Horizon must be between 1 and 52 weeks");
      return;
    }
    mutation.mutate({
      focus: { keywords, categories },
      custom_horizon_weeks: horizonNum,
    });
  };

  return (
    <Card
      title="Focus Profile"
      description="Scope forecasts and trend signals to what your business actually sells. A rice mill might track “rice, paddy, basmati”; a farm-supply store “fertilizer, seed, pesticide”."
    >
      {isLoading ? (
        <p className="text-sm text-slate-400">Loading…</p>
      ) : (
        <div className="space-y-5">
          <div className="flex items-center gap-2 text-xs text-content-subtle">
            <Target size={14} className="text-violet-500 shrink-0" aria-hidden="true" />
            Signals matching these terms are prioritized; everything else is filtered out of your
            forecasts.
          </div>

          <TagInput
            id="focus-keywords"
            label="Keywords"
            placeholder="e.g. rice, paddy, basmati — Enter to add"
            values={keywords}
            onChange={setKeywords}
          />
          <TagInput
            id="focus-categories"
            label="Categories"
            placeholder="e.g. grain, milled — Enter to add"
            values={categories}
            onChange={setCategories}
          />

          <div className="space-y-1.5 max-w-[12rem]">
            <label
              htmlFor="focus-horizon"
              className="text-[10px] font-bold uppercase tracking-wider text-slate-400"
            >
              Forecast horizon (weeks)
            </label>
            <input
              id="focus-horizon"
              type="number"
              min={1}
              max={52}
              value={horizon}
              onChange={(e) => setHorizon(e.target.value)}
              className={`w-full rounded-xl border bg-white/70 dark:bg-surface-2 px-3 py-2 text-sm text-content outline-none focus:ring-2 focus:ring-violet-500/40 ${
                horizonValid ? "border-slate-200/60 dark:border-line" : "border-rose-400"
              }`}
            />
          </div>

          <div className="flex items-center justify-between gap-3 pt-1">
            <p className="text-[11px] text-slate-400 flex items-center gap-1">
              <Plus size={11} aria-hidden="true" />
              {keywords.length + categories.length} focus term
              {keywords.length + categories.length === 1 ? "" : "s"}
            </p>
            <Button
              type="button"
              size="sm"
              icon={<Save size={14} />}
              loading={mutation.isPending}
              onClick={save}
            >
              Save focus
            </Button>
          </div>
        </div>
      )}
    </Card>
  );
};
