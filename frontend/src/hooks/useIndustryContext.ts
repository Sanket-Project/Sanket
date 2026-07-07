import { useQuery } from "@tanstack/react-query";
import { industryApi } from "@/api/industry";
import { useIndustryStore } from "@/stores/industry";

export const useIndustryContext = () => {
  const active = useIndustryStore((s) => s.activeIndustry);
  return useQuery({
    queryKey: ["industry-context", active],
    queryFn: industryApi.context,
    staleTime: 5 * 60_000,
  });
};
