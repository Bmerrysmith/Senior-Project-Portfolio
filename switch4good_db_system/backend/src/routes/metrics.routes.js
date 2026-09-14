const router = require("express").Router();
const pool = require("../config/database");
const { authenticate, requireStaff } = require("../middleware/auth");

router.use(authenticate);

// =============================================
// CAN METRICS (Normalized)
// =============================================
router.get("/can-metrics", async (req, res) => {
  try {
    const result = await pool.query(`
      SELECT metric_id as id, metric_date as date, is_ongoing, impression,
             touchpoints, engagements, conversions, notes
      FROM can_metrics ORDER BY metric_id
    `);
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

router.post("/can-metrics", requireStaff, async (req, res) => {
  try {
    const { metric_date, is_ongoing, impression, touchpoints, engagements, conversions, notes } = req.body;
    const result = await pool.query(
      `INSERT INTO can_metrics (metric_date, is_ongoing, impression, touchpoints, engagements, conversions, notes)
       VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING *`,
      [metric_date || null, is_ongoing || false, impression, touchpoints || 0, engagements || 0, conversions || 0, notes]
    );
    res.status(201).json(result.rows[0]);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

router.put("/can-metrics/:id", requireStaff, async (req, res) => {
  try {
    const { id } = req.params;
    const { metric_date, is_ongoing, impression, touchpoints, engagements, conversions, notes } = req.body;
    const result = await pool.query(
      `UPDATE can_metrics SET
         metric_date = COALESCE($1, metric_date),
         is_ongoing = COALESCE($2, is_ongoing),
         impression = COALESCE($3, impression),
         touchpoints = COALESCE($4, touchpoints),
         engagements = COALESCE($5, engagements),
         conversions = COALESCE($6, conversions),
         notes = COALESCE($7, notes)
       WHERE metric_id = $8 RETURNING *`,
      [metric_date, is_ongoing, impression, touchpoints, engagements, conversions, notes, id]
    );
    res.json(result.rows[0]);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

router.delete("/can-metrics/:id", requireStaff, async (req, res) => {
  try {
    await pool.query("DELETE FROM can_metrics WHERE metric_id = $1", [req.params.id]);
    res.json({ message: "Deleted successfully" });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// =============================================
// V2 API - Normalized Schema Endpoints
// =============================================
router.get("/v2/semesters", async (req, res) => {
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

router.get("/v2/universities", async (req, res) => {
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

router.get("/v2/programs", async (req, res) => {
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

router.get("/v2/partnerships", async (req, res) => {
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
    if (semester_id) { params.push(semester_id); query += ` AND sem.id = $${params.length}`; }
    if (status) { params.push(status); query += ` AND part.status = $${params.length}`; }
    query += ` ORDER BY sem.start_date DESC, u.name, prog.name`;
    
    const result = await pool.query(query, params);
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

router.get("/v2/projects", async (req, res) => {
  try {
    const { partnership_id } = req.query;
    let query = `
      SELECT p.id, p.name, p.description, p.start_date, p.end_date,
             p.deliverable_description, pt.name AS project_type,
             part.id AS partnership_id, sem.name AS semester,
             prog.name AS program_name, u.name AS university_name
      FROM project p
      LEFT JOIN project_type pt ON p.project_type_id = pt.id
      JOIN partnership part ON p.partnership_id = part.id
      JOIN semester sem ON part.semester_id = sem.id
      JOIN program prog ON part.program_id = prog.id
      JOIN university u ON prog.university_id = u.id
      WHERE 1=1
    `;
    const params = [];
    if (partnership_id) { params.push(partnership_id); query += ` AND part.id = $${params.length}`; }
    query += ` ORDER BY p.start_date DESC`;
    
    const result = await pool.query(query, params);
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// =============================================
// Dashboard Metrics (from views)
// =============================================
const metricEndpoints = [
  { path: "/v2/metrics/active-partnerships", view: "v_metric_active_partnerships", single: true },
  { path: "/v2/metrics/students-engaged", view: "v_metric_students_engaged", single: false },
  { path: "/v2/metrics/service-hours", view: "v_metric_service_hours", single: false },
  { path: "/v2/metrics/completion-rate", view: "v_metric_completion_rate", single: false },
  { path: "/v2/metrics/university-reach", view: "v_metric_university_reach", single: true },
  { path: "/v2/metrics/program-types", view: "v_metric_program_types", single: false },
  { path: "/v2/metrics/course-impact", view: "v_metric_course_impact", single: true },
  { path: "/v2/metrics/outreach-funnel", view: "v_metric_outreach_funnel", single: false },
  { path: "/v2/metrics/project-performance", view: "v_metric_project_performance", single: false },
  { path: "/v2/metrics/retention", view: "v_metric_retention", single: true },
  { path: "/v2/metrics/staff-workload", view: "v_metric_staff_workload", single: false },
  { path: "/v2/metrics/milestones", view: "v_metric_milestones", single: false },
];

metricEndpoints.forEach(({ path, view, single }) => {
  router.get(path, async (req, res) => {
    try {
      const result = await pool.query(`SELECT * FROM ${view}`);
      res.json(single ? (result.rows[0] || {}) : result.rows);
    } catch (err) {
      res.status(500).json({ error: err.message });
    }
  });
});

// Additional view endpoints
router.get("/v2/current-activity", async (req, res) => {
  try {
    const result = await pool.query(`SELECT * FROM v_current_semester_activity`);
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

router.get("/v2/partnership-history", async (req, res) => {
  try {
    const result = await pool.query(`SELECT * FROM v_partnership_history`);
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

router.get("/v2/hours-totals", async (req, res) => {
  try {
    const result = await pool.query(`SELECT * FROM v_student_hours_totals`);
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Combined dashboard data
router.get("/v2/dashboard", async (req, res) => {
  try {
    const [
      activePartnerships, studentsEngaged, serviceHours, completionRate,
      universityReach, programTypes, courseImpact, retention, milestones
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

module.exports = router;
