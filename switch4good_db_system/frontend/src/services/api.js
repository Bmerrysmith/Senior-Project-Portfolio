/**
 * API Configuration and Service
 * Centralized API calls for the Switch4Good application
 */

// API base URL - can be configured via environment variable
export const API_URL = import.meta.env.VITE_API_URL || "/api";

/**
 * Get authorization headers for API calls
 */
export const getAuthHeaders = () => {
  const token = localStorage.getItem("token");
  return {
    "Content-Type": "application/json",
    ...(token && { Authorization: `Bearer ${token}` }),
  };
};

/**
 * Generic API request handler
 */
export const apiRequest = async (endpoint, options = {}) => {
  const url = `${API_URL}${endpoint}`;
  const config = {
    headers: getAuthHeaders(),
    ...options,
  };

  const response = await fetch(url, config);

  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ error: "Request failed" }));
    throw new Error(error.error || error.message || "API request failed");
  }

  return response.json();
};

/**
 * API methods organized by resource
 */
export const api = {
  // Auth
  auth: {
    login: (username, password) =>
      apiRequest("/auth/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      }),
    verify: () => apiRequest("/auth/verify"),
    changePassword: (currentPassword, newPassword) =>
      apiRequest("/auth/password", {
        method: "PATCH",
        body: JSON.stringify({ currentPassword, newPassword }),
      }),
  },

  // Dashboard
  dashboard: {
    getStats: () => apiRequest("/dashboard"),
    getV2Dashboard: () => apiRequest("/v2/dashboard"),
  },

  // Schools
  schools: {
    getAll: () => apiRequest("/schools"),
    create: (data) =>
      apiRequest("/schools", { method: "POST", body: JSON.stringify(data) }),
    update: (id, data) =>
      apiRequest(`/schools/${id}`, {
        method: "PUT",
        body: JSON.stringify(data),
      }),
    delete: (id) => apiRequest(`/schools/${id}`, { method: "DELETE" }),
  },

  // Programs
  programs: {
    getAll: () => apiRequest("/programs"),
    getDirectory: () => apiRequest("/program-directory"),
    create: (data) =>
      apiRequest("/programs", { method: "POST", body: JSON.stringify(data) }),
    update: (id, data) =>
      apiRequest(`/programs/${id}`, {
        method: "PUT",
        body: JSON.stringify(data),
      }),
    delete: (id) => apiRequest(`/programs/${id}`, { method: "DELETE" }),
  },

  // Students
  students: {
    getAll: () => apiRequest("/students"),
    getTracker: () => apiRequest("/student-tracker"),
    create: (data) =>
      apiRequest("/students", { method: "POST", body: JSON.stringify(data) }),
    update: (id, data) =>
      apiRequest(`/students/${id}`, {
        method: "PUT",
        body: JSON.stringify(data),
      }),
    delete: (id) => apiRequest(`/students/${id}`, { method: "DELETE" }),
    getHours: (participationId) => apiRequest(`/hours/${participationId}`),
    getChecklist: (participationId) =>
      apiRequest(`/checklist/${participationId}`),
  },

  // CAN Metrics
  canMetrics: {
    getAll: () => apiRequest("/can-metrics"),
    create: (data) =>
      apiRequest("/can-metrics", {
        method: "POST",
        body: JSON.stringify(data),
      }),
    update: (id, data) =>
      apiRequest(`/can-metrics/${id}`, {
        method: "PUT",
        body: JSON.stringify(data),
      }),
    delete: (id) => apiRequest(`/can-metrics/${id}`, { method: "DELETE" }),
  },

  // Staging tables
  staging: {
    programCourse: {
      getAll: () => apiRequest("/staging/program-course"),
      create: (data) =>
        apiRequest("/staging/program-course", {
          method: "POST",
          body: JSON.stringify(data),
        }),
      delete: (id) =>
        apiRequest(`/staging/program-course/${id}`, { method: "DELETE" }),
    },
    studentTracker: {
      getAll: () => apiRequest("/staging/student-tracker"),
      create: (data) =>
        apiRequest("/staging/student-tracker", {
          method: "POST",
          body: JSON.stringify(data),
        }),
      delete: (id) =>
        apiRequest(`/staging/student-tracker/${id}`, { method: "DELETE" }),
    },
    canMetrics: {
      getAll: () => apiRequest("/staging/can-metrics"),
      create: (data) =>
        apiRequest("/staging/can-metrics", {
          method: "POST",
          body: JSON.stringify(data),
        }),
      delete: (id) =>
        apiRequest(`/staging/can-metrics/${id}`, { method: "DELETE" }),
    },
    programDirectory: {
      getAll: () => apiRequest("/staging/program-directory"),
      create: (data) =>
        apiRequest("/staging/program-directory", {
          method: "POST",
          body: JSON.stringify(data),
        }),
      delete: (id) =>
        apiRequest(`/staging/program-directory/${id}`, { method: "DELETE" }),
    },
  },

  // File upload
  upload: {
    getTables: () => apiRequest("/upload/tables"),
    preview: async (file, targetTable = null) => {
      const formData = new FormData();
      formData.append("file", file);
      if (targetTable) formData.append("targetTable", targetTable);

      const response = await fetch(`${API_URL}/upload/preview`, {
        method: "POST",
        headers: { Authorization: `Bearer ${localStorage.getItem("token")}` },
        body: formData,
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || "Preview failed");
      }
      return response.json();
    },
    import: async (file, targetTable = null) => {
      const formData = new FormData();
      formData.append("file", file);
      if (targetTable) formData.append("targetTable", targetTable);

      const response = await fetch(`${API_URL}/upload/import`, {
        method: "POST",
        headers: { Authorization: `Bearer ${localStorage.getItem("token")}` },
        body: formData,
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || "Import failed");
      }
      return response.json();
    },
  },

  // Admin
  admin: {
    getUsers: () => apiRequest("/admin/users"),
    createUser: (data) =>
      apiRequest("/admin/users", {
        method: "POST",
        body: JSON.stringify(data),
      }),
    updateUser: (id, data) =>
      apiRequest(`/admin/users/${id}`, {
        method: "PUT",
        body: JSON.stringify(data),
      }),
    deleteUser: (id) => apiRequest(`/admin/users/${id}`, { method: "DELETE" }),
    resetPassword: (id, newPassword) =>
      apiRequest(`/admin/users/${id}/password`, {
        method: "PATCH",
        body: JSON.stringify({ newPassword }),
      }),
    unlockUser: (id) =>
      apiRequest(`/admin/users/${id}/unlock`, { method: "PATCH" }),
  },

  // V2 API (normalized schema)
  v2: {
    semesters: () => apiRequest("/v2/semesters"),
    universities: () => apiRequest("/v2/universities"),
    programs: () => apiRequest("/v2/programs"),
    partnerships: (params = {}) => {
      const query = new URLSearchParams(params).toString();
      return apiRequest(`/v2/partnerships${query ? `?${query}` : ""}`);
    },
    projects: (params = {}) => {
      const query = new URLSearchParams(params).toString();
      return apiRequest(`/v2/projects${query ? `?${query}` : ""}`);
    },
    metrics: {
      activePartnerships: () => apiRequest("/v2/metrics/active-partnerships"),
      studentsEngaged: () => apiRequest("/v2/metrics/students-engaged"),
      serviceHours: () => apiRequest("/v2/metrics/service-hours"),
      completionRate: () => apiRequest("/v2/metrics/completion-rate"),
      universityReach: () => apiRequest("/v2/metrics/university-reach"),
      programTypes: () => apiRequest("/v2/metrics/program-types"),
      retention: () => apiRequest("/v2/metrics/retention"),
    },
  },
};

export default api;
