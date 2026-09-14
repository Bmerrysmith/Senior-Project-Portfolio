const router = require("express").Router();
const bcrypt = require("bcryptjs");
const pool = require("../config/database");
const { authenticate, requireAdmin } = require("../middleware/auth");

// Apply auth middleware to all routes
router.use(authenticate);
router.use(requireAdmin);

/**
 * @route   GET /api/admin/users
 * @desc    Get all admin users
 * @access  Admin only
 */
router.get("/users", async (req, res) => {
  try {
    const result = await pool.query(`
      SELECT id, username, email, name, role, is_active, 
             failed_login_attempts, locked_until, last_login, 
             password_changed_at, created_at, updated_at
      FROM admin_users 
      ORDER BY created_at DESC
    `);
    res.json(result.rows);
  } catch (err) {
    console.error("Error fetching admin users:", err);
    res.status(500).json({ error: err.message });
  }
});

/**
 * @route   GET /api/admin/users/:id
 * @desc    Get single admin user
 * @access  Admin only
 */
router.get("/users/:id", async (req, res) => {
  try {
    const { id } = req.params;
    const result = await pool.query(
      `SELECT id, username, email, name, role, is_active, 
              failed_login_attempts, locked_until, last_login,
              password_changed_at, created_at, updated_at
       FROM admin_users WHERE id = $1`,
      [id]
    );

    if (result.rows.length === 0) {
      return res.status(404).json({ error: "User not found" });
    }
    res.json(result.rows[0]);
  } catch (err) {
    console.error("Error fetching admin user:", err);
    res.status(500).json({ error: err.message });
  }
});

/**
 * @route   POST /api/admin/users
 * @desc    Create new admin user
 * @access  Admin only
 */
router.post("/users", async (req, res) => {
  try {
    const { username, password, email, name, role } = req.body;

    // Validation
    if (!username || !password || !name) {
      return res.status(400).json({ error: "Username, password, and name are required" });
    }

    if (password.length < 8) {
      return res.status(400).json({ error: "Password must be at least 8 characters" });
    }

    const validRoles = ["admin", "staff", "viewer"];
    if (role && !validRoles.includes(role)) {
      return res.status(400).json({ error: "Invalid role. Must be admin, staff, or viewer" });
    }

    // Check if username already exists
    const existingUser = await pool.query(
      "SELECT id FROM admin_users WHERE username = $1",
      [username.toLowerCase()]
    );
    if (existingUser.rows.length > 0) {
      return res.status(400).json({ error: "Username already exists" });
    }

    // Check if email already exists
    if (email) {
      const existingEmail = await pool.query(
        "SELECT id FROM admin_users WHERE email = $1",
        [email.toLowerCase()]
      );
      if (existingEmail.rows.length > 0) {
        return res.status(400).json({ error: "Email already exists" });
      }
    }

    // Hash password and create user
    const passwordHash = await bcrypt.hash(password, 12);
    const result = await pool.query(
      `INSERT INTO admin_users (username, password_hash, email, name, role)
       VALUES ($1, $2, $3, $4, $5)
       RETURNING id, username, email, name, role, is_active, created_at`,
      [username.toLowerCase(), passwordHash, email?.toLowerCase() || null, name, role || "viewer"]
    );

    res.status(201).json({
      success: true,
      message: "User created successfully",
      user: result.rows[0],
    });
  } catch (err) {
    console.error("Error creating admin user:", err);
    res.status(500).json({ error: err.message });
  }
});

/**
 * @route   PUT /api/admin/users/:id
 * @desc    Update admin user
 * @access  Admin only
 */
