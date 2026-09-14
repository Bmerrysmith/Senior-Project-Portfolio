const express = require("express");
const cors = require("cors");
const routes = require("./routes");
const pool = require("./config/database");

const app = express();

// =============================================
// Middleware
// =============================================
app.use(cors());
app.use(express.json());

// Request logging (development)
if (process.env.NODE_ENV !== "production") {
  app.use((req, res, next) => {
    console.log(`${new Date().toISOString()} ${req.method} ${req.path}`);
    next();
  });
}

// =============================================
// Routes
// =============================================

// Health check (no auth required)
app.get("/", (req, res) => {
  res.json({ message: "Switch4Good API is running!" });
});

// Database connection test (no auth required)
app.get("/api/test-db", async (req, res) => {
  try {
    const result = await pool.query("SELECT NOW()");
    res.json({
      success: true,
      message: "Database connected successfully!",
      timestamp: result.rows[0].now,
    });
  } catch (err) {
    res.status(500).json({
      success: false,
      error: err.message,
    });
  }
});

// Mount API routes
app.use("/api", routes);

// =============================================
// Error Handling
// =============================================

// 404 handler
app.use((req, res) => {
  res.status(404).json({ error: "Endpoint not found" });
});

// Global error handler
app.use((err, req, res, next) => {
  console.error("Server error:", err);
  res.status(500).json({ error: "Internal server error" });
});

module.exports = app;
