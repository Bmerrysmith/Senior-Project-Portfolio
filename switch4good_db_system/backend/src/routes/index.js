const router = require("express").Router();

// Import route modules
const authRoutes = require("./auth.routes");
const adminRoutes = require("./admin.routes");
const schoolsRoutes = require("./schools.routes");
const programsRoutes = require("./programs.routes");
const studentsRoutes = require("./students.routes");
const stagingRoutes = require("./staging.routes");
const metricsRoutes = require("./metrics.routes");
const uploadRoutes = require("./upload.routes");

// Mount routes
router.use("/auth", authRoutes);
router.use("/admin", adminRoutes);
router.use("/schools", schoolsRoutes);
router.use("/programs", programsRoutes);
router.use("/students", studentsRoutes);
router.use("/staging", stagingRoutes);
router.use("/", metricsRoutes); // Mounts can-metrics and v2/* routes
router.use("/upload", uploadRoutes);

// Legacy route aliases (for backward compatibility)
router.use("/login", (req, res, next) => {
  req.url = "/auth/login";
  authRoutes(req, res, next);
});

router.use("/verify", (req, res, next) => {
  req.url = "/auth/verify";
  authRoutes(req, res, next);
});

// Dashboard stats (protected)
const pool = require("../config/database");
const { authenticate } = require("../middleware/auth");

router.get("/dashboard", authenticate, async (req, res) => {
  try {
    const stats = {};
    const queries = [
      { key: "schools", query: "SELECT COUNT(*) as count FROM schools" },
      { key: "programs", query: "SELECT COUNT(*) as count FROM programs" },
      { key: "students", query: "SELECT COUNT(*) as count FROM students" },
      { key: "staff", query: "SELECT COUNT(*) as count FROM staff_contacts" },
      { key: "canMetrics", query: "SELECT COUNT(*) as count FROM can_metrics" },
      { key: "participations", query: "SELECT COUNT(*) as count FROM student_participation" },
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

// Semesters
router.get("/semesters", async (req, res) => {
  try {
    const result = await pool.query("SELECT * FROM semesters ORDER BY year DESC, season");
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Staff contacts
router.get("/staff", authenticate, async (req, res) => {
  try {
    const result = await pool.query("SELECT * FROM staff_contacts ORDER BY full_name");
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

router.post("/staff", authenticate, async (req, res) => {
  try {
    const { full_name, email, role_title, organization } = req.body;
    const result = await pool.query(
      `INSERT INTO staff_contacts (full_name, email, role_title, organization)
       VALUES ($1, $2, $3, $4) RETURNING *`,
      [full_name, email, role_title, organization]
    );
    res.status(201).json(result.rows[0]);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Program directory (legacy route)
router.get("/program-directory", authenticate, async (req, res) => {
  try {
    const result = await pool.query(`
      SELECT 
        (psa.program_id || '-' || psa.semester_id) as id,
        p.program_name as program,
        p.website,
        p.program_type,
        sch.school_name as school,
        sem.season || ' ' || sem.year::text as semester,
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
      ORDER BY sem.year DESC, sem.season, p.program_id
    `);
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Student tracker (legacy route)
router.get("/student-tracker", authenticate, async (req, res) => {
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
        sem.season || ' ' || sem.year::text as semester,
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

// Hours and checklist (legacy routes)
router.get("/hours/:participation_id", authenticate, async (req, res) => {
  try {
    const result = await pool.query(
      "SELECT * FROM hours_log WHERE participation_id = $1 ORDER BY period_number",
      [req.params.participation_id]
    );
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

router.get("/checklist/:participation_id", authenticate, async (req, res) => {
  try {
    const result = await pool.query(
      "SELECT * FROM student_checklist_item WHERE participation_id = $1 ORDER BY item_type",
      [req.params.participation_id]
    );
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Tables list
router.get("/tables", async (req, res) => {
  try {
    const result = await pool.query(`
      SELECT table_name FROM information_schema.tables 
      WHERE table_schema = 'public' ORDER BY table_name
    `);
    res.json(result.rows.map((row) => row.table_name));
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

module.exports = router;
