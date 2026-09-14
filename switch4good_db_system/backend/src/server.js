/**
 * Switch4Good API Server
 * Entry point for the application
 */
require("dotenv").config();
const app = require("./app");
const { PORT } = require("./config");

// Export for Vercel serverless
module.exports = app;

// Only start HTTP server when running locally (not on Vercel)
if (!process.env.VERCEL) {
  app.listen(PORT, () => {
    console.log(`
╔════════════════════════════════════════════╗
║     Switch4Good API Server                 ║
╠════════════════════════════════════════════╣
║  Status:  Running                          ║
║  Port:    ${PORT}                              ║
║  Mode:    ${process.env.NODE_ENV || "development"}                      ║
╚════════════════════════════════════════════╝
  `);
  });
}
