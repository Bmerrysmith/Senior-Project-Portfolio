const router = require("express").Router();
const pool = require("../config/database");
const { authenticate, requireStaff } = require("../middleware/auth");

router.use(authenticate);

// =============================================
// SS1 Program/Course Tab
// =============================================
router.get("/program-course", async (req, res) => {
  try {
    const result = await pool.query(`
      SELECT stg_id as id, school, sg4_staff, program, faculty_staff, ty_note,
             students_participating, total_classes_in_session, status, notes,
             next_steps, course_details, source_file, imported_at
      FROM stg_ss1_program_course_tab ORDER BY stg_id ASC
    `);
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

router.post("/program-course", requireStaff, async (req, res) => {
  try {
    const { school, sg4_staff, program, faculty_staff, ty_note, students_participating, 
            total_classes_in_session, status, notes, next_steps, course_details } = req.body;
    const result = await pool.query(
      `INSERT INTO stg_ss1_program_course_tab 
       (school, sg4_staff, program, faculty_staff, ty_note, students_participating, 
        total_classes_in_session, status, notes, next_steps, course_details, imported_at)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, NOW()) RETURNING *`,
      [school, sg4_staff, program, faculty_staff, ty_note, students_participating, 
       total_classes_in_session, status, notes, next_steps, course_details]
    );
    res.status(201).json(result.rows[0]);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

router.put("/program-course/:id", requireStaff, async (req, res) => {
  try {
    const { id } = req.params;
    const allowedFields = ['school', 'sg4_staff', 'program', 'faculty_staff', 'ty_note', 
                           'students_participating', 'total_classes_in_session', 'status', 
                           'notes', 'next_steps', 'course_details'];
    const updates = [], values = [];
    let paramCount = 1;
    
    for (const field of allowedFields) {
      if (req.body[field] !== undefined) {
        updates.push(`${field} = $${paramCount++}`);
        values.push(req.body[field]);
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

router.delete("/program-course/:id", requireStaff, async (req, res) => {
  try {
    await pool.query('DELETE FROM stg_ss1_program_course_tab WHERE stg_id = $1', [req.params.id]);
    res.json({ message: 'Deleted successfully' });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// =============================================
// SS1 Student Tracker
// =============================================
router.get("/student-tracker", async (req, res) => {
  try {
    const result = await pool.query(`
      SELECT stg_id as id, name, sg4_staff, pronouns, tshirt_size, school_program,
             email_address, year_in_school, areas_of_interest, projects, project_duration,
             meeting_cadence, conflicting_dates_times, success_metric, date_intro_email_sent,
             attended_orientation, read_community_guidelines, signed_media_release, sent_headshot,
             completed_deliverables_raw as completed_deliverables, survey_checkins_raw as survey_checkins,
             meeting_checkins_raw as meeting_checkins, hours_worked_raw as hours_worked,
             total_hours_per_student as total_hours, notes_raw as notes, source_file, imported_at
      FROM stg_ss1_student_tracker ORDER BY stg_id ASC
    `);
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

router.post("/student-tracker", requireStaff, async (req, res) => {
  try {
    const { name, sg4_staff, pronouns, tshirt_size, school_program, email_address, year_in_school,
            areas_of_interest, projects, project_duration, meeting_cadence, conflicting_dates_times,
            success_metric, date_intro_email_sent, attended_orientation, read_community_guidelines,
            signed_media_release, sent_headshot, completed_deliverables, survey_checkins,
            meeting_checkins, hours_worked, total_hours, notes } = req.body;
    const result = await pool.query(
      `INSERT INTO stg_ss1_student_tracker 
       (name, sg4_staff, pronouns, tshirt_size, school_program, email_address, year_in_school,
        areas_of_interest, projects, project_duration, meeting_cadence, conflicting_dates_times,
        success_metric, date_intro_email_sent, attended_orientation, read_community_guidelines,
        signed_media_release, sent_headshot, completed_deliverables_raw, survey_checkins_raw,
        meeting_checkins_raw, hours_worked_raw, total_hours_per_student, notes_raw, imported_at)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, NOW())
       RETURNING *`,
      [name, sg4_staff, pronouns, tshirt_size, school_program, email_address, year_in_school,
       areas_of_interest, projects, project_duration, meeting_cadence, conflicting_dates_times,
       success_metric, date_intro_email_sent, attended_orientation, read_community_guidelines,
       signed_media_release, sent_headshot, completed_deliverables, survey_checkins,
       meeting_checkins, hours_worked, total_hours, notes]
    );
    res.status(201).json(result.rows[0]);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

router.delete("/student-tracker/:id", requireStaff, async (req, res) => {
  try {
    await pool.query('DELETE FROM stg_ss1_student_tracker WHERE stg_id = $1', [req.params.id]);
    res.json({ message: 'Deleted successfully' });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// =============================================
// SS2 CAN Metrics
// =============================================
router.get("/can-metrics", async (req, res) => {
  try {
    const result = await pool.query(`
      SELECT stg_id as id, date_raw as date, impression, touchpoints_raw as touchpoints,
             engagements_raw as engagements, conversions_raw as conversions, source_file, imported_at
      FROM stg_ss2_can_metrics ORDER BY stg_id ASC
    `);
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

router.post("/can-metrics", requireStaff, async (req, res) => {
  try {
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

router.delete("/can-metrics/:id", requireStaff, async (req, res) => {
  try {
    await pool.query('DELETE FROM stg_ss2_can_metrics WHERE stg_id = $1', [req.params.id]);
    res.json({ message: 'Deleted successfully' });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// =============================================
// SS3 Program Directory
// =============================================
router.get("/program-directory", async (req, res) => {
  try {
    const result = await pool.query(`
      SELECT stg_id as id, program, website, program_type, school, season, semesters_active,
             needs_formalization_raw as needs_formalization, most_recent_contact_raw as most_recent_contact,
             sg4_staff_contact, staff, email_address, notes, source_file, imported_at
      FROM stg_ss3_program_directory ORDER BY stg_id ASC
    `);
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

router.post("/program-directory", requireStaff, async (req, res) => {
  try {
    const { program, website, program_type, school, season, semesters_active, needs_formalization,
            most_recent_contact, sg4_staff_contact, staff, email_address, notes } = req.body;
    const result = await pool.query(
      `INSERT INTO stg_ss3_program_directory 
       (program, website, program_type, school, season, semesters_active, needs_formalization_raw,
        most_recent_contact_raw, sg4_staff_contact, staff, email_address, notes, imported_at)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, NOW()) RETURNING *`,
      [program, website, program_type, school, season, semesters_active, needs_formalization,
       most_recent_contact, sg4_staff_contact, staff, email_address, notes]
    );
    res.status(201).json(result.rows[0]);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

router.delete("/program-directory/:id", requireStaff, async (req, res) => {
  try {
    await pool.query('DELETE FROM stg_ss3_program_directory WHERE stg_id = $1', [req.params.id]);
    res.json({ message: 'Deleted successfully' });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

module.exports = router;
