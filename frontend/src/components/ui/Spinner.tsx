import clsx from "clsx";

export const Spinner = ({ size = "md", className }: { size?: "sm" | "md" | "lg"; className?: string }) => {
  const sz = { sm: "h-4 w-4 border-2", md: "h-8 w-8 border-2", lg: "h-12 w-12 border-[3px]" }[size];
  return (
    <div className={clsx("flex items-center justify-center", className)}>
      <div
        className={clsx(
          sz,
          "rounded-full border-white/15 border-t-accent-primary animate-spin",
        )}
      />
    </div>
  );
};

export const PageLoader = () => (
  <div className="min-h-[50vh] flex items-center justify-center">
    <Spinner size="lg" />
  </div>
);
