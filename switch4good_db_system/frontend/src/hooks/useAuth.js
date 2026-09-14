/**
 * useAuth Hook
 * Manages authentication state and operations
 */
import { useState, useEffect, useCallback } from "react";
import { api, API_URL } from "../services/api";

export function useAuth() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Check for existing token on mount
  useEffect(() => {
    const verifyToken = async () => {
      const token = localStorage.getItem("token");
      if (!token) {
        setLoading(false);
        return;
      }

      try {
        const response = await fetch(`${API_URL}/auth/verify`, {
          headers: { Authorization: `Bearer ${token}` },
        });

        if (response.ok) {
          const data = await response.json();
          setUser(data.user);
        } else {
          localStorage.removeItem("token");
        }
      } catch (err) {
        console.error("Token verification failed:", err);
        localStorage.removeItem("token");
      } finally {
        setLoading(false);
      }
    };

    verifyToken();
  }, []);

  const login = useCallback(async (username, password) => {
    setError(null);
    setLoading(true);

    try {
      const data = await api.auth.login(username, password);
      localStorage.setItem("token", data.token);
      setUser(data.user);
      return { success: true };
    } catch (err) {
      setError(err.message);
      return { success: false, error: err.message };
    } finally {
      setLoading(false);
    }
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem("token");
    setUser(null);
  }, []);

  const getAuthHeaders = useCallback(() => {
    const token = localStorage.getItem("token");
    return {
      "Content-Type": "application/json",
      ...(token && { Authorization: `Bearer ${token}` }),
    };
  }, []);

  const isAdmin = user?.role === "admin";
  const isStaff = user?.role === "staff" || user?.role === "admin";
  const isViewer = user?.role === "viewer";

  return {
    user,
    loading,
    error,
    login,
    logout,
    getAuthHeaders,
    isAuthenticated: !!user,
    isAdmin,
    isStaff,
    isViewer,
  };
}

export default useAuth;
