import { useState, type SubmitEvent } from "react";
import { logout } from "../auth";
import { api, errorMessage } from "../api";
import { navigate } from "../router";

type Status = "idle" | "loading" | "success" | "error";

export function HomePage({ username }: { username: string }) {
  const [url, setUrl] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [result, setResult] = useState("");

  const handleSubmit = async (e: SubmitEvent<HTMLFormElement>) => {
    e.preventDefault();
    setStatus("loading");
    setResult("");

    try {
      const { data } = await api.post("/blogs/", { url });
      setResult(typeof data.content === "string" ? data.content : JSON.stringify(data, null, 2));
      setStatus("success");
    } catch (err) {
      setResult(errorMessage(err));
      setStatus("error");
    }
  };

  const handleLogout = async () => {
    await logout();
    navigate("/");
  };

  return (
    <div className="app">
      <header className="top-bar">
        <span>Hi, {username}</span>
        <button type="button" className="link-button" onClick={handleLogout}>
          Logout
        </button>
      </header>

      <h1>AI Blog Generator</h1>

      <form className="blog-form" onSubmit={handleSubmit}>
        <input
          type="url"
          className="url-input"
          placeholder="https://example.com/article"
          value={url}
          onChange={e => setUrl(e.target.value)}
          required
        />
        <button type="submit" className="send-button" disabled={status === "loading"}>
          {status === "loading" ? "Creating..." : "Create Blog"}
        </button>
      </form>

      <section className="blog-article">
        <h2>AI Blog Article</h2>
        {result ? (
          <pre className={`blog-output ${status === "error" ? "error" : ""}`}>{result}</pre>
        ) : (
          <p className="placeholder">
            {status === "loading"
              ? "Generating your blog..."
              : "Your generated blog will appear here."}
          </p>
        )}
      </section>
    </div>
  );
}
