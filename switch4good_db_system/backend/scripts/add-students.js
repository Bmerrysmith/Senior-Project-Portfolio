/**
 * Add 120+ students to the database for demo
 */
const pool = require('../db');

const firstNames = ['Emma', 'Liam', 'Olivia', 'Noah', 'Ava', 'Ethan', 'Sophia', 'Mason', 'Isabella', 'William', 'Mia', 'James', 'Charlotte', 'Benjamin', 'Amelia', 'Lucas', 'Harper', 'Henry', 'Evelyn', 'Alexander', 'Abigail', 'Michael', 'Emily', 'Daniel', 'Elizabeth', 'Jacob', 'Sofia', 'Logan', 'Avery', 'Jackson', 'Ella', 'Sebastian', 'Scarlett', 'Aiden', 'Grace', 'Matthew', 'Chloe', 'Samuel', 'Victoria', 'David', 'Riley', 'Joseph', 'Aria', 'Carter', 'Lily', 'Owen', 'Aurora', 'Wyatt', 'Zoey', 'John'];
const lastNames = ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez', 'Hernandez', 'Lopez', 'Gonzalez', 'Wilson', 'Anderson', 'Thomas', 'Taylor', 'Moore', 'Jackson', 'Martin', 'Lee', 'Perez', 'Thompson', 'White', 'Harris', 'Sanchez', 'Clark', 'Ramirez', 'Lewis', 'Robinson'];
const pronouns = ['she/her', 'he/him', 'they/them'];
const tshirts = ['XS', 'S', 'M', 'L', 'XL'];
const years = ['Freshman', 'Sophomore', 'Junior', 'Senior', 'Graduate'];
const majors = ['Nutrition Science', 'Public Health', 'Environmental Studies', 'Biology', 'Communications', 'Sociology', 'Psychology', 'Health Sciences'];
const interests = ['Nutrition Research', 'Public Health', 'Social Media', 'Video Production', 'Event Planning', 'Data Analysis', 'Community Outreach'];

const rand = arr => arr[Math.floor(Math.random() * arr.length)];
const randInt = (min, max) => Math.floor(Math.random() * (max - min + 1)) + min;

async function addStudents() {
  console.log('🎓 Adding students to database...\n');
  
  let added = 0;
  const usedEmails = new Set();
  
  for (let i = 0; i < 125; i++) {
    const fn = rand(firstNames);
    const ln = rand(lastNames);
    let email = `${fn.toLowerCase()}.${ln.toLowerCase()}${randInt(100, 9999)}@student.edu`;
    
    // Ensure unique email
    while (usedEmails.has(email)) {
      email = `${fn.toLowerCase()}.${ln.toLowerCase()}${randInt(10000, 99999)}@student.edu`;
    }
    usedEmails.add(email);
    
    try {
      await pool.query(
        `INSERT INTO student_pii (first_name, last_name, email, phone, pronouns, tshirt_size, year_in_school, major, areas_of_interest) 
         VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)`,
        [
          fn, 
          ln, 
          email, 
          `(${randInt(200, 999)}) ${randInt(100, 999)}-${randInt(1000, 9999)}`, 
          rand(pronouns), 
          rand(tshirts), 
          rand(years), 
          rand(majors),
          `${rand(interests)}, ${rand(interests)}`
        ]
      );
      added++;
      if (added % 25 === 0) console.log(`   Added ${added} students...`);
    } catch(e) {
      // console.log('Error:', e.message);
    }
  }
  console.log(`\n✅ Added ${added} new students`);
  
  // Get counts for registrations
  const students = await pool.query('SELECT id FROM student_pii');
  const projects = await pool.query('SELECT id FROM project');
  const staff = await pool.query('SELECT id FROM s4g_staff');
  
  console.log(`\n📊 Creating student registrations...`);
  console.log(`   Students: ${students.rows.length}, Projects: ${projects.rows.length}, Staff: ${staff.rows.length}`);
  
  let regs = 0;
  for (const s of students.rows) {
    const numProj = randInt(1, 2);
    for (let i = 0; i < numProj; i++) {
      const proj = rand(projects.rows);
      const st = rand(staff.rows);
      try {
        await pool.query(
          `INSERT INTO student_registration (student_id, project_id, s4g_staff_id, status, registration_date) 
           VALUES ($1, $2, $3, $4, CURRENT_DATE - INTERVAL '${randInt(1, 365)} days')`,
          [s.id, proj.id, st.id, rand(['Active', 'Completed', 'Active', 'Completed', 'Active'])]
        );
        regs++;
      } catch(e) {
        // Duplicate, skip
      }
    }
  }
  console.log(`✅ Added ${regs} new registrations`);
  
  // Add outreach contacts
  console.log(`\n📧 Adding outreach contacts...`);
  const universities = await pool.query('SELECT id, abbreviation FROM university');
  let contacts = 0;
  
  for (let i = 0; i < 50; i++) {
    const uni = rand(universities.rows);
    const fn = rand(firstNames);
    const ln = rand(lastNames);
    
    try {
      await pool.query(
        `INSERT INTO outreach_contact (university_id, name, title, email, department, is_primary, notes) 
         VALUES ($1, $2, $3, $4, $5, $6, $7)`,
        [
          uni.id,
          `${fn} ${ln}`,
          rand(['Professor', 'Department Chair', 'Director', 'Coordinator', 'Dean']),
          `${fn.toLowerCase()}.${ln.toLowerCase()}@${(uni.abbreviation || 'school').toLowerCase()}.edu`,
          rand(['Nutrition', 'Public Health', 'Biology', 'Health Sciences']),
          Math.random() > 0.7,
          rand(['Active collaborator', 'Interested in partnership', 'Follow-up needed', 'Initial contact made'])
        ]
      );
      contacts++;
    } catch(e) {}
  }
  console.log(`✅ Added ${contacts} outreach contacts`);
  
  // Final counts
  console.log('\n═══════════════════════════════════════════════════════════');
  console.log('📊 FINAL DATABASE COUNTS:');
  console.log('═══════════════════════════════════════════════════════════');
  
  const tables = ['semester', 's4g_staff', 'university', 'program', 'project_type', 'course', 'partnership', 'project', 'student_pii', 'student_registration', 'outreach_contact'];
  let total = 0;
  
  for (const t of tables) {
    const r = await pool.query(`SELECT COUNT(*) FROM ${t}`);
    const count = parseInt(r.rows[0].count);
    total += count;
    console.log(`   ${t.padEnd(25)} ${count}`);
  }
  
  console.log('   ─────────────────────────────────────────────');
  console.log(`   TOTAL RECORDS              ${total}`);
  console.log('═══════════════════════════════════════════════════════════');
  console.log('✅ Database ready for sponsor demo!');
  console.log('═══════════════════════════════════════════════════════════\n');
  
  await pool.end();
}

addStudents().catch(console.error);

