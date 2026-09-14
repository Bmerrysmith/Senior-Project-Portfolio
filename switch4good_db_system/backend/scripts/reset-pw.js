require("dotenv").config();
const bcrypt = require("bcryptjs");
const { Pool } = require("pg");

const pool = new Pool({
  user: process.env.DB_USER,
  password: process.env.DB_PASSWORD,
  host: process.env.DB_HOST,
  port: process.env.DB_PORT,
  database: process.env.DB_NAME,
  ssl: { rejectUnauthorized: false },
});

bcrypt
  .hash("Admin1234!", 12)
  .then((hash) => {
    return pool.query(
      "UPDATE admin_users SET password_hash = $1, failed_login_attempts = 0, locked_until = NULL WHERE username = $2",
      [hash, "admin"],
    );
  })
  .then(() => {
    console.log("Password reset successfully. Login with: admin / Admin1234!");
    pool.end();
  })
  .catch((e) => {
    console.error(e.message);
    pool.end();
  });
