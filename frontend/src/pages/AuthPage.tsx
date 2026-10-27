import { useState, type SubmitEvent } from "react";
import { login, signup } from "../auth";
import { navigate } from "../router";

type Mode = "login" | "signup";

export function AuthPage() {
  const [mode, setMode] = useState<Mode>("login");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");

  const switchMode = (next: Mode) => {
    setMode(next);
    setError("");
    setPassword("");
    setConfirmPassword("");
  };

  const handleSubmit = async (e: SubmitEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError("");

    try {
      if (mode === "signup") {
        if (password !== confirmPassword) throw new Error("Passwords do not match");
        await signup(username, email, password);
      } else {
        await login(username, password);
      }
      navigate("/home");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const isSignup = mode === "signup";

  return (
    <div className="app">
      <h1>AI Blog Generator</h1>

      <form className="login-form" onSubmit={handleSubmit}>
        <div className="auth-tabs" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={!isSignup}
            className={`auth-tab ${!isSignup ? "active" : ""}`}
            onClick={() => switchMode("login")}
          >
            Login
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={isSignup}
            className={`auth-tab ${isSignup ? "active" : ""}`}
            onClick={() => switchMode("signup")}
          >
            Sign up
          </button>
        </div>

        <input
          className="text-input"
          placeholder="Username"
          autoComplete="username"
          value={username}
          onChange={e => setUsername(e.target.value)}
          required
        />
        {isSignup && (
          <input
            type="email"
            className="text-input"
            placeholder="Email"
            autoComplete="email"
            value={email}
            onChange={e => setEmail(e.target.value)}
            required
          />
        )}
        <input
          type="password"
          className="text-input"
          placeholder="Password"
          autoComplete={isSignup ? "new-password" : "current-password"}
          value={password}
          onChange={e => setPassword(e.target.value)}
          required
        />
        {isSignup && (
          <input
            type="password"
            className="text-input"
            placeholder="Confirm password"
            autoComplete="new-password"
            value={confirmPassword}
            onChange={e => setConfirmPassword(e.target.value)}
            required
          />
        )}
        {error && <p className="form-error">{error}</p>}
        <button type="submit" className="send-button">
          {isSignup ? "Create account" : "Login"}
        </button>

        <p className="auth-switch">
          {isSignup ? "Already have an account? " : "Don't have an account? "}
          <button
            type="button"
            className="link-button"
            onClick={() => switchMode(isSignup ? "login" : "signup")}
          >
            {isSignup ? "Login" : "Sign up"}
          </button>
        </p>
      </form>
    </div>
  );
}
