import { useEffect } from "react";
import "./index.css";
import { loadUser, useUser } from "./auth";
import { navigate, usePath } from "./router";
import { HomePage } from "./pages/HomePage";
import { AuthPage } from "./pages/AuthPage";

export function App() {
  const path = usePath();
  const user = useUser();

  // Restore the session from the backend cookie on page load.
  useEffect(() => {
    loadUser();
  }, []);

  // Logged-in users go to /home; everyone else is sent to the login/signup page at /.
  const target = user ? "/home" : "/";

  useEffect(() => {
    if (user !== undefined && path !== target) navigate(target, true);
  }, [user, path, target]);

  // Still checking the session, or about to redirect.
  if (user === undefined || path !== target) return null;
  return user ? <HomePage username={user.username} /> : <AuthPage />;
}

export default App;
