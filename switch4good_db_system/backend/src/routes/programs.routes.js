const router = require("express").Router();
const pool = require("../config/database");
const { authenticate, requireStaff } = require("../middleware/auth");

router.use(authenticate);

/**
 * @route   GET /api/programs
 * @desc    Get all programs with school info
 */
router.get("/", async (req, res) => {
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
      ORDER BY p.program_id
    `);
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

/**
 * @route   POST /api/programs
 * @desc    Create a program
 */
router.post("/", requireStaff, async (req, res) => {
  try {
    const { program_name, school_id, website, program_type, needs_formalization, notes } = req.body;
    const result = await pool.query(
      `INSERT INTO programs (program_name, school_id, website, program_type, needs_formalization, notes)
       VALUES ($1, $2, $3, $4, $5, $6) RETURNING *`,
      [program_name, school_id, website, program_type, needs_formalization || false, notes]
    );
    res.status(201).json(result.rows[0]);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

/**
 * @route   PUT /api/programs/:id
 * @desc    Update a program
 */
router.put("/:id", requireStaff, async (req, res) => {
  try {
    const { id } = req.params;
    const { program_name, school_id, website, program_type, needs_formalization, notes } = req.body;
    const result = await pool.query(
      `UPDATE programs SET
         program_name = COALESCE($1, program_name),
         school_id = COALESCE($2, school_id),
         website = COALESCE($3, website),
         program_type = COALESCE($4, program_type),
         needs_formalization = COALESCE($5, needs_formalization),
         notes = COALESCE($6, notes)
       WHERE program_id = $7 RETURNING *`,
      [program_name, school_id, website, program_type, needs_formalization, notes, id]
    );
    res.json(result.rows[0]);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

/**
 * @route   DELETE /api/programs/:id
 * @desc    Delete a program
 */
router.delete("/:id", requireStaff, async (req, res) => {
  try {
    const { id } = req.params;
    await pool.query("DELETE FROM programs WHERE program_id = $1", [id]);
    res.json({ message: "Deleted successfully" });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

/**
 * @route   GET /api/programs/directory
 * @desc    Get program directory with semester activity
 */
router.get("/directory", async (req, res) => {
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

module.exports = router;
