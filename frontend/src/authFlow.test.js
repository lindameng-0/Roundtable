import React, { act } from "react";
import { createRoot } from "react-dom/client";
import axios from "axios";
import { AuthProvider, useAuth } from "./context/AuthContext";
import AuthCallback from "./pages/AuthCallback";

jest.mock("axios", () => ({ get: jest.fn(), post: jest.fn() }));
const mockNavigate = jest.fn();
jest.mock("react-router-dom", () => ({
  useNavigate: () => mockNavigate,
  Link: ({ to, children, ...props }) => <a href={to} {...props}>{children}</a>,
}), { virtual: true });

let currentAuth;
let root;
let container;
const deferred = () => {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
};
function Probe() { currentAuth = useAuth(); return null; }
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  jest.clearAllMocks();
  localStorage.clear();
  window.history.replaceState(null, "", "/auth/callback");
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
  delete global.IS_REACT_ACT_ENVIRONMENT;
});

test("a delayed failed startup check cannot undo a successful login", async () => {
  const startup = deferred();
  axios.get.mockReturnValueOnce(startup.promise);
  await act(async () => root.render(<AuthProvider><Probe /></AuthProvider>));
  act(() => currentAuth.login({ user_id: "signed-in" }));
  expect(currentAuth.loading).toBe(false);
  await act(async () => startup.reject({ response: { status: 401 } }));
  expect(currentAuth.user.user_id).toBe("signed-in");
});

test("a delayed successful check cannot restore a logged-out session", async () => {
  const startup = deferred();
  axios.get.mockReturnValueOnce(startup.promise);
  axios.post.mockResolvedValueOnce({});
  await act(async () => root.render(<AuthProvider><Probe /></AuthProvider>));
  await act(async () => currentAuth.logout());
  await act(async () => startup.resolve({ data: { user_id: "old-session" } }));
  expect(currentAuth.user).toBeNull();
  expect(currentAuth.loading).toBe(false);
});

test("a rejected callback stays on a clear error screen and can retry", async () => {
  axios.get.mockRejectedValue({ response: { status: 401 } });
  await act(async () => root.render(<AuthProvider><Probe /><AuthCallback /></AuthProvider>));
  expect(container.querySelector('[role="alert"]').textContent).toContain("couldn't finish signing you in");
  expect(mockNavigate).not.toHaveBeenCalled();
  axios.get.mockResolvedValueOnce({ data: { user_id: "recovered" } });
  await act(async () => container.querySelector("button").click());
  expect(currentAuth.user.user_id).toBe("recovered");
  expect(currentAuth.loading).toBe(false);
  expect(mockNavigate).toHaveBeenCalledWith("/dashboard", { replace: true });
  expect(axios.get.mock.calls.at(-1)[1]).toMatchObject({ withCredentials: true, timeout: 15000 });
});

test("leaving the callback aborts its request and prevents late navigation", async () => {
  const pending = deferred();
  axios.get.mockReturnValue(pending.promise);
  await act(async () => root.render(<AuthProvider><Probe /><AuthCallback /></AuthProvider>));
  const callbackRequest = axios.get.mock.calls.find(([, options]) => options.signal);
  await act(async () => root.render(<AuthProvider><Probe /></AuthProvider>));
  expect(callbackRequest[1].signal.aborted).toBe(true);
  await act(async () => pending.resolve({ data: { user_id: "late" } }));
  expect(mockNavigate).not.toHaveBeenCalled();
});
