const router = require("express").Router();
const pool = require("../config/database");
const { authenticate, requireStaff } = require("../middleware/auth");

router.use(authenticate);

/**
 * @route   GET /api/students
 * @desc    Get all students
 */
router.get("/", async (req, res) => {
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

/**
 * @route   POST /api/students
 * @desc    Create a student
 */
router.post("/", requireStaff, async (req, res) => {
  try {
    const { full_name, email, pronouns, tshirt_size, year_in_school, areas_of_interest } = req.body;
    const result = await pool.query(
      `INSERT INTO students (full_name, email, pronouns, tshirt_size, year_in_school, areas_of_interest)
       VALUES ($1, $2, $3, $4, $5, $6) RETURNING *`,
      [full_name, email, pronouns, tshirt_size, year_in_school, areas_of_interest]
    );
    res.status(201).json(result.rows[0]);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

/**
 * @route   PUT /api/students/:id
 * @desc    Update a student
 */
router.put("/:id", requireStaff, async (req, res) => {
  try {
    const { id } = req.params;
    const { full_name, email, pronouns, tshirt_size, year_in_school, areas_of_interest } = req.body;
    const result = await pool.query(
      `UPDATE students SET
         full_name = COALESCE($1, full_name),
         email = COALESCE($2, email),
         pronouns = COALESCE($3, pronouns),
         tshirt_size = COALESCE($4, tshirt_size),
         year_in_school = COALESCE($5, year_in_school),
         areas_of_interest = COALESCE($6, areas_of_interest)
       WHERE student_id = $7 RETURNING *`,
      [full_name, email, pronouns, tshirt_size, year_in_school, areas_of_interest, id]
    );
    res.json(result.rows[0]);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

/**
 * @route   DELETE /api/students/:id
 * @desc    Delete a student
 */
router.delete("/:id", requireStaff, async (req, res) => {
  try {
    const { id } = req.params;
    await pool.query("DELETE FROM students WHERE student_id = $1", [id]);
    res.json({ message: "Deleted successfully" });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

/**
 * @route   GET /api/students/tracker
 * @desc    Get student participation tracker with full details
 */
router.get("/tracker", async (req, res) => {
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

/**
 * @route   GET /api/students/hours/:participation_id
 * @desc    Get hours log for a participation
 */
router.get("/hours/:participation_id", async (req, res) => {
  try {
    const { participation_id } = req.params;
    const result = await pool.query(
      "SELECT * FROM hours_log WHERE participation_id = $1 ORDER BY period_number",
      [participation_id]
    );
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

/**
 * @route   POST /api/students/hours
 * @desc    Log hours for a participation
 */
router.post("/hours", requireStaff, async (req, res) => {
  try {
    const { participation_id, period_number, hours, notes } = req.body;
    const result = await pool.query(
      `INSERT INTO hours_log (participation_id, period_number, hours, notes)
       VALUES ($1, $2, $3, $4) RETURNING *`,
      [participation_id, period_number, hours, notes]
    );
    res.status(201).json(result.rows[0]);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

/**
 * @route   GET /api/students/checklist/:participation_id
 * @desc    Get checklist for a participation
 */
router.get("/checklist/:participation_id", async (req, res) => {
  try {
    const { participation_id } = req.params;
    const result = await pool.query(
      "SELECT * FROM student_checklist_item WHERE participation_id = $1 ORDER BY item_type",
      [participation_id]
    );
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

module.exports = router;
