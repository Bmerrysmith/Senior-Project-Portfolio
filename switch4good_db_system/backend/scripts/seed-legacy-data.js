/**
 * Add demo data to the legacy tables that the frontend uses
 * (students, student_participation, programs, schools, semesters)
 */
const pool = require('../db');

const firstNames = ['Emma', 'Liam', 'Olivia', 'Noah', 'Ava', 'Ethan', 'Sophia', 'Mason', 'Isabella', 'William', 'Mia', 'James', 'Charlotte', 'Benjamin', 'Amelia', 'Lucas', 'Harper', 'Henry', 'Evelyn', 'Alexander', 'Abigail', 'Michael', 'Emily', 'Daniel', 'Elizabeth', 'Jacob', 'Sofia', 'Logan', 'Avery', 'Jackson', 'Ella', 'Sebastian', 'Scarlett', 'Aiden', 'Grace', 'Matthew', 'Chloe', 'Samuel', 'Victoria', 'David', 'Riley', 'Joseph', 'Aria', 'Carter', 'Lily', 'Owen', 'Aurora', 'Wyatt', 'Zoey', 'John'];
const lastNames = ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez', 'Hernandez', 'Lopez', 'Gonzalez', 'Wilson', 'Anderson', 'Thomas', 'Taylor', 'Moore', 'Jackson', 'Martin', 'Lee', 'Perez', 'Thompson', 'White', 'Harris', 'Sanchez', 'Clark', 'Ramirez', 'Lewis', 'Robinson'];
const pronouns = ['she/her', 'he/him', 'they/them'];
const tshirts = ['XS', 'S', 'M', 'L', 'XL', 'XXL'];
const years = ['Freshman', 'Sophomore', 'Junior', 'Senior', 'Graduate'];
const areasOfInterest = ['Nutrition Research', 'Public Health', 'Social Media', 'Video Production', 'Event Planning', 'Data Analysis', 'Community Outreach', 'Writing', 'Graphic Design'];

const schools = [
  'UCLA', 'USC', 'Stanford University', 'UC Berkeley', 'UC San Diego', 
  'UC Davis', 'Cal Poly SLO', 'San Jose State', 'Arizona State University',
  'University of Arizona', 'University of Washington', 'Oregon State University',
  'University of Colorado Boulder', 'University of Texas Austin', 'Texas A&M University',
  'University of Florida', 'Florida State University', 'NYU', 'Columbia University',
  'Cornell University', 'Boston University', 'Harvard University', 'University of Michigan',
  'Michigan State University', 'Ohio State University'
];

const programNames = [
  'Nutrition Education Initiative', 'Campus Food Justice', 'Sustainable Agriculture Program',
  'Community Health Outreach', 'Plant-Based Initiative', 'Environmental Advocacy Project',
  'Farm to Fork Program', 'Student Wellness Program', 'Food Systems Research',
  'Dairy Alternatives Project', 'Animal Welfare Education', 'Climate Action Team',
  'Health Policy Research', 'Public Health Fellowship', 'Nutrition Science Internship'
];

const projectNames = [
  'Social Media Campaign', 'Research Report', 'Community Event', 'Educational Workshop',
  'Cookbook Development', 'Video Production', 'Website Content', 'Survey Analysis',
  'Infographic Design', 'Podcast Series', 'Newsletter', 'Data Collection'
];

const semesters = [
  { season: 'Fall', year: 2025 },
  { season: 'Spring', year: 2025 },
  { season: 'Fall', year: 2024 },
  { season: 'Spring', year: 2024 },
  { season: 'Fall', year: 2023 },
  { season: 'Spring', year: 2023 },
  { season: 'Fall', year: 2022 },
  { season: 'Spring', year: 2022 },
  { season: 'Fall', year: 2021 },
  { season: 'Spring', year: 2021 },
  { season: 'Fall', year: 2020 },
  { season: 'Spring', year: 2020 }
];

const s4gStaff = ['Lucy Gonzalez', 'Marcus Chen', 'Sarah Williams', 'David Kim', 'Rachel Patel', 'James Thompson', 'Emily Rodriguez', 'Alex Johnson'];
const meetingCadences = ['Weekly', 'Bi-weekly', 'Monthly', 'As needed'];
const successMetrics = ['Completed All Deliverables', 'Exceeded Expectations', 'Met Expectations', 'In Progress', 'Outstanding'];

const rand = arr => arr[Math.floor(Math.random() * arr.length)];
const randInt = (min, max) => Math.floor(Math.random() * (max - min + 1)) + min;
const randBool = () => Math.random() > 0.5;

