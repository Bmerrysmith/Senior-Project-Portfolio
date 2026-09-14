const { Pool } = require("pg");
require("dotenv").config();

/**
 * PostgreSQL Connection Pool
 * Configured via environment variables
 */
const pool = new Pool({
  user: process.env.DB_USER,
  password: process.env.DB_PASSWORD,
  host: process.env.DB_HOST,
  port: process.env.DB_PORT,
  database: process.env.DB_NAME,
  ssl: process.env.DB_SSL === "true" ? { rejectUnauthorized: false } : false,
});

// Connection event handlers
pool.on("connect", () => {
  console.log("✓ Connected to PostgreSQL database");
});

pool.on("error", (err) => {
  console.error("✗ Database connection error:", err);
  process.exit(-1);
});

module.exports = pool;
