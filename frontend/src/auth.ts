import { useSyncExternalStore } from "react";
import { api, errorMessage } from "./api";

export type User = { id: number; username: string; email: string };

// The logged-in user is kept in memory only; the backend session cookie is the
// source of truth. `undefined` means we haven't asked the backend yet.
let currentUser: User | null | undefined = undefined;
const listeners = new Set<() => void>();

function setUser(user: User | null): void {
  currentUser = user;
  listeners.forEach(listener => listener());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useUser(): User | null | undefined {
  return useSyncExternalStore(subscribe, () => currentUser);
}

// Ask the backend who is logged in (also sets the CSRF cookie). It answers 403
// when nobody is logged in.
export async function loadUser(): Promise<void> {
  try {
    const { data } = await api.get<User>("/me/");
    setUser(data);
  } catch {
    setUser(null);
  }
}

export async function login(username: string, password: string): Promise<void> {
  try {
    const { data } = await api.post<User>("/login/", { username, password });
    setUser(data);
  } catch (err) {
    throw new Error(errorMessage(err));
  }
}

export async function signup(username: string, email: string, password: string): Promise<void> {
  try {
    const { data } = await api.post<User>("/signup/", { username, email, password });
    setUser(data);
  } catch (err) {
    throw new Error(errorMessage(err));
  }
}

export async function logout(): Promise<void> {
  try {
    await api.post("/logout/");
  } catch {
    // Session may already be gone; treat the user as logged out either way.
  } finally {
    setUser(null);
  }
}
