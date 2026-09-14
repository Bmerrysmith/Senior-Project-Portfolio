const express = require("express");
const cors = require("cors");
const pool = require("./db");
const bcrypt = require("bcryptjs");
const jwt = require("jsonwebtoken");
const { upload, processUpload, previewUpload, getSupportedTables } = require("./file-upload");
require("dotenv").config();

const app = express();
const PORT = process.env.PORT || 5000;
const JWT_SECRET = process.env.JWT_SECRET || "switch4good-secret-key-2026";

// Middleware
app.use(cors());
app.use(express.json());

// =============================================
// AUTHENTICATION
// =============================================

// Security constants
const MAX_LOGIN_ATTEMPTS = 5;
const LOCKOUT_DURATION_MINUTES = 15;

// Login endpoint - now uses database
app.post("/api/login", async (req, res) => {
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
        error: `Account is locked. Try again in ${minutesLeft} minutes.` 
      });
    }

    // Verify password
    const validPassword = await bcrypt.compare(password, user.password_hash);
    
    if (!validPassword) {
      // Increment failed login attempts
      const newAttempts = (user.failed_login_attempts || 0) + 1;
      
      if (newAttempts >= MAX_LOGIN_ATTEMPTS) {
        // Lock the account
        const lockUntil = new Date(Date.now() + LOCKOUT_DURATION_MINUTES * 60000);
        await pool.query(
          "UPDATE admin_users SET failed_login_attempts = $1, locked_until = $2 WHERE id = $3",
          [newAttempts, lockUntil, user.id]
        );
        return res.status(401).json({ 
          error: `Too many failed attempts. Account locked for ${LOCKOUT_DURATION_MINUTES} minutes.` 
        });
      } else {
        await pool.query(
          "UPDATE admin_users SET failed_login_attempts = $1 WHERE id = $2",
          [newAttempts, user.id]
        );
        return res.status(401).json({ error: "Invalid username or password" });
      }
    }

    // Successful login - reset failed attempts and update last login
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
      { expiresIn: "24h" },
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

