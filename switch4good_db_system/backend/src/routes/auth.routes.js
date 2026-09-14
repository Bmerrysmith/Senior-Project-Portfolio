const router = require("express").Router();
const bcrypt = require("bcryptjs");
const jwt = require("jsonwebtoken");
const pool = require("../config/database");
const { JWT_SECRET, MAX_LOGIN_ATTEMPTS, LOCKOUT_DURATION_MINUTES } = require("../config");
const { authenticate } = require("../middleware/auth");

/**
 * @route   POST /api/auth/login
 * @desc    Authenticate user and get token
 * @access  Public
 */
router.post("/login", async (req, res) => {
  try {
    const { username, password } = req.body;

    if (!username || !password) {
      return res.status(400).json({ error: "Username and password are required" });
    }

    // Query user from database
    const userResult = await pool.query(
      "SELECT * FROM admin_users WHERE username = $1",
      [username.toLowerCase()]
    );

    if (userResult.rows.length === 0) {
      return res.status(401).json({ error: "Invalid username or password" });
    }

    const user = userResult.rows[0];

    // Check if account is active
    if (!user.is_active) {
      return res.status(401).json({ error: "Account is disabled. Contact administrator." });
    }

    // Check if account is locked
    if (user.locked_until && new Date(user.locked_until) > new Date()) {
      const minutesLeft = Math.ceil((new Date(user.locked_until) - new Date()) / 60000);
      return res.status(401).json({
        error: `Account is locked. Try again in ${minutesLeft} minutes.`,
      });
    }

    // Verify password
    const validPassword = await bcrypt.compare(password, user.password_hash);

    if (!validPassword) {
      // Increment failed login attempts
      const newAttempts = (user.failed_login_attempts || 0) + 1;

      if (newAttempts >= MAX_LOGIN_ATTEMPTS) {
        const lockUntil = new Date(Date.now() + LOCKOUT_DURATION_MINUTES * 60000);
        await pool.query(
          "UPDATE admin_users SET failed_login_attempts = $1, locked_until = $2 WHERE id = $3",
          [newAttempts, lockUntil, user.id]
        );
        return res.status(401).json({
          error: `Too many failed attempts. Account locked for ${LOCKOUT_DURATION_MINUTES} minutes.`,
        });
      } else {
        await pool.query(
          "UPDATE admin_users SET failed_login_attempts = $1 WHERE id = $2",
          [newAttempts, user.id]
        );
        return res.status(401).json({ error: "Invalid username or password" });
      }
    }

    // Successful login - reset failed attempts
    await pool.query(
      "UPDATE admin_users SET failed_login_attempts = 0, locked_until = NULL, last_login = CURRENT_TIMESTAMP WHERE id = $1",
      [user.id]
    );

    const token = jwt.sign(
      {
        id: user.id,
        username: user.username,
        role: user.role,
        name: user.name,
      },
      JWT_SECRET,
      { expiresIn: "24h" }
    );

    res.json({
      success: true,
      token,
      user: {
        id: user.id,
        username: user.username,
        role: user.role,
        name: user.name,
      },
    });
  } catch (err) {
    console.error("Login error:", err);
    res.status(500).json({ error: "Authentication service unavailable" });
  }
});

/**
 * @route   GET /api/auth/verify
 * @desc    Verify JWT token
 * @access  Public
 */
router.get("/verify", (req, res) => {
  const token = req.headers.authorization?.split(" ")[1];

  if (!token) {
    return res.status(401).json({ error: "No token provided" });
  }

  try {
    const decoded = jwt.verify(token, JWT_SECRET);
    res.json({ valid: true, user: decoded });
  } catch (err) {
    res.status(401).json({ error: "Invalid token" });
  }
});

/**
 * @route   PATCH /api/auth/password
 * @desc    Change own password
 * @access  Private
 */
router.patch("/password", authenticate, async (req, res) => {
  try {
    const { currentPassword, newPassword } = req.body;

    if (!newPassword || newPassword.length < 8) {
      return res.status(400).json({ error: "New password must be at least 8 characters" });
    }

    const userResult = await pool.query("SELECT * FROM admin_users WHERE id = $1", [req.user.id]);
    if (userResult.rows.length === 0) {
      return res.status(404).json({ error: "User not found" });
    }

    const user = userResult.rows[0];

    // Verify current password
    if (!currentPassword) {
      return res.status(400).json({ error: "Current password is required" });
    }
    const validPassword = await bcrypt.compare(currentPassword, user.password_hash);
    if (!validPassword) {
      return res.status(401).json({ error: "Current password is incorrect" });
    }

    // Hash and save new password
    const passwordHash = await bcrypt.hash(newPassword, 12);
    await pool.query(
      `UPDATE admin_users SET password_hash = $1, password_changed_at = CURRENT_TIMESTAMP WHERE id = $2`,
      [passwordHash, req.user.id]
    );

    res.json({ success: true, message: "Password changed successfully" });
  } catch (err) {
    console.error("Password change error:", err);
    res.status(500).json({ error: err.message });
  }
});

module.exports = router;
