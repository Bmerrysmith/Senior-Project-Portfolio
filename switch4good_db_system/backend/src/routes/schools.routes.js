const router = require("express").Router();
const pool = require("../config/database");
const { authenticate, requireStaff } = require("../middleware/auth");

// All routes require authentication
router.use(authenticate);

/**
 * @route   GET /api/schools
 * @desc    Get all schools
 */
router.get("/", async (req, res) => {
  try {
    const result = await pool.query("SELECT * FROM schools ORDER BY school_id");
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

/**
 * @route   POST /api/schools
 * @desc    Create a school
 */
router.post("/", requireStaff, async (req, res) => {
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

/**
 * @route   PUT /api/schools/:id
 * @desc    Update a school
 */
router.put("/:id", requireStaff, async (req, res) => {
  try {
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

/**
 * @route   DELETE /api/schools/:id
 * @desc    Delete a school
 */
router.delete("/:id", requireStaff, async (req, res) => {
  try {
    const { id } = req.params;
    await pool.query("DELETE FROM schools WHERE school_id = $1", [id]);
    res.json({ message: "Deleted successfully" });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

module.exports = router;
