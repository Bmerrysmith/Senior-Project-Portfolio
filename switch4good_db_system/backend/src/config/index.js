require("dotenv").config();

module.exports = {
  // Server config
  PORT: process.env.PORT || 5000,
  NODE_ENV: process.env.NODE_ENV || "development",

  // JWT config
  JWT_SECRET: process.env.JWT_SECRET || "switch4good-secret-key-2026",
  JWT_EXPIRY: process.env.JWT_EXPIRY || "24h",

  // Security config
  MAX_LOGIN_ATTEMPTS: 5,
  LOCKOUT_DURATION_MINUTES: 15,

  // Database config (exported separately from database.js)
  DB_HOST: process.env.DB_HOST,
  DB_PORT: process.env.DB_PORT,
  DB_USER: process.env.DB_USER,
  DB_NAME: process.env.DB_NAME,
};