router.put("/users/:id", async (req, res) => {
  try {
    const { id } = req.params;
    const { email, name, role, is_active } = req.body;

    // Check if user exists
    const existingUser = await pool.query("SELECT * FROM admin_users WHERE id = $1", [id]);
    if (existingUser.rows.length === 0) {
      return res.status(404).json({ error: "User not found" });
    }

    // Prevent deactivating own account
    if (req.user.id === parseInt(id) && is_active === false) {
      return res.status(400).json({ error: "Cannot deactivate your own account" });
    }

    const validRoles = ["admin", "staff", "viewer"];
    if (role && !validRoles.includes(role)) {
      return res.status(400).json({ error: "Invalid role. Must be admin, staff, or viewer" });
    }

    // Check email uniqueness
    if (email && email.toLowerCase() !== existingUser.rows[0].email) {
      const existingEmail = await pool.query(
        "SELECT id FROM admin_users WHERE email = $1 AND id != $2",
        [email.toLowerCase(), id]
      );
      if (existingEmail.rows.length > 0) {
        return res.status(400).json({ error: "Email already in use" });
      }
    }

    const result = await pool.query(
      `UPDATE admin_users SET
         email = COALESCE($1, email),
         name = COALESCE($2, name),
         role = COALESCE($3, role),
         is_active = COALESCE($4, is_active),
         updated_at = CURRENT_TIMESTAMP
       WHERE id = $5
       RETURNING id, username, email, name, role, is_active, updated_at`,
      [email?.toLowerCase() || null, name, role, is_active, id]
    );

    res.json({
      success: true,
      message: "User updated successfully",
      user: result.rows[0],
    });
  } catch (err) {
    console.error("Error updating admin user:", err);
    res.status(500).json({ error: err.message });
  }
});

/**
 * @route   PATCH /api/admin/users/:id/password
 * @desc    Reset user password (admin can reset any)
 * @access  Admin only
 */
router.patch("/users/:id/password", async (req, res) => {
  try {
    const { id } = req.params;
    const { newPassword } = req.body;

    if (!newPassword || newPassword.length < 8) {
      return res.status(400).json({ error: "New password must be at least 8 characters" });
    }

    const userResult = await pool.query("SELECT id FROM admin_users WHERE id = $1", [id]);
    if (userResult.rows.length === 0) {
      return res.status(404).json({ error: "User not found" });
    }

    const passwordHash = await bcrypt.hash(newPassword, 12);
    await pool.query(
      `UPDATE admin_users SET password_hash = $1, password_changed_at = CURRENT_TIMESTAMP WHERE id = $2`,
      [passwordHash, id]
    );

    res.json({ success: true, message: "Password reset successfully" });
  } catch (err) {
    console.error("Error resetting password:", err);
    res.status(500).json({ error: err.message });
  }
});

/**
 * @route   PATCH /api/admin/users/:id/unlock
 * @desc    Unlock user account
 * @access  Admin only
 */
router.patch("/users/:id/unlock", async (req, res) => {
  try {
    const { id } = req.params;
    const result = await pool.query(
      `UPDATE admin_users SET failed_login_attempts = 0, locked_until = NULL, updated_at = CURRENT_TIMESTAMP
       WHERE id = $1 RETURNING id, username, name`,
      [id]
    );

    if (result.rows.length === 0) {
      return res.status(404).json({ error: "User not found" });
    }

    res.json({
      success: true,
      message: `Account ${result.rows[0].username} has been unlocked`,
    });
  } catch (err) {
    console.error("Error unlocking user:", err);
    res.status(500).json({ error: err.message });
  }
});

/**
 * @route   DELETE /api/admin/users/:id
 * @desc    Delete admin user
 * @access  Admin only
 */
router.delete("/users/:id", async (req, res) => {
  try {
    const { id } = req.params;

    if (req.user.id === parseInt(id)) {
      return res.status(400).json({ error: "Cannot delete your own account" });
    }

    const existingUser = await pool.query("SELECT username FROM admin_users WHERE id = $1", [id]);
    if (existingUser.rows.length === 0) {
      return res.status(404).json({ error: "User not found" });
    }

    await pool.query("DELETE FROM admin_users WHERE id = $1", [id]);

    res.json({
      success: true,
      message: `User ${existingUser.rows[0].username} deleted successfully`,
    });
  } catch (err) {
    console.error("Error deleting admin user:", err);
    res.status(500).json({ error: err.message });
  }
});

module.exports = router;
