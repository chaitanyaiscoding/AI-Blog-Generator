import { useEffect, useState, type SubmitEvent } from "react";
import { logout } from "../auth";
import { api, errorMessage } from "../api";
import { navigate } from "../router";

type Status = "idle" | "loading" | "success" | "error";

// The backend saves the blog right away and a Celery worker fills in the
// content; status says how far along it is.
type Blog = {
  id: number;
  status: "pending" | "processing" | "completed" | "failed";
  content: string;
  error: string;
};

const POLL_INTERVAL_MS = 5000;

const PROGRESS_MESSAGES: Record<string, string> = {
  pending: "Queued, waiting for a free worker...",
  processing: "Transcribing the video and writing your blog...",
};

export function HomePage({ username }: { username: string }) {
  const [url, setUrl] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [result, setResult] = useState("");
  // The blog being generated; polled until it's completed or failed.
  const [blog, setBlog] = useState<Blog | null>(null);

  const showBlog = (data: Blog) => {
    if (data.status === "completed") {
      setResult(data.content);
      setStatus("success");
    } else if (data.status === "failed") {
      setResult(data.error || "Generating the blog failed.");
      setStatus("error");
    } else {
      setBlog(data);
    }
  };

  // Each poll sets a new blog object, which schedules the next one, so requests never overlap.
  useEffect(() => {
    if (!blog) return;
    const timer = setTimeout(async () => {
      try {
        const { data } = await api.get<Blog>(`/blogs/${blog.id}/`);
        showBlog(data);
      } catch (err) {
        setResult(errorMessage(err));
        setStatus("error");
      }
    }, POLL_INTERVAL_MS);
    return () => clearTimeout(timer);
  }, [blog]);

  const handleSubmit = async (e: SubmitEvent<HTMLFormElement>) => {
    e.preventDefault();
    setStatus("loading");
    setResult("");
    setBlog(null);

    try {
      const { data } = await api.post<Blog>("/blogs/", { url });
      showBlog(data);
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
              ? (blog && PROGRESS_MESSAGES[blog.status]) || "Submitting..."
              : "Your generated blog will appear here."}
          </p>
        )}
      </section>
    </div>
  );
}
