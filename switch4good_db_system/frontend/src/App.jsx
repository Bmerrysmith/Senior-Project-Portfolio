import { useState, useEffect, useCallback } from "react";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:5000/api";;

// =============================================
// FILE UPLOAD COMPONENT
// =============================================
function FileUploadZone({ user, onUploadComplete, getAuthHeaders }) {
  const [isDragging, setIsDragging] = useState(false);
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [importing, setImporting] = useState(false);
  const [uploadResult, setUploadResult] = useState(null);
  const [error, setError] = useState(null);
  const [selectedTable, setSelectedTable] = useState("");
  const [supportedTables, setSupportedTables] = useState({});

  // Fetch supported tables on mount
  useEffect(() => {
    const fetchTables = async () => {
      try {
        const response = await fetch(`${API_URL}/upload/tables`, {
          headers: getAuthHeaders(),
        });
        if (response.ok) {
          setSupportedTables(await response.json());
        }
      } catch (err) {
        console.error("Error fetching tables:", err);
      }
    };
    fetchTables();
  }, []);

  const handleDragOver = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    const droppedFile = e.dataTransfer.files[0];
    if (droppedFile) {
      validateAndSetFile(droppedFile);
    }
  }, []);

  const handleFileSelect = (e) => {
    const selectedFile = e.target.files[0];
    if (selectedFile) {
      validateAndSetFile(selectedFile);
    }
  };

  const validateAndSetFile = (selectedFile) => {
    const allowedExtensions = [".csv", ".xls", ".xlsx"];
    const ext = selectedFile.name
      .toLowerCase()
      .slice(selectedFile.name.lastIndexOf("."));

    if (!allowedExtensions.includes(ext)) {
      setError("Invalid file type. Please upload a CSV or Excel file.");
      return;
    }

    if (selectedFile.size > 10 * 1024 * 1024) {
      setError("File too large. Maximum size is 10MB.");
      return;
    }

    setFile(selectedFile);
    setError(null);
    setUploadResult(null);
    setPreview(null);
    previewFile(selectedFile);
  };

  const previewFile = async (fileToPreview) => {
    setUploading(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append("file", fileToPreview);
      if (selectedTable) {
        formData.append("targetTable", selectedTable);
      }

      const response = await fetch(`${API_URL}/upload/preview`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${localStorage.getItem("token")}`,
        },
        body: formData,
      });

      if (response.ok) {
        const data = await response.json();
        setPreview(data);
      } else {
        const errData = await response.json();
        setError(errData.error || "Failed to preview file");
      }
    } catch (err) {
      setError("Error previewing file: " + err.message);
    } finally {
      setUploading(false);
    }
  };

  const importFile = async () => {
    if (!file || user?.role !== "admin") return;

    setImporting(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append("file", file);
      if (selectedTable) {
        formData.append("targetTable", selectedTable);
      }

      const response = await fetch(`${API_URL}/upload/import`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${localStorage.getItem("token")}`,
        },
        body: formData,
      });

      if (response.ok) {
        const result = await response.json();
        setUploadResult(result);
        if (onUploadComplete) onUploadComplete();
      } else {
        const errData = await response.json();
        setError(errData.error || "Failed to import file");
      }
    } catch (err) {
      setError("Error importing file: " + err.message);
    } finally {
      setImporting(false);
    }
  };

  const resetUpload = () => {
    setFile(null);
    setPreview(null);
    setUploadResult(null);
    setError(null);
    setSelectedTable("");
  };

  const getFileIcon = (filename) => {
    const ext = filename.toLowerCase().slice(filename.lastIndexOf("."));
    if (ext === ".csv") return "📊";
    if (ext === ".xlsx" || ext === ".xls") return "📗";
    return "📄";
  };

  return (
    <div className="upload-container">
      <div className="upload-header">
        <h3>📤 Import Data from CSV/Excel</h3>
        <p>
          Drag and drop files or click to browse. Data will be automatically
          mapped to the correct tables.
        </p>
      </div>

      {/* Table selector */}
      <div className="table-selector">
        <label>Target Table (optional - auto-detects if not selected):</label>
        <select
          value={selectedTable}
          onChange={(e) => {
            setSelectedTable(e.target.value);
            if (file) previewFile(file);
          }}
        >
          <option value="">Auto-detect from columns</option>
          {Object.entries(supportedTables).map(([key, info]) => (
            <option key={key} value={key}>
              {info.tableName} - {info.identifyColumns.slice(0, 3).join(", ")}
            </option>
          ))}
        </select>
      </div>

      {/* Drop zone */}
      <div
        className={`drop-zone ${isDragging ? "dragging" : ""} ${file ? "has-file" : ""}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => document.getElementById("file-input").click()}
      >
        <input
          type="file"
          id="file-input"
          accept=".csv,.xls,.xlsx"
          onChange={handleFileSelect}
          style={{ display: "none" }}
        />

        {!file ? (
          <div className="drop-content">
            <div className="drop-icon">📁</div>
            <p className="drop-text">Drag & Drop your CSV or Excel file here</p>
            <p className="drop-subtext">or click to browse</p>
            <div className="supported-formats">
              <span className="format-badge csv">CSV</span>
              <span className="format-badge excel">XLS</span>
              <span className="format-badge excel">XLSX</span>
            </div>
          </div>
        ) : (
          <div className="file-info">
            <span className="file-icon">{getFileIcon(file.name)}</span>
            <div className="file-details">
              <span className="file-name">{file.name}</span>
              <span className="file-size">
                {(file.size / 1024).toFixed(1)} KB
              </span>
            </div>
            <button
              className="remove-file"
              onClick={(e) => {
                e.stopPropagation();
                resetUpload();
              }}
            >
              ✕
            </button>
          </div>
        )}
      </div>

      {/* Status messages */}
      {error && <div className="upload-error">⚠️ {error}</div>}
      {uploading && <div className="upload-loading">🔄 Analyzing file...</div>}
      {importing && <div className="upload-loading">📥 Importing data...</div>}

      {/* Preview section */}
      {preview && preview.sheets && preview.sheets.length > 0 && (
        <div className="preview-section">
          <h4>📋 File Preview</h4>

          {preview.sheets.map((sheet, idx) => (
            <div key={idx} className="sheet-preview">
              <div className="sheet-header">
                <span className="sheet-name">{sheet.name}</span>
                <span className="sheet-info">
                  {sheet.rowCount} rows →
                  <strong>{sheet.tableName || "Unknown table"}</strong>
                </span>
              </div>

              {/* Column mapping */}
              {sheet.columnMapping && (
                <div className="column-mapping">
                  <h5>Column Mapping:</h5>
                  <div className="mapping-grid">
                    {Object.entries(sheet.columnMapping).map(
                      ([excelCol, mapping]) => (
                        <div
                          key={excelCol}
                          className={`mapping-item ${mapping.matched ? "matched" : "unmatched"}`}
                        >
                          <span className="excel-col">{excelCol}</span>
                          <span className="mapping-arrow">→</span>
                          <span className="db-col">
                            {mapping.dbColumn || "Not mapped"}
                          </span>
                        </div>
                      ),
                    )}
                  </div>
                </div>
              )}

              {/* Data preview table */}
              {sheet.preview && sheet.preview.length > 0 && (
                <div className="data-preview">
                  <h5>Data Preview (first 5 rows):</h5>
                  <div className="preview-table-wrapper">
                    <table className="preview-table">
                      <thead>
                        <tr>
                          {sheet.columns.map((col) => (
                            <th key={col}>{col}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {sheet.preview.map((row, rowIdx) => (
                          <tr key={rowIdx}>
                            {sheet.columns.map((col) => (
                              <td key={col}>{row[col] ?? "-"}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          ))}

          {/* Warnings */}
          {preview.warnings && preview.warnings.length > 0 && (
            <div className="preview-warnings">
              {preview.warnings.map((warning, idx) => (
                <div key={idx} className="warning-item">
                  ⚠️ {warning}
                </div>
              ))}
            </div>
          )}

          {/* Import button */}
          {user?.role === "admin" && (
            <div className="import-actions">
              <button
                className="import-btn"
                onClick={importFile}
                disabled={importing}
              >
                {importing ? "📥 Importing..." : "✅ Import Data to Database"}
              </button>
              <button className="cancel-btn" onClick={resetUpload}>
                Cancel
              </button>
            </div>
          )}
          {user?.role !== "admin" && (
            <div className="admin-only-notice">
              ℹ️ Only administrators can import data
            </div>
          )}
        </div>
      )}

      {/* Upload result */}
      {uploadResult && (
        <div className="upload-result">
          <h4>✅ Import Complete</h4>
          <div className="result-summary">
            <div className="result-stat success">
              <span className="stat-value">{uploadResult.imported}</span>
              <span className="stat-label">Records Imported</span>
            </div>
            <div className="result-stat total">
              <span className="stat-value">{uploadResult.totalRows}</span>
              <span className="stat-label">Total Rows</span>
            </div>
            {uploadResult.errors && uploadResult.errors.length > 0 && (
              <div className="result-stat errors">
                <span className="stat-value">{uploadResult.errors.length}</span>
                <span className="stat-label">Errors</span>
              </div>
            )}
          </div>

          {/* Sheet details */}
          {uploadResult.sheets &&
            uploadResult.sheets.map((sheet, idx) => (
              <div key={idx} className="sheet-result">
                <strong>{sheet.name}</strong>: {sheet.imported} of {sheet.rows}{" "}
                imported to <code>{sheet.table}</code>
                {sheet.skipped > 0 && (
                  <span className="skipped"> ({sheet.skipped} skipped)</span>
                )}
              </div>
            ))}

          {/* Errors */}
          {uploadResult.errors && uploadResult.errors.length > 0 && (
            <div className="import-errors">
              <h5>Import Errors:</h5>
              <div className="error-list">
                {uploadResult.errors.slice(0, 10).map((err, idx) => (
                  <div key={idx} className="error-item">
                    Row {err.row}: {err.error}
                  </div>
                ))}
                {uploadResult.errors.length > 10 && (
                  <div className="error-more">
                    ... and {uploadResult.errors.length - 10} more errors
                  </div>
                )}
              </div>
            </div>
          )}

          <button className="new-upload-btn" onClick={resetUpload}>
            📤 Upload Another File
          </button>
        </div>
      )}

      {/* Help section */}
      <div className="upload-help">
        <h5>📖 Supported Data Types:</h5>
        <div className="help-grid">
          {Object.entries(supportedTables)
            .slice(0, 6)
            .map(([key, info]) => (
              <div key={key} className="help-item">
                <strong>{info.tableName}</strong>
                <p>Headers: {info.exampleHeaders.slice(0, 5).join(", ")}...</p>
              </div>
            ))}
        </div>
      </div>
    </div>
  );
}

// =============================================
// EXPORT UTILITIES
// =============================================
const exportToCSV = (data, filename, columns) => {
  if (!data || data.length === 0) {
    alert("No data to export");
    return;
  }

  const headers = columns.map((col) => col.label).join(",");
  const rows = data.map((row) =>
    columns
      .map((col) => {
        let val = row[col.key] ?? "";
        // Escape quotes and wrap in quotes if contains comma
        if (
          typeof val === "string" &&
          (val.includes(",") || val.includes('"') || val.includes("\n"))
        ) {
          val = '"' + val.replace(/"/g, '""') + '"';
        }
        return val;
      })
      .join(","),
  );

  const csv = [headers, ...rows].join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `${filename}_${new Date().toISOString().split("T")[0]}.csv`;
  link.click();
};

const exportToPDF = (data, filename, columns, title) => {
  if (!data || data.length === 0) {
    alert("No data to export");
    return;
  }

  // Create printable HTML
  const html = `
    <!DOCTYPE html>
    <html>
    <head>
      <title>${title}</title>
      <style>
        body { font-family: Arial, sans-serif; padding: 20px; }
        h1 { color: #2e7d32; margin-bottom: 20px; }
        table { border-collapse: collapse; width: 100%; font-size: 10px; }
        th, td { border: 1px solid #ddd; padding: 6px; text-align: left; }
        th { background-color: #2e7d32; color: white; }
        tr:nth-child(even) { background-color: #f9f9f9; }
        .export-date { color: #666; margin-bottom: 10px; }
        @media print { body { -webkit-print-color-adjust: exact; print-color-adjust: exact; } }
      </style>
    </head>
    <body>
      <h1>🌱 Switch4Good - ${title}</h1>
      <p class="export-date">Exported: ${new Date().toLocaleString()}</p>
      <table>
        <thead>
          <tr>${columns.map((col) => `<th>${col.label}</th>`).join("")}</tr>
        </thead>
        <tbody>
          ${data.map((row) => `<tr>${columns.map((col) => `<td>${row[col.key] ?? "-"}</td>`).join("")}</tr>`).join("")}
        </tbody>
      </table>
    </body>
    </html>
  `;

  const printWindow = window.open("", "_blank");
  printWindow.document.write(html);
  printWindow.document.close();
  printWindow.onload = () => {
    printWindow.print();
  };
};

// =============================================
// LOGIN COMPONENT
// =============================================
function LoginPage({ onLogin }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError("");

    try {
      const response = await fetch(`${API_URL}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });

      const data = await response.json();

      if (response.ok && data.success) {
        localStorage.setItem("token", data.token);
        localStorage.setItem("user", JSON.stringify(data.user));
        onLogin(data.user);
      } else {
        setError(data.error || "Login failed");
      }
    } catch (err) {
      setError("Cannot connect to server. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-container">
      <div className="login-box">
        <div className="login-header">
          <h1>Switch4Good</h1>
          <p>Campus Advocacy Network</p>
        </div>
        <form onSubmit={handleSubmit} className="login-form">
          <h2>Sign In</h2>
          {error && <div className="login-error">{error}</div>}
          <div className="form-group">
            <label>Username</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="Enter username"
              required
              autoFocus
              autoComplete="username"
            />
          </div>
          <div className="form-group">
            <label>Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter password"
              required
              autoComplete="current-password"
            />
          </div>
          <button type="submit" className="login-btn" disabled={loading}>
            {loading ? "Signing in..." : "Sign In"}
          </button>
          <div className="security-notice">
            <p>Secure Connection</p>
          </div>
        </form>
      </div>
    </div>
  );
}

// =============================================
// MAIN APP COMPONENT
// =============================================
function App() {
  const [user, setUser] = useState(null);
  const [activeTab, setActiveTab] = useState("schools");
  const [loading, setLoading] = useState(true);
  const [dbStatus, setDbStatus] = useState({
    status: "loading",
    message: "Connecting...",
  });
  const [saveStatus, setSaveStatus] = useState({
    show: false,
    message: "",
    type: "",
  });
  const [filter, setFilter] = useState("");
  const [columnFilters, setColumnFilters] = useState({});

  // Data states - Normalized tables with data
  const [programs, setPrograms] = useState([]);
  const [students, setStudents] = useState([]);
  const [studentTracker, setStudentTracker] = useState([]);
  const [canMetrics, setCanMetrics] = useState([]);
  const [programDirectory, setProgramDirectory] = useState([]);
  const [schools, setSchools] = useState([]);
  const [dashboard, setDashboard] = useState({});

  // Check for existing session
  useEffect(() => {
    const token = localStorage.getItem("token");
    const savedUser = localStorage.getItem("user");
    if (token && savedUser) {
      fetch(`${API_URL}/auth/verify`, {
        headers: { Authorization: `Bearer ${token}` },
      })
        .then((res) => res.json())
        .then((data) => {
          if (data.valid) setUser(JSON.parse(savedUser));
          else {
            localStorage.removeItem("token");
            localStorage.removeItem("user");
          }
        })
        .catch(() => {
          localStorage.removeItem("token");
          localStorage.removeItem("user");
        });
    }
  }, []);

  useEffect(() => {
    if (user) {
      testConnection();
      fetchAll();
    }
  }, [user]);

  const handleLogin = (userData) => setUser(userData);
  const handleLogout = () => {
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    setUser(null);
  };
  const getAuthHeaders = () => ({
    "Content-Type": "application/json",
    Authorization: `Bearer ${localStorage.getItem("token")}`,
  });

  const showSaveStatus = (message, type = "success") => {
    setSaveStatus({ show: true, message, type });
    setTimeout(
      () => setSaveStatus({ show: false, message: "", type: "" }),
      3000,
    );
  };

  const testConnection = async () => {
    try {
      const response = await fetch(`${API_URL}/test-db`);
      const data = await response.json();
      setDbStatus(
        data.success
          ? { status: "success", message: "Connected" }
          : { status: "error", message: data.error },
      );
    } catch (err) {
      setDbStatus({ status: "error", message: "Cannot connect" });
    }
  };

  const fetchAll = async () => {
    setLoading(true);
    await Promise.all([
      fetchPrograms(),
      fetchStudents(),
      fetchStudentTracker(),
      fetchCanMetrics(),
      fetchProgramDirectory(),
      fetchSchools(),
      fetchDashboard(),
    ]);
    setLoading(false);
  };

  const fetchPrograms = async () => {
    try {
      const response = await fetch(`${API_URL}/programs`, {
        headers: getAuthHeaders(),
      });
      if (response.ok) setPrograms(await response.json());
      else if (response.status === 401) handleLogout();
    } catch (err) {
      console.log("Error:", err);
    }
  };

  const fetchStudents = async () => {
    try {
      const response = await fetch(`${API_URL}/students`, {
        headers: getAuthHeaders(),
      });
      if (response.ok) setStudents(await response.json());
      else if (response.status === 401) handleLogout();
    } catch (err) {
      console.log("Error:", err);
    }
  };

  const fetchStudentTracker = async () => {
    try {
      const response = await fetch(`${API_URL}/student-tracker`, {
        headers: getAuthHeaders(),
      });
      if (response.ok) setStudentTracker(await response.json());
      else if (response.status === 401) handleLogout();
    } catch (err) {
      console.log("Error:", err);
    }
  };

  const fetchCanMetrics = async () => {
    try {
      const response = await fetch(`${API_URL}/can-metrics`, {
        headers: getAuthHeaders(),
      });
      if (response.ok) setCanMetrics(await response.json());
      else if (response.status === 401) handleLogout();
    } catch (err) {
      console.log("Error:", err);
    }
  };

  const fetchProgramDirectory = async () => {
    try {
      const response = await fetch(`${API_URL}/program-directory`, {
        headers: getAuthHeaders(),
      });
      if (response.ok) setProgramDirectory(await response.json());
      else if (response.status === 401) handleLogout();
    } catch (err) {
      console.log("Error:", err);
    }
  };

  const fetchSchools = async () => {
    try {
      const response = await fetch(`${API_URL}/schools`, {
        headers: getAuthHeaders(),
      });
      if (response.ok) setSchools(await response.json());
      else if (response.status === 401) handleLogout();
    } catch (err) {
      console.log("Error:", err);
    }
  };

  const fetchDashboard = async () => {
    try {
      const response = await fetch(`${API_URL}/dashboard`, {
        headers: getAuthHeaders(),
      });
      if (response.ok) setDashboard(await response.json());
      else if (response.status === 401) handleLogout();
    } catch (err) {
      console.log("Error:", err);
    }
  };

  // CRUD Operations
  const saveData = async (endpoint, id, data, tableName) => {
    if (user?.role === "viewer") {
      showSaveStatus("View-only cannot edit", "error");
      return false;
    }
    try {
      const response = await fetch(`${API_URL}/${endpoint}/${id}`, {
        method: "PUT",
        headers: getAuthHeaders(),
        body: JSON.stringify(data),
      });
      if (response.ok) {
        showSaveStatus(`✓ Saved to ${tableName}`, "success");
        return true;
      }
      showSaveStatus("Failed to save", "error");
      return false;
    } catch (err) {
      showSaveStatus("Error: " + err.message, "error");
      return false;
    }
  };

  const deleteRow = async (endpoint, id, tableName) => {
    if (user?.role === "viewer") {
      showSaveStatus("View-only cannot delete", "error");
      return;
    }
    if (!confirm(`Delete this ${tableName} record?`)) return;
    try {
      const response = await fetch(`${API_URL}/${endpoint}/${id}`, {
        method: "DELETE",
        headers: getAuthHeaders(),
      });
      if (response.ok) {
        showSaveStatus(`✓ Deleted`, "success");
        fetchAll();
      } else showSaveStatus("Failed to delete", "error");
    } catch (err) {
      showSaveStatus("Error: " + err.message, "error");
    }
  };

  const addNewRow = async (endpoint, defaultData, tableName) => {
    if (user?.role === "viewer") {
      showSaveStatus("View-only cannot add", "error");
      return;
    }
    try {
      const response = await fetch(`${API_URL}/${endpoint}`, {
        method: "POST",
        headers: getAuthHeaders(),
        body: JSON.stringify(defaultData),
      });
      if (response.ok) {
        showSaveStatus(`✓ Added ${tableName}`, "success");
        fetchAll();
      } else showSaveStatus("Failed to add", "error");
    } catch (err) {
      showSaveStatus("Error: " + err.message, "error");
    }
  };

  // Editable Cell Component
  const EditableCell = ({
    value,
    rowId,
    field,
    endpoint,
    tableName,
    className = "",
  }) => {
    const [isEditing, setIsEditing] = useState(false);
    const [editValue, setEditValue] = useState(value || "");
    const canEdit = user?.role !== "viewer";

    const handleSave = async () => {
      if (editValue !== value) {
        const success = await saveData(
          endpoint,
          rowId,
          { [field]: editValue },
          tableName,
        );
        if (success) fetchAll();
      }
      setIsEditing(false);
    };

    if (isEditing && canEdit) {
      return (
        <td className={className}>
          <input
            type="text"
            value={editValue}
            onChange={(e) => setEditValue(e.target.value)}
            onBlur={handleSave}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleSave();
              if (e.key === "Escape") {
                setEditValue(value || "");
                setIsEditing(false);
              }
            }}
            autoFocus
            className="cell-input"
          />
        </td>
      );
    }
    return (
      <td
        className={`${className} ${canEdit ? "editable-cell" : ""}`}
        onClick={() => canEdit && setIsEditing(true)}
        title={canEdit ? "Click to edit" : "View only"}
      >
        {value || "-"}
      </td>
    );
  };

  // Filter data
  const filterData = (data, filterableColumns = []) => {
    let result = data;

    // Apply column filters
    Object.entries(columnFilters).forEach(([key, value]) => {
      if (value && value !== "all") {
        result = result.filter(
          (row) =>
            String(row[key] ?? "").toLowerCase() ===
            String(value).toLowerCase(),
        );
      }
    });

    // Apply text search filter
    if (filter) {
      result = result.filter((row) =>
        Object.values(row).some((val) =>
          String(val).toLowerCase().includes(filter.toLowerCase()),
        ),
      );
    }

    return result;
  };

  // Get unique values for a column (for dropdown options)
  const getUniqueValues = (data, columnKey) => {
    const values = new Set();
    data.forEach((row) => {
      const val = row[columnKey];
      if (val !== null && val !== undefined && val !== "") {
        values.add(val);
      }
    });

    // Special sorting for semester columns - chronological order
    if (columnKey === "semester" || columnKey.includes("semester")) {
      return Array.from(values).sort((a, b) => {
        // Parse semester strings like "Spring 2020", "Fall 2008"
        const parseSemaster = (s) => {
          const str = String(s);
          const match = str.match(/(Spring|Summer|Fall|Winter)\s*(\d{4})/i);
          if (match) {
            const seasonOrder = { spring: 0, summer: 1, fall: 2, winter: 3 };
            const season = match[1].toLowerCase();
            const year = parseInt(match[2]);
            return { year, seasonNum: seasonOrder[season] || 0, original: str };
          }
          return { year: 0, seasonNum: 0, original: str };
        };

        const parsedA = parseSemaster(a);
        const parsedB = parseSemaster(b);

        // Sort by year descending (most recent first), then by season
        if (parsedB.year !== parsedA.year) {
          return parsedB.year - parsedA.year;
        }
        return parsedB.seasonNum - parsedA.seasonNum;
      });
    }

    return Array.from(values).sort((a, b) =>
      String(a).localeCompare(String(b)),
    );
  };

  // Clear all filters
  const clearFilters = () => {
    setFilter("");
    setColumnFilters({});
  };

  // Update a specific column filter
  const updateColumnFilter = (columnKey, value) => {
    setColumnFilters((prev) => ({
      ...prev,
      [columnKey]: value,
    }));
  };

  // Column definitions for each table (filterable = true means show dropdown filter)
  const programsColumns = [
    { key: "id", label: "ID" },
    { key: "program", label: "Program" },
    { key: "school", label: "School", filterable: true },
    { key: "website", label: "Website" },
    { key: "program_type", label: "Type", filterable: true },
    {
      key: "needs_formalization",
      label: "Needs Formalization",
      filterable: true,
    },
    { key: "notes", label: "Notes" },
  ];

  const studentsColumns = [
    { key: "id", label: "ID" },
    { key: "name", label: "Name" },
    { key: "email_address", label: "Email" },
    { key: "pronouns", label: "Pronouns", filterable: true },
    { key: "tshirt_size", label: "T-Shirt", filterable: true },
    { key: "year_in_school", label: "Year", filterable: true },
    { key: "areas_of_interest", label: "Areas of Interest" },
  ];

  const studentTrackerColumns = [
    { key: "id", label: "ID" },
    { key: "semester", label: "Semester", filterable: true, priority: 1 },
    { key: "name", label: "Name" },
    { key: "email_address", label: "Email" },
    { key: "school", label: "School", filterable: true },
    { key: "program", label: "Program", filterable: true },
    { key: "project", label: "Project", filterable: true },
    { key: "sg4_staff", label: "SG4 Staff", filterable: true },
    { key: "year_in_school", label: "Year", filterable: true },
    { key: "pronouns", label: "Pronouns", filterable: true },
    { key: "tshirt_size", label: "T-Shirt", filterable: true },
    { key: "areas_of_interest", label: "Areas of Interest" },
    { key: "project_start_date", label: "Start Date" },
    { key: "project_end_date", label: "End Date" },
    { key: "meeting_cadence", label: "Meeting Cadence", filterable: true },
    { key: "conflicting_datetimes", label: "Conflicts" },
    { key: "success_metric", label: "Success Metric", filterable: true },
    { key: "total_hours", label: "Total Hours" },
  ];

  const canMetricsColumns = [
    { key: "id", label: "ID" },
    { key: "date", label: "Date" },
    { key: "is_ongoing", label: "Ongoing", filterable: true },
    { key: "impression", label: "Impression", filterable: true },
    { key: "touchpoints", label: "Touchpoints" },
    { key: "engagements", label: "Engagements" },
    { key: "conversions", label: "Conversions" },
    { key: "notes", label: "Notes" },
  ];

  const programDirectoryColumns = [
    { key: "id", label: "ID" },
    { key: "semester", label: "Semester", filterable: true, priority: 1 },
    { key: "program", label: "Program" },
    { key: "school", label: "School", filterable: true },
    { key: "program_type", label: "Type", filterable: true },
    { key: "website", label: "Website" },
    { key: "is_active", label: "Active", filterable: true },
    { key: "sg4_staff_contact", label: "SG4 Contact", filterable: true },
    { key: "most_recent_contact_date", label: "Last Contact" },
    { key: "partner_email", label: "Partner Email" },
    {
      key: "needs_formalization",
      label: "Needs Formalization",
      filterable: true,
    },
    { key: "notes", label: "Notes" },
  ];

  const schoolsColumns = [
    { key: "school_id", label: "ID" },
    { key: "school_name", label: "School Name" },
  ];

  // Render table with all columns
  const renderTable = (data, columns, endpoint, tableName, defaultNew) => {
    // Sort filterable columns - semester first (priority 1), then others
    const filterableColumns = columns
      .filter((c) => c.filterable)
      .sort((a, b) => (a.priority || 99) - (b.priority || 99));
    const filteredData = filterData(data, filterableColumns);
    const idField = columns.find((c) => c.key.includes("id"))?.key || "id";
    const hasActiveFilters =
      filter || Object.values(columnFilters).some((v) => v && v !== "all");

    // Check if this table has a semester column
    const hasSemester = filterableColumns.some((c) => c.key === "semester");

    return (
      <div className="spreadsheet-container">
        <div className="table-header">
          <h3>
            {tableName} ({filteredData.length} records)
          </h3>
          <div className="table-actions">
            <input
              type="text"
              placeholder="🔍 Search all..."
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              className="filter-input"
            />
            <button
              onClick={() => exportToCSV(filteredData, endpoint, columns)}
              className="export-btn csv"
            >
              📥 CSV
            </button>
            <button
              onClick={() =>
                exportToPDF(filteredData, endpoint, columns, tableName)
              }
              className="export-btn pdf"
            >
              📄 PDF
            </button>
            {user?.role !== "viewer" && (
              <button
                onClick={() => addNewRow(endpoint, defaultNew, tableName)}
                className="add-btn"
              >
                ➕ Add Row
              </button>
            )}
          </div>
        </div>

        {/* Filter dropdowns */}
        {filterableColumns.length > 0 && (
          <div className="filter-bar">
            {/* Primary filter (Semester) */}
            {hasSemester && (
              <div className="primary-filter">
                <label className="filter-label">📅 Semester:</label>
                <select
                  value={columnFilters["semester"] || "all"}
                  onChange={(e) =>
                    updateColumnFilter("semester", e.target.value)
                  }
                  className={`semester-select ${columnFilters["semester"] && columnFilters["semester"] !== "all" ? "active-filter" : ""}`}
                >
                  <option value="all">All Semesters</option>
                  {getUniqueValues(data, "semester").map((val) => (
                    <option key={val} value={val}>
                      {String(val)}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {/* Other filters */}
            <div className="secondary-filters">
              <span className="filter-label">More Filters:</span>
              <div className="filter-dropdowns">
                {filterableColumns
                  .filter((col) => col.key !== "semester")
                  .map((col) => (
                    <div key={col.key} className="filter-dropdown">
                      <select
                        value={columnFilters[col.key] || "all"}
                        onChange={(e) =>
                          updateColumnFilter(col.key, e.target.value)
                        }
                        className={
                          columnFilters[col.key] &&
                          columnFilters[col.key] !== "all"
                            ? "active-filter"
                            : ""
                        }
                      >
                        <option value="all">{col.label}: All</option>
                        {getUniqueValues(data, col.key).map((val) => (
                          <option key={val} value={val}>
                            {String(val)}
                          </option>
                        ))}
                      </select>
                    </div>
                  ))}
              </div>
            </div>

            {hasActiveFilters && (
              <button onClick={clearFilters} className="clear-filters-btn">
                ✕ Clear All
              </button>
            )}
          </div>
        )}

        <div className="table-wrapper">
          <table className="spreadsheet">
            <thead>
              <tr>
                {columns.map((col) => (
                  <th key={col.key}>{col.label}</th>
                ))}
                {user?.role !== "viewer" && <th>Actions</th>}
              </tr>
            </thead>
            <tbody>
              {filteredData.length === 0 ? (
                <tr>
                  <td colSpan={columns.length + 1} className="no-data">
                    No data found
                  </td>
                </tr>
              ) : (
                filteredData.map((row) => (
                  <tr key={row[idField]}>
                    {columns.map((col) =>
                      col.key.includes("id") ? (
                        <td key={col.key}>{row[col.key]}</td>
                      ) : (
                        <EditableCell
                          key={col.key}
                          value={row[col.key]}
                          rowId={row[idField]}
                          field={col.key}
                          endpoint={endpoint}
                          tableName={tableName}
                        />
                      ),
                    )}
                    {user?.role !== "viewer" && (
                      <td>
                        <button
                          onClick={() =>
                            deleteRow(endpoint, row[idField], tableName)
                          }
                          className="delete-btn"
                        >
                          🗑️
                        </button>
                      </td>
                    )}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    );
  };

  // Show login if not authenticated
  if (!user) return <LoginPage onLogin={handleLogin} />;

  return (
    <div className="app">
      <header className="app-header">
        <div className="header-left">
          <h1>SWITCH4GOOD</h1>
        </div>
        <div className="header-right">
          <span className={`db-status ${dbStatus.status}`}>
            {dbStatus.status === "success" ? "🟢" : "🔴"} {dbStatus.message}
          </span>
          <div className="user-info">
            <span>👤 {user.name}</span>
            <span className="user-role">({user.role})</span>
            <button onClick={handleLogout} className="logout-btn">
              Logout
            </button>
          </div>
        </div>
      </header>

      {saveStatus.show && (
        <div className={`save-toast ${saveStatus.type}`}>
          {saveStatus.message}
        </div>
      )}

      <div className="dashboard-stats">
        <div className="stat-card">
          <span className="stat-number">{schools.length}</span>
          <span className="stat-label">Schools</span>
        </div>
        <div className="stat-card">
          <span className="stat-number">{programs.length}</span>
          <span className="stat-label">Programs</span>
        </div>
        <div className="stat-card">
          <span className="stat-number">{students.length}</span>
          <span className="stat-label">Students</span>
        </div>
        <div className="stat-card">
          <span className="stat-number">{studentTracker.length}</span>
          <span className="stat-label">Participation</span>
        </div>
        <div className="stat-card">
          <span className="stat-number">{canMetrics.length}</span>
          <span className="stat-label">CAN Metrics</span>
        </div>
        <div className="stat-card">
          <span className="stat-number">{programDirectory.length}</span>
          <span className="stat-label">Directory</span>
        </div>
      </div>

      <div className="spreadsheet-tabs">
        <button
          className={activeTab === "schools" ? "active" : ""}
          onClick={() => {
            setActiveTab("schools");
            clearFilters();
          }}
        >
          🏫 Schools
        </button>
        <button
          className={activeTab === "programs" ? "active" : ""}
          onClick={() => {
            setActiveTab("programs");
            clearFilters();
          }}
        >
          📚 Programs
        </button>
        <button
          className={activeTab === "students" ? "active" : ""}
          onClick={() => {
            setActiveTab("students");
            clearFilters();
          }}
        >
          👨‍🎓 Students
        </button>
        <button
          className={activeTab === "student-tracker" ? "active" : ""}
          onClick={() => {
            setActiveTab("student-tracker");
            clearFilters();
          }}
        >
          📊 Student Tracker
        </button>
        <button
          className={activeTab === "can-metrics" ? "active" : ""}
          onClick={() => {
            setActiveTab("can-metrics");
            clearFilters();
          }}
        >
          📈 CAN Metrics
        </button>
        <button
          className={activeTab === "program-directory" ? "active" : ""}
          onClick={() => {
            setActiveTab("program-directory");
            clearFilters();
          }}
        >
          📁 Program Directory
        </button>
        {user?.role === "admin" && (
          <button
            className={activeTab === "upload" ? "active" : ""}
            onClick={() => {
              setActiveTab("upload");
              clearFilters();
            }}
          >
            📤 Upload Data
          </button>
        )}
      </div>

      <main className="main-content">
        {loading ? (
          <div className="loading">Loading data...</div>
        ) : (
          <>
            {activeTab === "schools" &&
              renderTable(schools, schoolsColumns, "schools", "🏫 Schools", {
                school_name: "New School",
              })}
            {activeTab === "programs" &&
              renderTable(
                programs,
                programsColumns,
                "programs",
                "📚 Programs",
                {
                  program_name: "New Program",
                  school_id: null,
                  website: "",
                  program_type: "",
                  notes: "",
                },
              )}
            {activeTab === "students" &&
              renderTable(
                students,
                studentsColumns,
                "students",
                "👨‍🎓 Students",
                {
                  full_name: "New Student",
                  email: "",
                  pronouns: "",
                  tshirt_size: "",
                  year_in_school: "",
                  areas_of_interest: "",
                },
              )}
            {activeTab === "student-tracker" &&
              renderTable(
                studentTracker,
                studentTrackerColumns,
                "student-tracker",
                "📊 Student Participation",
                { name: "New Entry" },
              )}
            {activeTab === "can-metrics" &&
              renderTable(
                canMetrics,
                canMetricsColumns,
                "can-metrics",
                "📈 CAN Metrics",
                {
                  metric_date: null,
                  impression: "",
                  touchpoints: 0,
                  engagements: 0,
                  conversions: 0,
                  notes: "",
                },
              )}
            {activeTab === "program-directory" &&
              renderTable(
                programDirectory,
                programDirectoryColumns,
                "program-directory",
                "📁 Program Directory",
                { program: "New Program" },
              )}
            {activeTab === "upload" && user?.role === "admin" && (
              <FileUploadZone
                user={user}
                onUploadComplete={fetchAll}
                getAuthHeaders={getAuthHeaders}
              />
            )}
          </>
        )}
      </main>

      <footer className="app-footer">
        <p>Switch4Good CAN - Secure Data Management System</p>
        {user?.role !== "viewer" && (
          <p className="edit-hint">
            Click any cell to edit - Changes save automatically
          </p>
        )}
      </footer>
    </div>
  );
}

export default App;
