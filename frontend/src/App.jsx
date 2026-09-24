import { useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import AuthPage from "./pages/AuthPage";
import DashboardPage from "./pages/DashboardPage";
import GrowwConnectPage from "./pages/GrowwConnectPage";
import GrowwManagePage from "./pages/GrowwManagePage";
import { clearToken, getToken, growwStatus, me } from "./api";

function App() {
  const [session, setSession] = useState({
    loading: true,
    user: null,
    growwConnected: false,
  });

  useEffect(() => {
    let active = true;

    async function bootstrap() {
      const token = getToken();

      if (!token) {
        if (active) setSession({ loading: false, user: null, growwConnected: false });
        return;
      }

      try {
        const [user, groww] = await Promise.all([me(), growwStatus()]);
        if (active) {
          setSession({
            loading: false,
            user,
            growwConnected: Boolean(groww.connected),
          });
        }
      } catch {
        clearToken();
        if (active) setSession({ loading: false, user: null, growwConnected: false });
      }
    }

    bootstrap();
    return () => {
      active = false;
    };
  }, []);

  if (session.loading) {
    return (
      <div className="app-shell centered">
        <div className="loader-orb" />
      </div>
    );
  }

  return (
    <Routes>
      <Route
        path="/auth"
        element={
          session.user ? (
            <Navigate to={session.growwConnected ? "/" : "/connect"} replace />
          ) : (
            <AuthPage
              onAuthenticated={(user, growwConnected) =>
                setSession((prev) => ({
                  ...prev,
                  user,
                  growwConnected,
                  loading: false,
                }))
              }
            />
          )
        }
      />

      <Route
        path="/connect"
        element={
          !session.user ? (
            <Navigate to="/auth" replace />
          ) : session.growwConnected ? (
            <Navigate to="/" replace />
          ) : (
            <GrowwConnectPage
              user={session.user}
              onConnected={() =>
                setSession((prev) => ({ ...prev, growwConnected: true }))
              }
            />
          )
        }
      />

      <Route
        path="/settings/groww"
        element={
          !session.user ? (
            <Navigate to="/auth" replace />
          ) : (
            <GrowwManagePage user={session.user} />
          )
        }
      />

      <Route
        path="/"
        element={
          !session.user ? (
            <Navigate to="/auth" replace />
          ) : !session.growwConnected ? (
            <Navigate to="/connect" replace />
          ) : (
            <DashboardPage
              user={session.user}
              onLogout={() => {
                clearToken();
                setSession({ loading: false, user: null, growwConnected: false });
              }}
            />
          )
        }
      />

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default App;
