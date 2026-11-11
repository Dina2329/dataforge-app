import { useMutation, useQuery } from "@tanstack/react-query";
import { apiClient } from "../lib/apiClient";
import type { PublicForm, RecordRow } from "../types";

export function usePublicForm(token: string | undefined) {
  return useQuery({
    queryKey: ["public-form", token],
    queryFn: async () => (await apiClient.get<PublicForm>(`/api/public/forms/${token}`)).data,
    enabled: !!token,
    retry: false,
  });
}

export function useSubmitPublicForm(token: string | undefined) {
  return useMutation({
    mutationFn: async (values: Record<string, unknown>) =>
      (await apiClient.post<RecordRow>(`/api/public/forms/${token}/submit`, { values })).data,
  });
}