// Verify token endpoint
app.get("/api/verify", (req, res) => {
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

// Auth middleware (optional - for protected routes)
const authMiddleware = (req, res, next) => {
  const token = req.headers.authorization?.split(" ")[1];

  if (!token) {
    return res.status(401).json({ error: "Authentication required" });
  }

  try {
    const decoded = jwt.verify(token, JWT_SECRET);
    req.user = decoded;
    next();
  } catch (err) {
    res.status(401).json({ error: "Invalid token" });
  }
};

// Admin-only middleware
const adminMiddleware = (req, res, next) => {
  if (req.user.role !== 'admin') {
    return res.status(403).json({ error: "Admin access required" });
  }
  next();
};

// =============================================
// ADMIN USER MANAGEMENT
// =============================================

// Get all admin users (admin only)
app.get("/api/admin/users", authMiddleware, adminMiddleware, async (req, res) => {
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

// Get single admin user (admin only)
app.get("/api/admin/users/:id", authMiddleware, adminMiddleware, async (req, res) => {
  try {
    const { id } = req.params;
    const result = await pool.query(`
      SELECT id, username, email, name, role, is_active, 
             failed_login_attempts, locked_until, last_login,
             password_changed_at, created_at, updated_at
      FROM admin_users 
      WHERE id = $1
    `, [id]);
    
    if (result.rows.length === 0) {
      return res.status(404).json({ error: "User not found" });
    }
    res.json(result.rows[0]);
  } catch (err) {
    console.error("Error fetching admin user:", err);
    res.status(500).json({ error: err.message });
  }
});

// Create new admin user (admin only)
app.post("/api/admin/users", authMiddleware, adminMiddleware, async (req, res) => {
  try {
    const { username, password, email, name, role } = req.body;

    // Validation
    if (!username || !password || !name) {
      return res.status(400).json({ error: "Username, password, and name are required" });
    }

    if (password.length < 8) {
      return res.status(400).json({ error: "Password must be at least 8 characters" });
    }

    // Check for valid role
    const validRoles = ['admin', 'staff', 'viewer'];
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

    // Check if email already exists (if provided)
    if (email) {
      const existingEmail = await pool.query(
        "SELECT id FROM admin_users WHERE email = $1",
        [email.toLowerCase()]
      );
      if (existingEmail.rows.length > 0) {
        return res.status(400).json({ error: "Email already exists" });
      }
    }

    // Hash password
    const passwordHash = await bcrypt.hash(password, 12);

    // Create user
    const result = await pool.query(`
      INSERT INTO admin_users (username, password_hash, email, name, role)
      VALUES ($1, $2, $3, $4, $5)
      RETURNING id, username, email, name, role, is_active, created_at
    `, [
      username.toLowerCase(),
      passwordHash,
      email ? email.toLowerCase() : null,
      name,
      role || 'viewer'
    ]);

    res.status(201).json({
      success: true,
      message: "User created successfully",
      user: result.rows[0]
    });
  } catch (err) {
    console.error("Error creating admin user:", err);
    res.status(500).json({ error: err.message });
  }
});

// Update admin user (admin only)
app.put("/api/admin/users/:id", authMiddleware, adminMiddleware, async (req, res) => {
  try {
    const { id } = req.params;
    const { email, name, role, is_active } = req.body;

    // Check if user exists
    const existingUser = await pool.query(
      "SELECT * FROM admin_users WHERE id = $1",
      [id]
    );
    if (existingUser.rows.length === 0) {
      return res.status(404).json({ error: "User not found" });
    }

    // Prevent deactivating own account
    if (req.user.id === parseInt(id) && is_active === false) {
      return res.status(400).json({ error: "Cannot deactivate your own account" });
    }

    // Check for valid role
    const validRoles = ['admin', 'staff', 'viewer'];
    if (role && !validRoles.includes(role)) {
      return res.status(400).json({ error: "Invalid role. Must be admin, staff, or viewer" });
    }

    // Check if email already exists (if changed)
    if (email && email.toLowerCase() !== existingUser.rows[0].email) {
      const existingEmail = await pool.query(
        "SELECT id FROM admin_users WHERE email = $1 AND id != $2",
        [email.toLowerCase(), id]
      );
      if (existingEmail.rows.length > 0) {
        return res.status(400).json({ error: "Email already in use" });
      }
    }

    // Update user
    const result = await pool.query(`
      UPDATE admin_users 
      SET email = COALESCE($1, email),
          name = COALESCE($2, name),
          role = COALESCE($3, role),
          is_active = COALESCE($4, is_active),
          updated_at = CURRENT_TIMESTAMP
      WHERE id = $5
      RETURNING id, username, email, name, role, is_active, updated_at
    `, [
      email ? email.toLowerCase() : null,
      name,
      role,
      is_active,
      id
    ]);

    res.json({
      success: true,
      message: "User updated successfully",
      user: result.rows[0]
    });
  } catch (err) {
    console.error("Error updating admin user:", err);
    res.status(500).json({ error: err.message });
  }
});

// Change password (admin can change any, users can change own)
app.patch("/api/admin/users/:id/password", authMiddleware, async (req, res) => {
  try {
    const { id } = req.params;
    const { currentPassword, newPassword } = req.body;

    // Check if user is changing their own password or is admin
    const isOwnAccount = req.user.id === parseInt(id);
    const isAdmin = req.user.role === 'admin';

    if (!isOwnAccount && !isAdmin) {
      return res.status(403).json({ error: "Not authorized to change this password" });
    }

    // Validate new password
    if (!newPassword || newPassword.length < 8) {
      return res.status(400).json({ error: "New password must be at least 8 characters" });
    }

    // Get user
    const userResult = await pool.query(
      "SELECT * FROM admin_users WHERE id = $1",
      [id]
    );
    if (userResult.rows.length === 0) {
      return res.status(404).json({ error: "User not found" });
    }

    const user = userResult.rows[0];

    // If changing own password, verify current password
    if (isOwnAccount && !isAdmin) {
      if (!currentPassword) {
        return res.status(400).json({ error: "Current password is required" });
      }
      const validPassword = await bcrypt.compare(currentPassword, user.password_hash);
      if (!validPassword) {
        return res.status(401).json({ error: "Current password is incorrect" });
      }
    }

    // Hash new password
    const passwordHash = await bcrypt.hash(newPassword, 12);

    // Update password
    await pool.query(`
      UPDATE admin_users 
      SET password_hash = $1, 
          password_changed_at = CURRENT_TIMESTAMP,
          updated_at = CURRENT_TIMESTAMP
      WHERE id = $2
    `, [passwordHash, id]);

    res.json({
      success: true,
      message: "Password changed successfully"
    });
  } catch (err) {
    console.error("Error changing password:", err);
    res.status(500).json({ error: err.message });
  }
});

// Unlock user account (admin only)
app.patch("/api/admin/users/:id/unlock", authMiddleware, adminMiddleware, async (req, res) => {
  try {
    const { id } = req.params;

    const result = await pool.query(`
      UPDATE admin_users 
      SET failed_login_attempts = 0, 
          locked_until = NULL,
          updated_at = CURRENT_TIMESTAMP
      WHERE id = $1
      RETURNING id, username, name
    `, [id]);

    if (result.rows.length === 0) {
      return res.status(404).json({ error: "User not found" });
    }

    res.json({
      success: true,
      message: `Account ${result.rows[0].username} has been unlocked`
    });
  } catch (err) {
    console.error("Error unlocking user:", err);
    res.status(500).json({ error: err.message });
  }
});

// Delete admin user (admin only)
app.delete("/api/admin/users/:id", authMiddleware, adminMiddleware, async (req, res) => {
  try {
    const { id } = req.params;

    // Prevent deleting own account
    if (req.user.id === parseInt(id)) {
      return res.status(400).json({ error: "Cannot delete your own account" });
    }

    // Check if user exists
    const existingUser = await pool.query(
      "SELECT username FROM admin_users WHERE id = $1",
      [id]
    );
    if (existingUser.rows.length === 0) {
      return res.status(404).json({ error: "User not found" });
    }

    // Delete user
    await pool.query("DELETE FROM admin_users WHERE id = $1", [id]);

    res.json({
      success: true,
      message: `User ${existingUser.rows[0].username} deleted successfully`
    });
  } catch (err) {
    console.error("Error deleting admin user:", err);
    res.status(500).json({ error: err.message });
  }
});

// Test route
app.get("/", (req, res) => {
  res.json({ message: "Switch4Good API is running!" });
});

// Test database connection
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

// Get list of all tables
app.get("/api/tables", async (req, res) => {
  try {
    const result = await pool.query(`
      SELECT table_name 
      FROM information_schema.tables 
      WHERE table_schema = 'public' 
      ORDER BY table_name
    `);
    res.json(result.rows.map((row) => row.table_name));
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// =============================================
// SCHOOLS (Protected Routes)
// =============================================
app.get("/api/schools", authMiddleware, async (req, res) => {
  try {
    const result = await pool.query(
      "SELECT * FROM schools ORDER BY school_name",
    );
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.post("/api/schools", authMiddleware, async (req, res) => {
  try {
    const { school_name } = req.body;
    const result = await pool.query(
      `INSERT INTO schools (school_name) VALUES ($1) RETURNING *`,
      [school_name]
    );
    res.status(201).json(result.rows[0]);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.put("/api/schools/:id", authMiddleware, async (req, res) => {
  try {
    if (req.user.role === 'viewer') return res.status(403).json({ error: "Viewers cannot modify data" });
    const { id } = req.params;
    const { school_name } = req.body;
    const result = await pool.query(
      `UPDATE schools SET school_name = COALESCE($1, school_name) WHERE school_id = $2 RETURNING *`,
      [school_name, id]
    );
    res.json(result.rows[0]);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.delete("/api/schools/:id", authMiddleware, async (req, res) => {
  try {
    const { id } = req.params;
    await pool.query("DELETE FROM schools WHERE school_id = $1", [id]);
    res.json({ message: "Deleted successfully" });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// =============================================
// SEMESTERS
// =============================================
app.get("/api/semesters", async (req, res) => {
  try {
    const result = await pool.query(
      "SELECT * FROM semesters ORDER BY year DESC, season",
    );
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// =============================================
// STAFF CONTACTS (Protected Routes)
// =============================================
app.get("/api/staff", authMiddleware, async (req, res) => {
  try {
    const result = await pool.query(
      "SELECT * FROM staff_contacts ORDER BY full_name",
    );
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.post("/api/staff", authMiddleware, async (req, res) => {
  try {
    const { full_name, email, role_title, organization } = req.body;
    const result = await pool.query(
      `INSERT INTO staff_contacts (full_name, email, role_title, organization)
       VALUES ($1, $2, $3, $4) RETURNING *`,
      [full_name, email, role_title, organization],
    );
    res.status(201).json(result.rows[0]);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// =============================================
// PROGRAMS (Protected Routes - with school info)
// =============================================
app.get("/api/programs", authMiddleware, async (req, res) => {
  try {
    const result = await pool.query(`
      SELECT 
        p.program_id as id,
        p.program_name as program,
        s.school_name as school,
        p.website,
        p.program_type,
        p.needs_formalization,
        p.notes
      FROM programs p
      LEFT JOIN schools s ON p.school_id = s.school_id
      ORDER BY p.program_name
    `);
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.post("/api/programs", authMiddleware, async (req, res) => {
  try {
    if (req.user.role === 'viewer') return res.status(403).json({ error: "Viewers cannot add data" });
    const {
      program_name,
      school_id,
      website,
      program_type,
      needs_formalization,
      notes,
    } = req.body;
    const result = await pool.query(
      `INSERT INTO programs (program_name, school_id, website, program_type, needs_formalization, notes)
       VALUES ($1, $2, $3, $4, $5, $6) RETURNING *`,
      [
        program_name,
        school_id,
        website,
        program_type,
        needs_formalization || false,
        notes,
      ],
    );
    res.status(201).json(result.rows[0]);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.put("/api/programs/:id", authMiddleware, async (req, res) => {
  try {
    if (req.user.role === 'viewer') return res.status(403).json({ error: "Viewers cannot modify data" });
    const { id } = req.params;
    const {
      program_name,
      school_id,
      website,
      program_type,
      needs_formalization,
      notes,
    } = req.body;
    const result = await pool.query(
      `UPDATE programs SET
       program_name = COALESCE($1, program_name),
       school_id = COALESCE($2, school_id),
       website = COALESCE($3, website),
       program_type = COALESCE($4, program_type),
       needs_formalization = COALESCE($5, needs_formalization),
       notes = COALESCE($6, notes)
       WHERE program_id = $7
       RETURNING *`,
      [
        program_name,
        school_id,
        website,
        program_type,
        needs_formalization,
        notes,
        id,
      ],
    );
    res.json(result.rows[0]);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.delete("/api/programs/:id", authMiddleware, async (req, res) => {
  try {
    if (req.user.role === 'viewer') return res.status(403).json({ error: "Viewers cannot delete data" });
    const { id } = req.params;
    await pool.query("DELETE FROM programs WHERE program_id = $1", [id]);
    res.json({ message: "Deleted successfully" });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// =============================================
// PROGRAM SEMESTER ACTIVITY (Protected - Program Directory view)
// =============================================
app.get("/api/program-directory", authMiddleware, async (req, res) => {
  try {
    const result = await pool.query(`
      SELECT 
        psa.activity_id as id,
        p.program_name as program,
        p.website,
        p.program_type,
        sch.school_name as school,
        sem.season || ' ' || sem.year as semester,
        psa.is_active,
        psa.most_recent_contact_date,
        sc.full_name as sg4_staff_contact,
        psa.partner_email,
        psa.notes,
        p.needs_formalization
      FROM program_semester_activity psa
      JOIN programs p ON psa.program_id = p.program_id
      LEFT JOIN schools sch ON p.school_id = sch.school_id
      LEFT JOIN semesters sem ON psa.semester_id = sem.semester_id
      LEFT JOIN staff_contacts sc ON psa.sg4_staff_contact_id = sc.staff_id
      ORDER BY sem.year DESC, sem.season, p.program_name
    `);
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// =============================================
// STUDENTS (Protected Routes)
// =============================================
app.get("/api/students", authMiddleware, async (req, res) => {
  try {
    const result = await pool.query(`
      SELECT 
        student_id as id,
        full_name as name,
        email as email_address,
        pronouns,
        tshirt_size,
        year_in_school,
        areas_of_interest
      FROM students
      ORDER BY student_id DESC
    `);
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.post("/api/students", authMiddleware, async (req, res) => {
  try {
    if (req.user.role === 'viewer') return res.status(403).json({ error: "Viewers cannot add data" });
    const {
      full_name,
      email,
      pronouns,
      tshirt_size,
      year_in_school,
      areas_of_interest,
    } = req.body;
    const result = await pool.query(
      `INSERT INTO students (full_name, email, pronouns, tshirt_size, year_in_school, areas_of_interest)
       VALUES ($1, $2, $3, $4, $5, $6) RETURNING *`,
      [
        full_name,
        email,
        pronouns,
        tshirt_size,
        year_in_school,
        areas_of_interest,
      ],
    );
    res.status(201).json(result.rows[0]);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.put("/api/students/:id", authMiddleware, async (req, res) => {
  try {
    if (req.user.role === 'viewer') return res.status(403).json({ error: "Viewers cannot modify data" });
    const { id } = req.params;
    const {
      full_name,
      email,
      pronouns,
      tshirt_size,
      year_in_school,
      areas_of_interest,
    } = req.body;
    const result = await pool.query(
      `UPDATE students SET
       full_name = COALESCE($1, full_name),
       email = COALESCE($2, email),
       pronouns = COALESCE($3, pronouns),
       tshirt_size = COALESCE($4, tshirt_size),
       year_in_school = COALESCE($5, year_in_school),
       areas_of_interest = COALESCE($6, areas_of_interest)
       WHERE student_id = $7
       RETURNING *`,
      [
        full_name,
        email,
        pronouns,
        tshirt_size,
        year_in_school,
        areas_of_interest,
        id,
      ],
    );
    res.json(result.rows[0]);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.delete("/api/students/:id", authMiddleware, async (req, res) => {
  try {
    if (req.user.role === 'viewer') return res.status(403).json({ error: "Viewers cannot delete data" });
    const { id } = req.params;
    await pool.query("DELETE FROM students WHERE student_id = $1", [id]);
    res.json({ message: "Deleted successfully" });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// =============================================
// STUDENT PARTICIPATION (Protected - Student Tracker view with full details)
// =============================================
app.get("/api/student-tracker", authMiddleware, async (req, res) => {
  try {
    const result = await pool.query(`
      SELECT 
        sp.participation_id as id,
        st.full_name as name,
        st.email as email_address,
        st.pronouns,
        st.tshirt_size,
        st.year_in_school,
        st.areas_of_interest,
        p.program_name as program,
        sch.school_name as school,
        sc.full_name as sg4_staff,
        sem.season || ' ' || sem.year as semester,
        sp.project_name as project,
        sp.project_start_date,
        sp.project_end_date,
        sp.meeting_cadence,
        sp.conflicting_datetimes,
        sp.success_metric,
        COALESCE(
          (SELECT SUM(hours) FROM hours_log WHERE participation_id = sp.participation_id), 0
        ) as total_hours
      FROM student_participation sp
      JOIN students st ON sp.student_id = st.student_id
      JOIN programs p ON sp.program_id = p.program_id
      LEFT JOIN schools sch ON p.school_id = sch.school_id
      LEFT JOIN semesters sem ON sp.semester_id = sem.semester_id
      LEFT JOIN staff_contacts sc ON sp.sg4_staff_id = sc.staff_id
      ORDER BY sp.participation_id DESC
    `);
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// =============================================
// HOURS LOG (Protected Routes)
// =============================================
app.get("/api/hours/:participation_id", authMiddleware, async (req, res) => {
  try {
    const { participation_id } = req.params;
    const result = await pool.query(
      "SELECT * FROM hours_log WHERE participation_id = $1 ORDER BY period_number",
      [participation_id],
    );
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.post("/api/hours", authMiddleware, async (req, res) => {
  try {
    if (req.user.role === 'viewer') return res.status(403).json({ error: "Viewers cannot add data" });
    const { participation_id, period_number, hours, notes } = req.body;
    const result = await pool.query(
      `INSERT INTO hours_log (participation_id, period_number, hours, notes)
       VALUES ($1, $2, $3, $4) RETURNING *`,
      [participation_id, period_number, hours, notes],
    );
    res.status(201).json(result.rows[0]);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// =============================================
// STUDENT CHECKLIST (Protected Routes)
// =============================================
app.get("/api/checklist/:participation_id", authMiddleware, async (req, res) => {
  try {
    const { participation_id } = req.params;
    const result = await pool.query(
      "SELECT * FROM student_checklist_item WHERE participation_id = $1 ORDER BY item_type",
      [participation_id],
    );
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// =============================================
// CAN METRICS (Protected Routes)
// =============================================
app.get("/api/can-metrics", authMiddleware, async (req, res) => {
  try {
    const result = await pool.query(`
      SELECT 
        metric_id as id,
        metric_date as date,
        is_ongoing,
        impression,
        touchpoints,
        engagements,
        conversions,
        notes
      FROM can_metrics
      ORDER BY metric_date DESC NULLS LAST
    `);
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.post("/api/can-metrics", authMiddleware, async (req, res) => {
  try {
    if (req.user.role === 'viewer') return res.status(403).json({ error: "Viewers cannot add data" });
    const {
      metric_date,
      is_ongoing,
      impression,
      touchpoints,
      engagements,
      conversions,
      notes,
    } = req.body;
    const result = await pool.query(
      `INSERT INTO can_metrics (metric_date, is_ongoing, impression, touchpoints, engagements, conversions, notes)
       VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING *`,
      [
        metric_date || null,
        is_ongoing || false,
        impression,
        touchpoints || 0,
        engagements || 0,
        conversions || 0,
        notes,
      ],
    );
    res.status(201).json(result.rows[0]);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.put("/api/can-metrics/:id", authMiddleware, async (req, res) => {
  try {
    if (req.user.role === 'viewer') return res.status(403).json({ error: "Viewers cannot modify data" });
    const { id } = req.params;
    const {
      metric_date,
      is_ongoing,
      impression,
      touchpoints,
      engagements,
      conversions,
      notes,
    } = req.body;
    const result = await pool.query(
      `UPDATE can_metrics SET
       metric_date = COALESCE($1, metric_date),
       is_ongoing = COALESCE($2, is_ongoing),
       impression = COALESCE($3, impression),
       touchpoints = COALESCE($4, touchpoints),
       engagements = COALESCE($5, engagements),
       conversions = COALESCE($6, conversions),
       notes = COALESCE($7, notes)
       WHERE metric_id = $8
       RETURNING *`,
      [
        metric_date,
        is_ongoing,
        impression,
        touchpoints,
        engagements,
        conversions,
        notes,
        id,
      ],
    );
    res.json(result.rows[0]);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.delete("/api/can-metrics/:id", authMiddleware, async (req, res) => {
  try {
    if (req.user.role === 'viewer') return res.status(403).json({ error: "Viewers cannot delete data" });
    const { id } = req.params;
    await pool.query("DELETE FROM can_metrics WHERE metric_id = $1", [id]);
    res.json({ message: "Deleted successfully" });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// =============================================
// Dashboard Stats (Protected Route)
// =============================================
app.get("/api/dashboard", authMiddleware, async (req, res) => {
  try {
    const stats = {};

    const queries = [
      { key: "schools", query: "SELECT COUNT(*) as count FROM schools" },
      { key: "programs", query: "SELECT COUNT(*) as count FROM programs" },
      { key: "students", query: "SELECT COUNT(*) as count FROM students" },
      { key: "staff", query: "SELECT COUNT(*) as count FROM staff_contacts" },
      { key: "canMetrics", query: "SELECT COUNT(*) as count FROM can_metrics" },
      {
        key: "participations",
        query: "SELECT COUNT(*) as count FROM student_participation",
      },
    ];

    for (const q of queries) {
      try {
        const result = await pool.query(q.query);
        stats[q.key] = parseInt(result.rows[0].count);
      } catch (e) {
        stats[q.key] = 0;
      }
    }

    res.json(stats);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// =============================================
// STAGING TABLES - Protected Routes (All original spreadsheet columns)
// =============================================

// SS1 Program/Course Tab - ALL COLUMNS
app.get("/api/staging/program-course", authMiddleware, async (req, res) => {
  try {
    const result = await pool.query(`
      SELECT 
        stg_id as id,
        school,
        sg4_staff,
        program,
        faculty_staff,
        ty_note,
        students_participating,
        total_classes_in_session,
        status,
        notes,
        next_steps,
        course_details,
        source_file,
        imported_at
      FROM stg_ss1_program_course_tab
      ORDER BY stg_id ASC
    `);
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.post("/api/staging/program-course", authMiddleware, async (req, res) => {
  try {
    if (req.user.role === 'viewer') return res.status(403).json({ error: "Viewers cannot add data" });
    const { school, sg4_staff, program, faculty_staff, ty_note, students_participating, total_classes_in_session, status, notes, next_steps, course_details } = req.body;
    const result = await pool.query(
      `INSERT INTO stg_ss1_program_course_tab 
       (school, sg4_staff, program, faculty_staff, ty_note, students_participating, total_classes_in_session, status, notes, next_steps, course_details, imported_at)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, NOW())
       RETURNING *`,
      [school, sg4_staff, program, faculty_staff, ty_note, students_participating, total_classes_in_session, status, notes, next_steps, course_details]
    );
    res.status(201).json(result.rows[0]);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.put("/api/staging/program-course/:id", authMiddleware, async (req, res) => {
  try {
    if (req.user.role === 'viewer') return res.status(403).json({ error: "Viewers cannot modify data" });
    const { id } = req.params;
    const fields = req.body;
    const updates = [];
    const values = [];
    let paramCount = 1;
    
    const allowedFields = ['school', 'sg4_staff', 'program', 'faculty_staff', 'ty_note', 'students_participating', 'total_classes_in_session', 'status', 'notes', 'next_steps', 'course_details'];
    
    for (const field of allowedFields) {
      if (fields[field] !== undefined) {
        updates.push(`${field} = $${paramCount}`);
        values.push(fields[field]);
        paramCount++;
      }
    }
    
    if (updates.length === 0) return res.status(400).json({ error: 'No fields to update' });
    
    values.push(id);
    const result = await pool.query(
      `UPDATE stg_ss1_program_course_tab SET ${updates.join(', ')} WHERE stg_id = $${paramCount} RETURNING *`,
      values
    );
    res.json(result.rows[0]);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.delete("/api/staging/program-course/:id", authMiddleware, async (req, res) => {
  try {
    if (req.user.role === 'viewer') return res.status(403).json({ error: "Viewers cannot delete data" });
    await pool.query('DELETE FROM stg_ss1_program_course_tab WHERE stg_id = $1', [req.params.id]);
    res.json({ message: 'Deleted successfully' });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// SS1 Student Tracker - ALL COLUMNS (Protected)
app.get("/api/staging/student-tracker", authMiddleware, async (req, res) => {
  try {
    const result = await pool.query(`
      SELECT 
        stg_id as id,
        name,
        sg4_staff,
        pronouns,
        tshirt_size,
        school_program,
        email_address,
        year_in_school,
        areas_of_interest,
        projects,
        project_duration,
        meeting_cadence,
        conflicting_dates_times,
        success_metric,
        date_intro_email_sent,
        attended_orientation,
        read_community_guidelines,
        signed_media_release,
        sent_headshot,
        completed_deliverables_raw as completed_deliverables,
        survey_checkins_raw as survey_checkins,
        meeting_checkins_raw as meeting_checkins,
        hours_worked_raw as hours_worked,
        total_hours_per_student as total_hours,
        notes_raw as notes,
        source_file,
        imported_at
      FROM stg_ss1_student_tracker
      ORDER BY stg_id ASC
    `);
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.post("/api/staging/student-tracker", authMiddleware, async (req, res) => {
  try {
    if (req.user.role === 'viewer') return res.status(403).json({ error: "Viewers cannot add data" });
    const { name, sg4_staff, pronouns, tshirt_size, school_program, email_address, year_in_school, areas_of_interest, projects, project_duration, meeting_cadence, conflicting_dates_times, success_metric, date_intro_email_sent, attended_orientation, read_community_guidelines, signed_media_release, sent_headshot, completed_deliverables, survey_checkins, meeting_checkins, hours_worked, total_hours, notes } = req.body;
    const result = await pool.query(
      `INSERT INTO stg_ss1_student_tracker 
       (name, sg4_staff, pronouns, tshirt_size, school_program, email_address, year_in_school, areas_of_interest, projects, project_duration, meeting_cadence, conflicting_dates_times, success_metric, date_intro_email_sent, attended_orientation, read_community_guidelines, signed_media_release, sent_headshot, completed_deliverables_raw, survey_checkins_raw, meeting_checkins_raw, hours_worked_raw, total_hours_per_student, notes_raw, imported_at)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, NOW())
       RETURNING *`,
      [name, sg4_staff, pronouns, tshirt_size, school_program, email_address, year_in_school, areas_of_interest, projects, project_duration, meeting_cadence, conflicting_dates_times, success_metric, date_intro_email_sent, attended_orientation, read_community_guidelines, signed_media_release, sent_headshot, completed_deliverables, survey_checkins, meeting_checkins, hours_worked, total_hours, notes]
    );
    res.status(201).json(result.rows[0]);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.put("/api/staging/student-tracker/:id", authMiddleware, async (req, res) => {
  try {
    if (req.user.role === 'viewer') return res.status(403).json({ error: "Viewers cannot modify data" });
    const { id } = req.params;
    const fields = req.body;
    const fieldMapping = {
      name: 'name', sg4_staff: 'sg4_staff', pronouns: 'pronouns', tshirt_size: 'tshirt_size',
      school_program: 'school_program', email_address: 'email_address', year_in_school: 'year_in_school',
      areas_of_interest: 'areas_of_interest', projects: 'projects', project_duration: 'project_duration',
      meeting_cadence: 'meeting_cadence', conflicting_dates_times: 'conflicting_dates_times',
      success_metric: 'success_metric', date_intro_email_sent: 'date_intro_email_sent',
      attended_orientation: 'attended_orientation', read_community_guidelines: 'read_community_guidelines',
      signed_media_release: 'signed_media_release', sent_headshot: 'sent_headshot',
      completed_deliverables: 'completed_deliverables_raw', survey_checkins: 'survey_checkins_raw',
      meeting_checkins: 'meeting_checkins_raw', hours_worked: 'hours_worked_raw',
      total_hours: 'total_hours_per_student', notes: 'notes_raw'
    };
    
    const updates = [];
    const values = [];
    let paramCount = 1;
    
    for (const [key, dbField] of Object.entries(fieldMapping)) {
      if (fields[key] !== undefined) {
        updates.push(`${dbField} = $${paramCount}`);
        values.push(fields[key]);
        paramCount++;
      }
    }
    
    if (updates.length === 0) return res.status(400).json({ error: 'No fields to update' });
    
    values.push(id);
    const result = await pool.query(
      `UPDATE stg_ss1_student_tracker SET ${updates.join(', ')} WHERE stg_id = $${paramCount} RETURNING *`,
      values
    );
    res.json(result.rows[0]);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.delete("/api/staging/student-tracker/:id", authMiddleware, async (req, res) => {
  try {
    if (req.user.role === 'viewer') return res.status(403).json({ error: "Viewers cannot delete data" });
    await pool.query('DELETE FROM stg_ss1_student_tracker WHERE stg_id = $1', [req.params.id]);
    res.json({ message: 'Deleted successfully' });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// SS2 CAN Metrics - ALL COLUMNS (Protected)
app.get("/api/staging/can-metrics", authMiddleware, async (req, res) => {
  try {
    const result = await pool.query(`
      SELECT 
        stg_id as id,
        date_raw as date,
        impression,
        touchpoints_raw as touchpoints,
        engagements_raw as engagements,
        conversions_raw as conversions,
        source_file,
        imported_at
      FROM stg_ss2_can_metrics
      ORDER BY stg_id ASC
    `);
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.post("/api/staging/can-metrics", authMiddleware, async (req, res) => {
  try {
    if (req.user.role === 'viewer') return res.status(403).json({ error: "Viewers cannot add data" });
    const { date, impression, touchpoints, engagements, conversions } = req.body;
    const result = await pool.query(
      `INSERT INTO stg_ss2_can_metrics (date_raw, impression, touchpoints_raw, engagements_raw, conversions_raw, imported_at)
       VALUES ($1, $2, $3, $4, $5, NOW()) RETURNING *`,
      [date, impression, touchpoints, engagements, conversions]
    );
    res.status(201).json(result.rows[0]);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.put("/api/staging/can-metrics/:id", authMiddleware, async (req, res) => {
  try {
    if (req.user.role === 'viewer') return res.status(403).json({ error: "Viewers cannot modify data" });
    const { id } = req.params;
    const { date, impression, touchpoints, engagements, conversions } = req.body;
    const fieldMapping = { date: 'date_raw', impression: 'impression', touchpoints: 'touchpoints_raw', engagements: 'engagements_raw', conversions: 'conversions_raw' };
    
    const updates = [];
    const values = [];
    let paramCount = 1;
    
    for (const [key, dbField] of Object.entries(fieldMapping)) {
      if (req.body[key] !== undefined) {
        updates.push(`${dbField} = $${paramCount}`);
        values.push(req.body[key]);
        paramCount++;
      }
    }
    
    if (updates.length === 0) return res.status(400).json({ error: 'No fields to update' });
    
    values.push(id);
    const result = await pool.query(
      `UPDATE stg_ss2_can_metrics SET ${updates.join(', ')} WHERE stg_id = $${paramCount} RETURNING *`,
      values
    );
    res.json(result.rows[0]);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.delete("/api/staging/can-metrics/:id", authMiddleware, async (req, res) => {
  try {
    if (req.user.role === 'viewer') return res.status(403).json({ error: "Viewers cannot delete data" });
    await pool.query('DELETE FROM stg_ss2_can_metrics WHERE stg_id = $1', [req.params.id]);
    res.json({ message: 'Deleted successfully' });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// SS3 Program Directory - ALL COLUMNS (Protected)
app.get("/api/staging/program-directory", authMiddleware, async (req, res) => {
  try {
    const result = await pool.query(`
      SELECT 
        stg_id as id,
        program,
        website,
        program_type,
        school,
        season,
        semesters_active,
        needs_formalization_raw as needs_formalization,
        most_recent_contact_raw as most_recent_contact,
        sg4_staff_contact,
        staff,
        email_address,
        notes,
        source_file,
        imported_at
      FROM stg_ss3_program_directory
      ORDER BY stg_id ASC
    `);
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.post("/api/staging/program-directory", authMiddleware, async (req, res) => {
  try {
    if (req.user.role === 'viewer') return res.status(403).json({ error: "Viewers cannot add data" });
    const { program, website, program_type, school, season, semesters_active, needs_formalization, most_recent_contact, sg4_staff_contact, staff, email_address, notes } = req.body;
    const result = await pool.query(
      `INSERT INTO stg_ss3_program_directory 
       (program, website, program_type, school, season, semesters_active, needs_formalization_raw, most_recent_contact_raw, sg4_staff_contact, staff, email_address, notes, imported_at)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, NOW()) RETURNING *`,
      [program, website, program_type, school, season, semesters_active, needs_formalization, most_recent_contact, sg4_staff_contact, staff, email_address, notes]
    );
    res.status(201).json(result.rows[0]);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.put("/api/staging/program-directory/:id", authMiddleware, async (req, res) => {
  try {
    if (req.user.role === 'viewer') return res.status(403).json({ error: "Viewers cannot modify data" });
    const { id } = req.params;
    const fieldMapping = {
      program: 'program', website: 'website', program_type: 'program_type', school: 'school',
      season: 'season', semesters_active: 'semesters_active', needs_formalization: 'needs_formalization_raw',
      most_recent_contact: 'most_recent_contact_raw', sg4_staff_contact: 'sg4_staff_contact',
      staff: 'staff', email_address: 'email_address', notes: 'notes'
    };
    
    const updates = [];
    const values = [];
    let paramCount = 1;
    
    for (const [key, dbField] of Object.entries(fieldMapping)) {
      if (req.body[key] !== undefined) {
        updates.push(`${dbField} = $${paramCount}`);
        values.push(req.body[key]);
        paramCount++;
      }
    }
    
    if (updates.length === 0) return res.status(400).json({ error: 'No fields to update' });
    
    values.push(id);
    const result = await pool.query(
      `UPDATE stg_ss3_program_directory SET ${updates.join(', ')} WHERE stg_id = $${paramCount} RETURNING *`,
      values
    );
    res.json(result.rows[0]);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.delete("/api/staging/program-directory/:id", authMiddleware, async (req, res) => {
  try {
    if (req.user.role === 'viewer') return res.status(403).json({ error: "Viewers cannot delete data" });
    await pool.query('DELETE FROM stg_ss3_program_directory WHERE stg_id = $1', [req.params.id]);
    res.json({ message: 'Deleted successfully' });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// =============================================
// NEW NORMALIZED SCHEMA APIs (Protected - Dashboard Metrics)
// =============================================

// Get all semesters from new schema
app.get("/api/v2/semesters", authMiddleware, async (req, res) => {
  try {
    const result = await pool.query(`
      SELECT id, name, academic_year, start_date, end_date, is_current
      FROM semester ORDER BY start_date DESC
    `);
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Get universities
app.get("/api/v2/universities", authMiddleware, async (req, res) => {
  try {
    const result = await pool.query(`
      SELECT id, name, abbreviation, city, state, 
             primary_contact_name, primary_contact_email, partnership_start_date
      FROM university ORDER BY name
    `);
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Get programs with university info
app.get("/api/v2/programs", authMiddleware, async (req, res) => {
  try {
    const result = await pool.query(`
      SELECT p.id, p.name, p.program_type, p.department, p.is_active,
             u.name AS university_name, u.abbreviation AS university_abbr,
             s.name AS staff_name
      FROM program p
      JOIN university u ON p.university_id = u.id
      LEFT JOIN s4g_staff s ON p.s4g_staff_id = s.id
      ORDER BY u.name, p.name
    `);
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Get partnerships (program + semester + course)
app.get("/api/v2/partnerships", authMiddleware, async (req, res) => {
  try {
    const { semester_id, status } = req.query;
    let query = `
      SELECT part.id, part.status, part.students_participating, part.total_in_class,
             part.ty_note_sent, part.notes, part.next_steps,
             sem.name AS semester, sem.id AS semester_id, sem.is_current,
             prog.name AS program_name, prog.program_type,
             u.name AS university_name,
             c.course_code, c.course_name,
             staff.name AS staff_name
      FROM partnership part
      JOIN semester sem ON part.semester_id = sem.id
      JOIN program prog ON part.program_id = prog.id
      JOIN university u ON prog.university_id = u.id
      LEFT JOIN course c ON part.course_id = c.id
      LEFT JOIN s4g_staff staff ON prog.s4g_staff_id = staff.id
      WHERE 1=1
    `;
    const params = [];
    if (semester_id) {
      params.push(semester_id);
      query += ` AND sem.id = $${params.length}`;
    }
    if (status) {
      params.push(status);
      query += ` AND part.status = $${params.length}`;
    }
    query += ` ORDER BY sem.start_date DESC, u.name, prog.name`;
    
    const result = await pool.query(query, params);
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Get projects
app.get("/api/v2/projects", authMiddleware, async (req, res) => {
  try {
    const { partnership_id } = req.query;
    let query = `
      SELECT p.id, p.name, p.description, p.start_date, p.end_date,
             p.deliverable_description, pt.name AS project_type,
             part.id AS partnership_id,
             sem.name AS semester,
             prog.name AS program_name,
             u.name AS university_name
      FROM project p
      LEFT JOIN project_type pt ON p.project_type_id = pt.id
      JOIN partnership part ON p.partnership_id = part.id
      JOIN semester sem ON part.semester_id = sem.id
      JOIN program prog ON part.program_id = prog.id
      JOIN university u ON prog.university_id = u.id
      WHERE 1=1
    `;
    const params = [];
    if (partnership_id) {
      params.push(partnership_id);
      query += ` AND part.id = $${params.length}`;
    }
    query += ` ORDER BY p.start_date DESC`;
    
    const result = await pool.query(query, params);
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Get student registrations (anonymized)
app.get("/api/v2/registrations", authMiddleware, async (req, res) => {
  try {
    const result = await pool.query(`SELECT * FROM v_student_registrations_anon`);
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// =============================================
// DASHBOARD METRICS (Protected - from views)
// =============================================

// Active partnerships metric
app.get("/api/v2/metrics/active-partnerships", authMiddleware, async (req, res) => {
  try {
    const result = await pool.query(`SELECT * FROM v_metric_active_partnerships`);
    res.json(result.rows[0] || { active_partnerships: 0, previous_semester_count: 0 });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Students engaged by semester
app.get("/api/v2/metrics/students-engaged", authMiddleware, async (req, res) => {
  try {
    const result = await pool.query(`SELECT * FROM v_metric_students_engaged`);
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Service hours by semester
app.get("/api/v2/metrics/service-hours", authMiddleware, async (req, res) => {
  try {
    const result = await pool.query(`SELECT * FROM v_metric_service_hours`);
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Completion rate
app.get("/api/v2/metrics/completion-rate", authMiddleware, async (req, res) => {
  try {
    const result = await pool.query(`SELECT * FROM v_metric_completion_rate`);
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// University reach
app.get("/api/v2/metrics/university-reach", authMiddleware, async (req, res) => {
  try {
    const result = await pool.query(`SELECT * FROM v_metric_university_reach`);
    res.json(result.rows[0] || { total_universities: 0, states_covered: 0 });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Program types distribution
app.get("/api/v2/metrics/program-types", authMiddleware, async (req, res) => {
  try {
    const result = await pool.query(`SELECT * FROM v_metric_program_types`);
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Course impact (dairy content)
app.get("/api/v2/metrics/course-impact", authMiddleware, async (req, res) => {
  try {
    const result = await pool.query(`SELECT * FROM v_metric_course_impact`);
    res.json(result.rows[0] || { courses_with_dairy_content: 0 });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Outreach funnel
app.get("/api/v2/metrics/outreach-funnel", authMiddleware, async (req, res) => {
  try {
    const result = await pool.query(`SELECT * FROM v_metric_outreach_funnel`);
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Project performance by type
app.get("/api/v2/metrics/project-performance", authMiddleware, async (req, res) => {
  try {
    const result = await pool.query(`SELECT * FROM v_metric_project_performance`);
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Retention metric
app.get("/api/v2/metrics/retention", authMiddleware, async (req, res) => {
  try {
    const result = await pool.query(`SELECT * FROM v_metric_retention`);
    res.json(result.rows[0] || { total_unique_students: 0, returning_students: 0, retention_rate: 0 });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Staff workload
app.get("/api/v2/metrics/staff-workload", authMiddleware, async (req, res) => {
  try {
    const result = await pool.query(`SELECT * FROM v_metric_staff_workload`);
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Milestones tracking
app.get("/api/v2/metrics/milestones", authMiddleware, async (req, res) => {
  try {
    const result = await pool.query(`SELECT * FROM v_metric_milestones`);
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Current semester activity view
app.get("/api/v2/current-activity", authMiddleware, async (req, res) => {
  try {
    const result = await pool.query(`SELECT * FROM v_current_semester_activity`);
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Partnership history (for finding inactive programs)
app.get("/api/v2/partnership-history", authMiddleware, async (req, res) => {
  try {
    const result = await pool.query(`SELECT * FROM v_partnership_history`);
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Hours totals by project
app.get("/api/v2/hours-totals", authMiddleware, async (req, res) => {
  try {
    const result = await pool.query(`SELECT * FROM v_student_hours_totals`);
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Combined dashboard data (all key metrics in one call)
app.get("/api/v2/dashboard", authMiddleware, async (req, res) => {
  try {
    const [
      activePartnerships,
      studentsEngaged,
      serviceHours,
      completionRate,
      universityReach,
      programTypes,
      courseImpact,
      retention,
      milestones
    ] = await Promise.all([
      pool.query(`SELECT * FROM v_metric_active_partnerships`),
      pool.query(`SELECT * FROM v_metric_students_engaged`),
      pool.query(`SELECT * FROM v_metric_service_hours`),
      pool.query(`SELECT * FROM v_metric_completion_rate`),
      pool.query(`SELECT * FROM v_metric_university_reach`),
      pool.query(`SELECT * FROM v_metric_program_types`),
      pool.query(`SELECT * FROM v_metric_course_impact`),
      pool.query(`SELECT * FROM v_metric_retention`),
      pool.query(`SELECT * FROM v_metric_milestones`)
    ]);

    res.json({
      activePartnerships: activePartnerships.rows[0] || {},
      studentsEngaged: studentsEngaged.rows,
      serviceHours: serviceHours.rows,
      completionRate: completionRate.rows,
      universityReach: universityReach.rows[0] || {},
      programTypes: programTypes.rows,
      courseImpact: courseImpact.rows[0] || {},
      retention: retention.rows[0] || {},
      milestones: milestones.rows
    });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// =============================================
// FILE UPLOAD ENDPOINTS
// =============================================

// Get list of supported tables for upload
app.get("/api/upload/tables", authMiddleware, (req, res) => {
  const tables = getSupportedTables();
  res.json(tables);
});

// Preview file before importing (with column detection)
app.post("/api/upload/preview", authMiddleware, upload.single('file'), async (req, res) => {
  try {
    if (!req.file) {
      return res.status(400).json({ error: "No file uploaded" });
    }

    const targetTable = req.body.targetTable || null;
    const preview = await previewUpload(req.file.buffer, req.file.originalname, targetTable);
    
    res.json(preview);
  } catch (err) {
    console.error("Preview error:", err);
    res.status(500).json({ error: err.message });
  }
});

// Import file data to database (admin only)
app.post("/api/upload/import", authMiddleware, adminMiddleware, upload.single('file'), async (req, res) => {
  try {
    if (!req.file) {
      return res.status(400).json({ error: "No file uploaded" });
    }

    const targetTable = req.body.targetTable || null;
    const result = await processUpload(
      req.file.buffer, 
      req.file.originalname, 
      targetTable, 
      req.user.id
    );
    
    // Log the upload activity
    console.log(`File import by ${req.user.username}:`, {
      filename: req.file.originalname,
      imported: result.imported,
      errors: result.errors.length
    });
    
    res.json(result);
  } catch (err) {
    console.error("Import error:", err);
    res.status(500).json({ error: err.message });
  }
});

// Upload with specific table target (admin only)
app.post("/api/upload/:table", authMiddleware, adminMiddleware, upload.single('file'), async (req, res) => {
  try {
    if (!req.file) {
      return res.status(400).json({ error: "No file uploaded" });
    }

    const targetTable = req.params.table;
    const supportedTables = getSupportedTables();
    
    if (!supportedTables[targetTable]) {
      return res.status(400).json({ 
        error: `Unsupported table: ${targetTable}`,
        supportedTables: Object.keys(supportedTables)
      });
    }

    const result = await processUpload(
      req.file.buffer, 
      req.file.originalname, 
      targetTable, 
      req.user.id
    );
    
    res.json(result);
  } catch (err) {
    console.error("Import error:", err);
    res.status(500).json({ error: err.message });
  }
});

// Get upload history/logs (admin only)
app.get("/api/upload/history", authMiddleware, adminMiddleware, async (req, res) => {
  try {
    // This could be expanded to log uploads to a database table
    res.json({
      message: "Upload history feature - logs stored in server console",
      note: "Consider adding an upload_log table for persistent tracking"
    });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Start server
app.listen(PORT, () => {
  console.log(`Server is running on http://localhost:${PORT}`);
});
