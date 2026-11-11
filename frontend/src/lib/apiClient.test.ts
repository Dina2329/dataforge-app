import axios from "axios";
import MockAdapter from "axios-mock-adapter";
import { beforeEach, describe, expect, it } from "vitest";
import { apiClient } from "./apiClient";
import { useAuthStore } from "../stores/authStore";

describe("apiClient 401 refresh-and-retry interceptor", () => {
  let mock: MockAdapter;
  // refreshAccessToken() in apiClient.ts deliberately posts through the bare
  // `axios` default instance rather than `apiClient` -- that's what keeps the
  // refresh call itself from carrying the (expired) auth header or looping
  // back through this same 401 interceptor -- so it needs its own mock.
  let refreshMock: MockAdapter;

  beforeEach(() => {
    mock = new MockAdapter(apiClient);
    refreshMock = new MockAdapter(axios);
    useAuthStore.setState({ accessToken: "expired-token", refreshToken: "valid-refresh-token", user: null });
  });

  it("refreshes the access token and retries the original request once", async () => {
    mock.onGet("/api/widgets").replyOnce(401);
    mock.onGet("/api/widgets").reply((config) => {
      expect(config.headers?.Authorization).toBe("Bearer new-access-token");
      return [200, { ok: true }];
    });
    refreshMock.onPost("/api/auth/refresh").reply(200, { access_token: "new-access-token" });

    const response = await apiClient.get("/api/widgets");

    expect(response.status).toBe(200);
    expect(response.data).toEqual({ ok: true });
    expect(useAuthStore.getState().accessToken).toBe("new-access-token");
  });

  it("dedupes concurrent refreshes: two 401s in flight trigger only one refresh call", async () => {
    let widgetCalls = 0;
    mock.onGet("/api/widgets").reply(() => {
      widgetCalls += 1;
      // First hit per request errors once; the interceptor's retry (2nd call
      // for that same request) should carry the refreshed token.
      return widgetCalls <= 2 ? [401] : [200, { ok: true }];
    });
    let refreshCalls = 0;
    refreshMock.onPost("/api/auth/refresh").reply(() => {
      refreshCalls += 1;
      return [200, { access_token: "new-access-token" }];
    });

    const [a, b] = await Promise.all([apiClient.get("/api/widgets"), apiClient.get("/api/widgets")]);

    expect(a.status).toBe(200);
    expect(b.status).toBe(200);
    expect(refreshCalls).toBe(1);
  });

  it("logs out when the refresh call itself fails", async () => {
    mock.onGet("/api/widgets").reply(401);
    refreshMock.onPost("/api/auth/refresh").reply(401);

    await expect(apiClient.get("/api/widgets")).rejects.toBeTruthy();

    const state = useAuthStore.getState();
    expect(state.accessToken).toBeNull();
    expect(state.refreshToken).toBeNull();
  });

  it("does not retry the same request more than once", async () => {
    let widgetCalls = 0;
    mock.onGet("/api/widgets").reply(() => {
      widgetCalls += 1;
      return [401];
    });
    refreshMock.onPost("/api/auth/refresh").reply(200, { access_token: "new-access-token" });

    await expect(apiClient.get("/api/widgets")).rejects.toBeTruthy();
    expect(widgetCalls).toBe(2); // original + exactly one retry, never looped
  });
});
