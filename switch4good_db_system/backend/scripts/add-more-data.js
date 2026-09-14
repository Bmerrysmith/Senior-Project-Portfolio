/**
 * Add additional demo data: outreach contacts, events, deliverables
 */
const pool = require('../db');

const firstNames = ['Emma', 'Liam', 'Olivia', 'Noah', 'Ava', 'Ethan', 'Sophia', 'Mason', 'Isabella', 'William', 'Mia', 'James', 'Charlotte', 'Benjamin'];
const lastNames = ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez'];
const roles = ['Professor', 'Department Chair', 'Program Director', 'Associate Dean', 'Faculty Coordinator', 'Research Director'];
const departments = ['Nutrition', 'Public Health', 'Biology', 'Health Sciences', 'Environmental Studies', 'Kinesiology'];
const contactMethods = ['Email', 'Phone', 'Video Call', 'In-Person'];

const rand = arr => arr[Math.floor(Math.random() * arr.length)];
const randInt = (min, max) => Math.floor(Math.random() * (max - min + 1)) + min;

async function addMoreData() {
  console.log('📧 Adding outreach contacts...\n');
  
  const unis = await pool.query('SELECT id, abbreviation FROM university');
  let contactCount = 0;
  
  for (let i = 0; i < 60; i++) {
    const uni = rand(unis.rows);
    const fn = rand(firstNames);
    const ln = rand(lastNames);
    
    try {
      await pool.query(
        `INSERT INTO outreach_contact (university_id, name, email, phone, role, department, preferred_contact_method, notes, is_active) 
         VALUES ($1, $2, $3, $4, $5, $6, $7, $8, true)`,
        [
          uni.id,
          `${fn} ${ln}`,
          `${fn.toLowerCase()}.${ln.toLowerCase()}${randInt(1, 99)}@${(uni.abbreviation || 'univ').toLowerCase()}.edu`,
          `(${randInt(200, 999)}) ${randInt(100, 999)}-${randInt(1000, 9999)}`,
          rand(roles),
          rand(departments),
          rand(contactMethods),
          rand(['Interested in partnership', 'Active collaborator', 'Initial meeting scheduled', 'Follow-up needed', 'Strong advocate'])
        ]
      );
      contactCount++;
    } catch(e) {}
  }
  console.log(`✅ Added ${contactCount} outreach contacts`);
  
  // Add outreach events
  console.log('\n📆 Adding outreach events...');
  const contacts = await pool.query('SELECT id FROM outreach_contact');
  const programs = await pool.query('SELECT id FROM program');
  const semesters = await pool.query('SELECT id FROM semester');
  const staff = await pool.query('SELECT id FROM s4g_staff');
  
  let eventCount = 0;
  const eventTypes = ['touchpoint', 'engagement', 'conversion'];
  const outcomes = ['Positive response', 'Meeting scheduled', 'Partnership confirmed', 'Needs follow-up', 'Very interested'];
  
  for (let i = 0; i < 80; i++) {
    try {
      await pool.query(
        `INSERT INTO outreach_event (contact_id, program_id, semester_id, s4g_staff_id, event_type, event_date, contact_method, subject, outcome, notes)
         VALUES ($1, $2, $3, $4, $5, CURRENT_DATE - INTERVAL '${randInt(1, 365)} days', $6, $7, $8, $9)`,
        [
          contacts.rows.length > 0 ? rand(contacts.rows).id : null,
          rand(programs.rows).id,
          rand(semesters.rows).id,
          rand(staff.rows).id,
          rand(eventTypes),
          rand(contactMethods),
          rand(['Initial Outreach', 'Follow-up Discussion', 'Partnership Review', 'Program Planning', 'Check-in Meeting']),
          rand(outcomes),
          rand(['Great conversation', 'Very receptive', 'Needs more info', 'Ready to commit', 'Scheduling next steps'])
        ]
      );
      eventCount++;
    } catch(e) {}
  }
  console.log(`✅ Added ${eventCount} outreach events`);
  
  // Add weekly hours for student registrations
  console.log('\n⏰ Adding weekly hours...');
  const registrations = await pool.query('SELECT id FROM student_registration');
  let hoursCount = 0;
  
  for (const reg of registrations.rows) {
    // Add 4-12 weeks of hours per registration
    const numWeeks = randInt(4, 12);
    for (let w = 0; w < numWeeks; w++) {
      try {
        await pool.query(
          `INSERT INTO weekly_hours (registration_id, week_number, hours_logged, notes)
           VALUES ($1, $2, $3, $4)`,
          [
            reg.id,
            w + 1,
            randInt(2, 12),
            rand(['Research', 'Content creation', 'Meetings', 'Event prep', 'Outreach', 'Documentation', 'Analysis'])
          ]
        );
        hoursCount++;
      } catch(e) {}
    }
  }
  console.log(`✅ Added ${hoursCount} weekly hour records`);
  
  // Add deliverables
  console.log('\n📦 Adding deliverables...');
  const deliverableTypes = ['Report', 'Presentation', 'Video', 'Infographic', 'Social Media Post', 'Research Summary', 'Event Plan'];
  let delivCount = 0;
  
  for (const reg of registrations.rows.slice(0, 100)) {
    const numDeliv = randInt(1, 3);
    for (let d = 0; d < numDeliv; d++) {
      try {
        await pool.query(
          `INSERT INTO deliverable (registration_id, title, description, due_date, submitted_date, status, feedback)
           VALUES ($1, $2, $3, CURRENT_DATE + INTERVAL '${randInt(-30, 60)} days', $4, $5, $6)`,
          [
            reg.id,
            `${rand(deliverableTypes)} - Week ${randInt(1, 15)}`,
            rand(['Complete assigned tasks', 'Create content for campaign', 'Research and analysis', 'Event coordination', 'Outreach documentation']),
            Math.random() > 0.3 ? `CURRENT_DATE - INTERVAL '${randInt(1, 30)} days'` : null,
            rand(['Pending', 'Submitted', 'Approved', 'Needs Revision', 'Submitted', 'Approved']),
            rand(['Great work!', 'Please revise', 'Excellent quality', 'On track', 'Needs more detail', null])
          ]
        );
        delivCount++;
      } catch(e) {}
    }
  }
  console.log(`✅ Added ${delivCount} deliverables`);
  
  // Final summary
  console.log('\n═══════════════════════════════════════════════════════════');
  console.log('📊 FINAL DATABASE SUMMARY:');
  console.log('═══════════════════════════════════════════════════════════');
  
  const tables = [
    'semester', 's4g_staff', 'university', 'program', 'project_type', 
    'course', 'partnership', 'project', 'student_pii', 'student_registration',
    'outreach_contact', 'outreach_event', 'weekly_hours', 'deliverable'
  ];
  
  let total = 0;
  for (const t of tables) {
    try {
      const r = await pool.query(`SELECT COUNT(*) FROM ${t}`);
      const count = parseInt(r.rows[0].count);
      total += count;
      console.log(`   ${t.padEnd(25)} ${count}`);
    } catch(e) {
      console.log(`   ${t.padEnd(25)} (table not found)`);
    }
  }
  
  console.log('   ─────────────────────────────────────────────');
  console.log(`   TOTAL RECORDS              ${total}`);
  console.log('═══════════════════════════════════════════════════════════');
  console.log('🎉 Database fully populated for sponsor demo!');
  console.log('═══════════════════════════════════════════════════════════\n');
  
  await pool.end();
}

addMoreData().catch(console.error);

