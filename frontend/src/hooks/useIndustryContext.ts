import { useQuery } from "@tanstack/react-query";
import { industryApi } from "@/api/industry";
import { useWorkspaceIndustry } from "@/hooks/useWorkspaceIndustry";

export const useIndustryContext = () => {
  const active = useWorkspaceIndustry();
  return useQuery({
    queryKey: ["industry-context", active],
    queryFn: industryApi.context,
    staleTime: 5 * 60_000,
  });
};
