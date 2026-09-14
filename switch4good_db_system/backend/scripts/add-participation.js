// Quick script to add participation records
const pool = require('../db');

async function run() {
  try {
    // First, let's see what's in the participation table
    const existing = await pool.query('SELECT * FROM student_participation LIMIT 1');
    console.log('Sample participation record:', existing.rows[0]);
    
    // Get all the IDs we need
    const studentsResult = await pool.query('SELECT student_id FROM students ORDER BY student_id');
    const programsResult = await pool.query('SELECT program_id FROM programs ORDER BY program_id');
    const semestersResult = await pool.query('SELECT semester_id FROM semesters ORDER BY semester_id');
    
    console.log('Students:', studentsResult.rows.length);
    console.log('Programs:', programsResult.rows.length);
    console.log('Semesters:', semestersResult.rows.length);
    
    const students = studentsResult.rows;
    const programs = programsResult.rows;
    const sems = semestersResult.rows;
    
    const projects = ['Social Media Campaign', 'Research Report', 'Event Planning', 'Video Production', 'Newsletter', 'Community Outreach', 'Mentorship Program', 'Campus Tour Guide', 'Peer Tutoring', 'Student Ambassador'];
    const metrics = ['Increased engagement by 25%', 'Completed all milestones', 'Exceeded expectations', 'Outstanding performance', 'Met all objectives', 'Strong leadership shown'];
    const cadences = ['Weekly', 'Bi-weekly', 'Monthly'];
    const conflicts = ['Tue 5pm', 'None', 'Wed afternoon', 'Mon/Fri mornings', 'Thursdays'];
    
    const rand = arr => arr[Math.floor(Math.random() * arr.length)];
    const randInt = (min, max) => Math.floor(Math.random() * (max - min + 1)) + min;
    const randDate = (year, monthStart, monthEnd) => {
      const month = randInt(monthStart, monthEnd);
      const day = randInt(1, 28);
      return `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
    };
    
    let added = 0;
    let errors = 0;
    
    // Add participation for each student
    for (let i = 0; i < Math.min(students.length, 100); i++) {
      const student = students[i];
      const numEntries = randInt(1, 3);
      
      for (let j = 0; j < numEntries; j++) {
        const program = rand(programs);
        const semester = rand(sems);
        const startDate = randDate(2024, 1, 6);
        const endDate = randDate(2024, 7, 12);
        
        try {
          await pool.query(`
            INSERT INTO student_participation 
            (student_id, program_id, semester_id, sg4_staff_id, project_name, project_start_date, project_end_date, meeting_cadence, conflicting_datetimes, success_metric)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
          `, [
            student.student_id,
            program.program_id,
            semester.semester_id,
            randInt(1, 5),  // sg4_staff_id
            rand(projects),
            startDate,
            endDate,
            rand(cadences),
            rand(conflicts),
            rand(metrics)
          ]);
          added++;
        } catch (e) {
          errors++;
          if (errors <= 5) {
            console.log('Error:', e.message);
          }
        }
      }
      
      if ((i + 1) % 20 === 0) {
        console.log(`Processed ${i + 1} students, added ${added} records...`);
      }
    }
    
    console.log(`\nDone! Added ${added} participation records (${errors} errors)`);
    
    // Final count
    const finalCount = await pool.query('SELECT COUNT(*) as count FROM student_participation');
    console.log('Total participation records:', finalCount.rows[0].count);
    
  } catch (e) {
    console.error('Fatal error:', e);
  } finally {
    await pool.end();
  }
}

run();