async function seedLegacyData() {
  console.log('🌱 Adding demo data to legacy tables...\n');
  console.log('═══════════════════════════════════════════════════════════');

  try {
    // 1. ADD SCHOOLS
    console.log('\n🏫 Adding schools...');
    const schoolIds = [];
    
    for (const schoolName of schools) {
      try {
        const result = await pool.query(
          `INSERT INTO schools (school_name) VALUES ($1)
           ON CONFLICT (school_name) DO UPDATE SET school_name = EXCLUDED.school_name
           RETURNING school_id`,
          [schoolName]
        );
        schoolIds.push({ id: result.rows[0].school_id, name: schoolName });
      } catch (e) {
        const existing = await pool.query(`SELECT school_id FROM schools WHERE school_name = $1`, [schoolName]);
        if (existing.rows.length > 0) {
          schoolIds.push({ id: existing.rows[0].school_id, name: schoolName });
        }
      }
    }
    console.log(`   ✓ ${schoolIds.length} schools ready`);

    // 2. ADD SEMESTERS
    console.log('\n📅 Adding semesters...');
    const semesterIds = [];
    
    for (const sem of semesters) {
      try {
        const result = await pool.query(
          `INSERT INTO semesters (season, year) VALUES ($1, $2)
           ON CONFLICT (season, year) DO UPDATE SET season = EXCLUDED.season
           RETURNING semester_id`,
          [sem.season, sem.year]
        );
        semesterIds.push({ id: result.rows[0].semester_id, name: `${sem.season} ${sem.year}` });
      } catch (e) {
        const existing = await pool.query(`SELECT semester_id FROM semesters WHERE season = $1 AND year = $2`, [sem.season, sem.year]);
        if (existing.rows.length > 0) {
          semesterIds.push({ id: existing.rows[0].semester_id, name: `${sem.season} ${sem.year}` });
        }
      }
    }
    console.log(`   ✓ ${semesterIds.length} semesters ready`);

    // 3. ADD PROGRAMS
    console.log('\n📋 Adding programs...');
    const programIds = [];
    
    for (const school of schoolIds) {
      // 2-3 programs per school
      const numPrograms = randInt(2, 3);
      for (let i = 0; i < numPrograms; i++) {
        const programName = rand(programNames);
        try {
          const result = await pool.query(
            `INSERT INTO programs (program_name, school_id, website, program_type, notes)
             VALUES ($1, $2, $3, $4, $5)
             RETURNING program_id`,
            [
              `${programName} - ${school.name.split(' ')[0]}`,
              school.id,
              `https://www.${school.name.toLowerCase().replace(/\s+/g, '')}.edu/${programName.toLowerCase().replace(/\s+/g, '-')}`,
              rand(['Service Learning', 'Internship', 'Fellowship', 'Research', 'Volunteer']),
              `Partnership program at ${school.name}`
            ]
          );
          programIds.push({ id: result.rows[0].program_id, name: programName, schoolId: school.id });
        } catch (e) {
          // Skip duplicates
        }
      }
    }
    console.log(`   ✓ ${programIds.length} programs created`);

    // 4. ADD STUDENTS
    console.log('\n👨‍🎓 Adding 120 students...');
    const studentIds = [];
    const usedEmails = new Set();
    
    for (let i = 0; i < 120; i++) {
      const firstName = rand(firstNames);
      const lastName = rand(lastNames);
      const fullName = `${firstName} ${lastName}`;
      let email = `${firstName.toLowerCase()}.${lastName.toLowerCase()}${randInt(1, 999)}@student.edu`;
      
      while (usedEmails.has(email)) {
        email = `${firstName.toLowerCase()}.${lastName.toLowerCase()}${randInt(1000, 9999)}@student.edu`;
      }
      usedEmails.add(email);
      
      try {
        const result = await pool.query(
          `INSERT INTO students (full_name, email, pronouns, tshirt_size, year_in_school, areas_of_interest)
           VALUES ($1, $2, $3, $4, $5, $6)
           RETURNING student_id`,
          [
            fullName,
            email,
            rand(pronouns),
            rand(tshirts),
            rand(years),
            `${rand(areasOfInterest)}, ${rand(areasOfInterest)}`
          ]
        );
        studentIds.push({ id: result.rows[0].student_id, name: fullName });
        if (studentIds.length % 30 === 0) console.log(`   Added ${studentIds.length} students...`);
      } catch (e) {
        // Skip duplicates
      }
    }
    console.log(`   ✓ ${studentIds.length} students created`);

    // 5. ADD STUDENT PARTICIPATION (Links students to programs/semesters)
    console.log('\n📊 Creating student participation records...');
    let participationCount = 0;
    
    for (const student of studentIds) {
      // Each student participates in 1-3 semesters
      const numSemesters = randInt(1, 3);
      const usedSems = new Set();
      
      for (let i = 0; i < numSemesters; i++) {
        const semester = rand(semesterIds);
        if (usedSems.has(semester.id)) continue;
        usedSems.add(semester.id);
        
        const program = rand(programIds);
        const startYear = parseInt(semester.name.split(' ')[1]);
        const startDate = `${startYear}-${randBool() ? '01' : '08'}-${randInt(10, 28)}`;
        const endDate = `${startYear}-${randBool() ? '05' : '12'}-${randInt(10, 28)}`;
        
        try {
          await pool.query(
            `INSERT INTO student_participation 
             (student_id, program_id, semester_id, sg4_staff, project, project_start_date, project_end_date,
              meeting_cadence, success_metric, total_hours)
             VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)`,
            [
              student.id,
              program.id,
              semester.id,
              rand(s4gStaff),
              rand(projectNames),
              startDate,
              endDate,
              rand(meetingCadences),
              rand(successMetrics),
              randInt(10, 150)
            ]
          );
          participationCount++;
        } catch (e) {
          // Skip duplicates
        }
      }
    }
    console.log(`   ✓ ${participationCount} participation records created`);

    // 6. ADD PROGRAM DIRECTORY (Program activity per semester)
    console.log('\n📁 Creating program directory entries...');
    let directoryCount = 0;
    
    for (const program of programIds) {
      // Each program active in 2-5 semesters
      const numSems = randInt(2, 5);
      const usedSems = new Set();
      
      for (let i = 0; i < numSems; i++) {
        const semester = rand(semesterIds);
        if (usedSems.has(semester.id)) continue;
        usedSems.add(semester.id);
        
        try {
          await pool.query(
            `INSERT INTO program_semester_activity 
             (program_id, semester_id, is_active, sg4_staff_contact, most_recent_contact_date, partner_email, notes)
             VALUES ($1, $2, $3, $4, CURRENT_DATE - INTERVAL '${randInt(1, 180)} days', $5, $6)`,
            [
              program.id,
              semester.id,
              randBool(),
              rand(s4gStaff),
              `contact@${program.name.toLowerCase().replace(/\s+/g, '').substring(0, 10)}.edu`,
              rand(['Active partnership', 'Exploring collaboration', 'Regular meetings scheduled', 'New program this semester'])
            ]
          );
          directoryCount++;
        } catch (e) {
          // Skip duplicates
        }
      }
    }
    console.log(`   ✓ ${directoryCount} directory entries created`);

    // 7. ADD CAN METRICS
    console.log('\n📈 Creating CAN metrics...');
    let metricsCount = 0;
    
    for (let i = 0; i < 50; i++) {
      try {
        await pool.query(
          `INSERT INTO can_metrics 
           (metric_date, is_ongoing, impression, touchpoints, engagements, conversions, notes)
           VALUES (CURRENT_DATE - INTERVAL '${randInt(1, 365)} days', $1, $2, $3, $4, $5, $6)`,
          [
            randBool(),
            rand(['Positive', 'Very Positive', 'Neutral', 'Good Reception', 'Excellent']),
            randInt(50, 500),
            randInt(10, 200),
            randInt(1, 50),
            `Campus outreach event - ${rand(projectNames)}`
          ]
        );
        metricsCount++;
      } catch (e) {}
    }
    console.log(`   ✓ ${metricsCount} CAN metrics created`);

    // SUMMARY
    console.log('\n═══════════════════════════════════════════════════════════');
    console.log('🎉 DEMO DATA SEED COMPLETE!');
    console.log('═══════════════════════════════════════════════════════════');
    console.log('');
    console.log('   🏫 Schools:                ' + schoolIds.length);
    console.log('   📅 Semesters:              ' + semesterIds.length);
    console.log('   📋 Programs:               ' + programIds.length);
    console.log('   👨‍🎓 Students:               ' + studentIds.length);
    console.log('   📊 Participation Records:  ' + participationCount);
    console.log('   📁 Directory Entries:      ' + directoryCount);
    console.log('   📈 CAN Metrics:            ' + metricsCount);
    console.log('   ─────────────────────────────────────────────');
    const total = schoolIds.length + semesterIds.length + programIds.length + 
                  studentIds.length + participationCount + directoryCount + metricsCount;
    console.log('   TOTAL RECORDS:             ' + total);
    console.log('');
    console.log('═══════════════════════════════════════════════════════════');
    console.log('✅ Refresh your browser to see all the demo data!');
    console.log('═══════════════════════════════════════════════════════════\n');

  } catch (err) {
    console.error('❌ Error:', err.message);
  } finally {
    await pool.end();
  }
}

seedLegacyData();

