import { beforeEach, describe, expect, it, vi } from "vitest";
import { toast, useToastStore } from "./toastStore";

describe("toastStore", () => {
  beforeEach(() => {
    useToastStore.setState({ toasts: [] });
    vi.useRealTimers();
  });

  it("push adds a toast with the given variant and message", () => {
    toast.success("Created base \"Acme\"");
    const toasts = useToastStore.getState().toasts;
    expect(toasts).toHaveLength(1);
    expect(toasts[0]).toMatchObject({ variant: "success", message: 'Created base "Acme"' });
  });

  it("stacks multiple toasts in call order with distinct ids", () => {
    toast.success("first");
    toast.error("second");
    const toasts = useToastStore.getState().toasts;
    expect(toasts.map((t) => t.message)).toEqual(["first", "second"]);
    expect(toasts[0].id).not.toBe(toasts[1].id);
  });

  it("dismiss removes only the targeted toast", () => {
    toast.success("keep me");
    toast.error("remove me");
    const [, second] = useToastStore.getState().toasts;
    useToastStore.getState().dismiss(second.id);
    const remaining = useToastStore.getState().toasts;
    expect(remaining).toHaveLength(1);
    expect(remaining[0].message).toBe("keep me");
  });

  it("auto-dismisses a toast after 4 seconds", () => {
    vi.useFakeTimers();
    toast.info("fading away");
    expect(useToastStore.getState().toasts).toHaveLength(1);

    vi.advanceTimersByTime(3999);
    expect(useToastStore.getState().toasts).toHaveLength(1);

    vi.advanceTimersByTime(1);
    expect(useToastStore.getState().toasts).toHaveLength(0);
  });
});
