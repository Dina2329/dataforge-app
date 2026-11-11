import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useCreateBase } from "./useBases";
import { useToastStore } from "../stores/toastStore";

vi.mock("../lib/apiClient", () => ({
  apiClient: {
    post: vi.fn(async (_url: string, body: { name: string }) => ({
      data: { id: "base-1", name: body.name, workspace_id: "ws-1" },
    })),
  },
}));

function wrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

describe("useCreateBase", () => {
  beforeEach(() => {
    useToastStore.setState({ toasts: [] });
  });

  it("invalidates the bases query and shows a success toast naming the new base", async () => {
    const queryClient = new QueryClient();
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(() => useCreateBase("ws-1"), { wrapper: wrapper(queryClient) });

    result.current.mutate("Product Data");

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["bases", "ws-1"] });

    const toasts = useToastStore.getState().toasts;
    expect(toasts).toHaveLength(1);
    expect(toasts[0]).toMatchObject({ variant: "success", message: 'Created base "Product Data"' });
  });
});
