/**
 * Seed Demo Data for Switch4Good Application
 * Generates 100+ realistic records for sponsor demonstration
 * 
 * Table structure:
 * - semester: id, name (e.g., 'Spring 2025'), academic_year, start_date, end_date, is_current
 * - s4g_staff: id, name, email, phone, role, is_active
 * - university: id, name, abbreviation, city, state, website, etc.
 * - program: id, university_id, s4g_staff_id, name, program_type, department, description, is_active
 * - course: id, program_id, course_code, course_name, etc.
 * - partnership: id, program_id, semester_id, course_id, students_participating, etc.
 * - project_type: id, name, description, is_active
 * - project: id, partnership_id, project_type_id, name, etc.
 * - student_pii: id, first_name, last_name, email, phone, pronouns, tshirt_size, year_in_school, major
 * - student_registration: id, student_id, project_id, s4g_staff_id, status, etc.
 */

const pool = require('../db');

// Sample data arrays
const firstNames = [
  'Emma', 'Liam', 'Olivia', 'Noah', 'Ava', 'Ethan', 'Sophia', 'Mason', 'Isabella', 'William',
  'Mia', 'James', 'Charlotte', 'Benjamin', 'Amelia', 'Lucas', 'Harper', 'Henry', 'Evelyn', 'Alexander',
  'Abigail', 'Michael', 'Emily', 'Daniel', 'Elizabeth', 'Jacob', 'Sofia', 'Logan', 'Avery', 'Jackson',
  'Ella', 'Sebastian', 'Scarlett', 'Aiden', 'Grace', 'Matthew', 'Chloe', 'Samuel', 'Victoria', 'David',
  'Riley', 'Joseph', 'Aria', 'Carter', 'Lily', 'Owen', 'Aurora', 'Wyatt', 'Zoey', 'John'
];

const lastNames = [
  'Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez',
  'Hernandez', 'Lopez', 'Gonzalez', 'Wilson', 'Anderson', 'Thomas', 'Taylor', 'Moore', 'Jackson', 'Martin',
  'Lee', 'Perez', 'Thompson', 'White', 'Harris', 'Sanchez', 'Clark', 'Ramirez', 'Lewis', 'Robinson',
  'Walker', 'Young', 'Allen', 'King', 'Wright', 'Scott', 'Torres', 'Nguyen', 'Hill', 'Flores'
];

const universities = [
  { name: 'UCLA', abbr: 'UCLA', city: 'Los Angeles', state: 'CA' },
  { name: 'USC', abbr: 'USC', city: 'Los Angeles', state: 'CA' },
  { name: 'Stanford University', abbr: 'Stanford', city: 'Stanford', state: 'CA' },
  { name: 'UC Berkeley', abbr: 'UCB', city: 'Berkeley', state: 'CA' },
  { name: 'UC San Diego', abbr: 'UCSD', city: 'San Diego', state: 'CA' },
  { name: 'UC Davis', abbr: 'UCD', city: 'Davis', state: 'CA' },
  { name: 'Cal Poly SLO', abbr: 'CPSLO', city: 'San Luis Obispo', state: 'CA' },
  { name: 'San Jose State University', abbr: 'SJSU', city: 'San Jose', state: 'CA' },
  { name: 'Arizona State University', abbr: 'ASU', city: 'Tempe', state: 'AZ' },
  { name: 'University of Arizona', abbr: 'UA', city: 'Tucson', state: 'AZ' },
  { name: 'University of Washington', abbr: 'UW', city: 'Seattle', state: 'WA' },
  { name: 'Oregon State University', abbr: 'OSU', city: 'Corvallis', state: 'OR' },
  { name: 'University of Colorado Boulder', abbr: 'CU', city: 'Boulder', state: 'CO' },
  { name: 'University of Texas Austin', abbr: 'UT', city: 'Austin', state: 'TX' },
  { name: 'Texas A&M University', abbr: 'TAMU', city: 'College Station', state: 'TX' },
  { name: 'University of Florida', abbr: 'UF', city: 'Gainesville', state: 'FL' },
  { name: 'Florida State University', abbr: 'FSU', city: 'Tallahassee', state: 'FL' },
  { name: 'NYU', abbr: 'NYU', city: 'New York', state: 'NY' },
  { name: 'Columbia University', abbr: 'Columbia', city: 'New York', state: 'NY' },
  { name: 'Cornell University', abbr: 'Cornell', city: 'Ithaca', state: 'NY' },
  { name: 'Boston University', abbr: 'BU', city: 'Boston', state: 'MA' },
  { name: 'Harvard University', abbr: 'Harvard', city: 'Cambridge', state: 'MA' },
  { name: 'University of Michigan', abbr: 'UMich', city: 'Ann Arbor', state: 'MI' },
  { name: 'Michigan State University', abbr: 'MSU', city: 'East Lansing', state: 'MI' },
  { name: 'Ohio State University', abbr: 'OSU-OH', city: 'Columbus', state: 'OH' }
];

const programTypes = ['Service Learning', 'Internship', 'Fellowship', 'Research', 'Other'];
const programNamePrefixes = [
  'Nutrition Education', 'Campus Food Justice', 'Sustainable Agriculture',
  'Community Health', 'Plant-Based Initiative', 'Environmental Advocacy',
  'Farm to Fork', 'Student Wellness', 'Food Systems', 'Dairy Alternatives',
  'Animal Welfare', 'Climate Action', 'Health Policy', 'Public Health',
  'Nutrition Science', 'Community Garden', 'Food Access', 'Wellness Ambassador'
];

const projectTypeNames = [
  'Social Media Campaign', 'Research Report', 'Community Event', 'Educational Workshop',
  'Cookbook Development', 'Video Production', 'Website Content', 'Survey Analysis',
  'Infographic Design', 'Podcast Series', 'Newsletter', 'Data Collection',
  'Presentation', 'Outreach Materials', 'Campus Tabling', 'Ambassador Program'
];

const semesters = [
  { name: 'Fall 2025', year: '2025-2026', start: '2025-08-25', end: '2025-12-15', current: true },
  { name: 'Spring 2025', year: '2024-2025', start: '2025-01-15', end: '2025-05-15', current: false },
  { name: 'Fall 2024', year: '2024-2025', start: '2024-08-26', end: '2024-12-13', current: false },
  { name: 'Spring 2024', year: '2023-2024', start: '2024-01-16', end: '2024-05-10', current: false },
  { name: 'Fall 2023', year: '2023-2024', start: '2023-08-28', end: '2023-12-15', current: false },
  { name: 'Spring 2023', year: '2022-2023', start: '2023-01-17', end: '2023-05-12', current: false },
  { name: 'Fall 2022', year: '2022-2023', start: '2022-08-29', end: '2022-12-16', current: false },
  { name: 'Spring 2022', year: '2021-2022', start: '2022-01-18', end: '2022-05-13', current: false },
  { name: 'Fall 2021', year: '2021-2022', start: '2021-08-30', end: '2021-12-17', current: false },
  { name: 'Spring 2021', year: '2020-2021', start: '2021-01-19', end: '2021-05-14', current: false }
];

const s4gStaffData = [
  { name: 'Lucy Gonzalez', email: 'lucy@switch4good.org', phone: '(310) 555-0101', role: 'Program Director' },
  { name: 'Marcus Chen', email: 'marcus@switch4good.org', phone: '(310) 555-0102', role: 'Outreach Coordinator' },
  { name: 'Sarah Williams', email: 'sarah@switch4good.org', phone: '(310) 555-0103', role: 'Education Manager' },
  { name: 'David Kim', email: 'david@switch4good.org', phone: '(310) 555-0104', role: 'Campus Liaison' },
  { name: 'Rachel Patel', email: 'rachel@switch4good.org', phone: '(310) 555-0105', role: 'Program Coordinator' },
  { name: 'James Thompson', email: 'james@switch4good.org', phone: '(310) 555-0106', role: 'Research Lead' },
  { name: 'Emily Rodriguez', email: 'emily@switch4good.org', phone: '(310) 555-0107', role: 'Operations Manager' },
  { name: 'Alex Johnson', email: 'alex@switch4good.org', phone: '(310) 555-0108', role: 'Student Coordinator' }
];

const courseCodes = ['NUTR', 'HLTH', 'ENVS', 'BIOL', 'COMM', 'SOCI', 'PSYC', 'PUBH'];
const pronounsList = ['she/her', 'he/him', 'they/them', 'she/they', 'he/they'];
const tshirtSizes = ['XS', 'S', 'M', 'L', 'XL', '2XL'];
const yearsInSchool = ['Freshman', 'Sophomore', 'Junior', 'Senior', 'Graduate'];
const majors = [
  'Nutrition Science', 'Public Health', 'Environmental Studies', 'Biology', 
  'Communications', 'Sociology', 'Psychology', 'Health Sciences',
  'Dietetics', 'Food Science', 'Kinesiology', 'Community Health',
  'Pre-Med', 'Biochemistry', 'Exercise Science', 'Health Education'
];
const areasOfInterest = [
  'Nutrition Research', 'Public Health', 'Environmental Science', 'Social Media',
  'Video Production', 'Graphic Design', 'Event Planning', 'Writing & Communications',
  'Data Analysis', 'Community Outreach', 'Policy Advocacy', 'Animal Welfare'
];

// Helper functions
const randomFrom = (arr) => arr[Math.floor(Math.random() * arr.length)];
const randomInt = (min, max) => Math.floor(Math.random() * (max - min + 1)) + min;
const randomBool = () => Math.random() > 0.5;
const randomDate = (year) => {
  const month = randomInt(1, 12);
  const day = randomInt(1, 28);
  return `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
};

async function seedData() {
  console.log('🌱 Starting demo data seed for Switch4Good...\n');
  console.log('═══════════════════════════════════════════════════════════');

  try {
    // =====================================================
    // 1. INSERT SEMESTERS
    // =====================================================
    console.log('\n📅 STEP 1: Inserting semesters...');
    const semesterIds = [];
    
    for (const sem of semesters) {
      try {
        const result = await pool.query(
          `INSERT INTO semester (name, academic_year, start_date, end_date, is_current)
           VALUES ($1, $2, $3, $4, $5)
           ON CONFLICT (name) DO UPDATE SET is_current = EXCLUDED.is_current
           RETURNING id`,
          [sem.name, sem.year, sem.start, sem.end, sem.current]
        );
        semesterIds.push({ id: result.rows[0].id, name: sem.name });
      } catch (e) {
        // Get existing
        const existing = await pool.query(`SELECT id FROM semester WHERE name = $1`, [sem.name]);
        if (existing.rows.length > 0) {
          semesterIds.push({ id: existing.rows[0].id, name: sem.name });
        }
      }
    }
    console.log(`   ✓ ${semesterIds.length} semesters ready`);

    // =====================================================
    // 2. INSERT S4G STAFF
    // =====================================================
    console.log('\n👥 STEP 2: Inserting S4G staff members...');
    const staffIds = [];
    
    for (const staff of s4gStaffData) {
      try {
        const result = await pool.query(
          `INSERT INTO s4g_staff (name, email, phone, role, is_active)
           VALUES ($1, $2, $3, $4, TRUE)
           ON CONFLICT (email) DO UPDATE SET name = EXCLUDED.name
           RETURNING id`,
          [staff.name, staff.email, staff.phone, staff.role]
        );
        staffIds.push({ id: result.rows[0].id, name: staff.name });
      } catch (e) {
        const existing = await pool.query(`SELECT id FROM s4g_staff WHERE email = $1`, [staff.email]);
        if (existing.rows.length > 0) {
          staffIds.push({ id: existing.rows[0].id, name: staff.name });
        }
      }
    }
    console.log(`   ✓ ${staffIds.length} staff members ready`);

    // =====================================================
    // 3. INSERT UNIVERSITIES
    // =====================================================
    console.log('\n🏫 STEP 3: Inserting universities...');
    const universityIds = [];
    
    for (const uni of universities) {
      const contactName = `${randomFrom(firstNames)} ${randomFrom(lastNames)}`;
      try {
        const result = await pool.query(
          `INSERT INTO university (name, abbreviation, city, state, website, primary_contact_name, primary_contact_email, partnership_start_date)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
           ON CONFLICT (name) DO UPDATE SET abbreviation = EXCLUDED.abbreviation
           RETURNING id`,
          [
            uni.name,
            uni.abbr,
            uni.city,
            uni.state,
            `https://www.${uni.name.toLowerCase().replace(/\s+/g, '')}.edu`,
            contactName,
            `${contactName.toLowerCase().replace(' ', '.')}@${uni.abbr.toLowerCase()}.edu`,
            randomDate(randomInt(2018, 2024))
          ]
        );
        universityIds.push({ id: result.rows[0].id, name: uni.name, abbr: uni.abbr });
      } catch (e) {
        const existing = await pool.query(`SELECT id FROM university WHERE name = $1`, [uni.name]);
        if (existing.rows.length > 0) {
          universityIds.push({ id: existing.rows[0].id, name: uni.name, abbr: uni.abbr });
        }
      }
    }
    console.log(`   ✓ ${universityIds.length} universities ready`);

    // =====================================================
    // 4. INSERT PROGRAMS
    // =====================================================
    console.log('\n📋 STEP 4: Inserting programs...');
    const programIds = [];
    const usedProgramNames = new Set();
    
    // Create 2-3 programs per university
    for (const uni of universityIds) {
      const numPrograms = randomInt(2, 3);
      for (let i = 0; i < numPrograms; i++) {
        let programName;
        let attempts = 0;
        do {
          programName = `${randomFrom(programNamePrefixes)} Program`;
          attempts++;
        } while (usedProgramNames.has(`${uni.id}-${programName}`) && attempts < 10);
        
        usedProgramNames.add(`${uni.id}-${programName}`);
        const staff = randomFrom(staffIds);
        
        try {
          const result = await pool.query(
            `INSERT INTO program (university_id, s4g_staff_id, name, program_type, department, description, is_active)
             VALUES ($1, $2, $3, $4, $5, $6, TRUE)
             RETURNING id`,
            [
              uni.id,
              staff.id,
              programName,
              randomFrom(programTypes),
              randomFrom(['Nutrition', 'Public Health', 'Environmental Studies', 'Biology', 'Health Sciences']),
              `Partnership program with ${uni.name} for ${programName.toLowerCase()}`
            ]
          );
          programIds.push({ id: result.rows[0].id, name: programName, universityId: uni.id, staffId: staff.id });
        } catch (e) {
          // Program name conflict - try different name
        }
      }
    }
    console.log(`   ✓ ${programIds.length} programs created`);

    // =====================================================
    // 5. INSERT PROJECT TYPES
    // =====================================================
    console.log('\n🏷️  STEP 5: Inserting project types...');
    const projectTypeIds = [];
    
    for (const typeName of projectTypeNames) {
      try {
        const result = await pool.query(
          `INSERT INTO project_type (name, description, is_active)
           VALUES ($1, $2, TRUE)
           ON CONFLICT (name) DO UPDATE SET description = EXCLUDED.description
           RETURNING id`,
          [typeName, `Projects involving ${typeName.toLowerCase()}`]
        );
        projectTypeIds.push({ id: result.rows[0].id, name: typeName });
      } catch (e) {
        const existing = await pool.query(`SELECT id FROM project_type WHERE name = $1`, [typeName]);
        if (existing.rows.length > 0) {
          projectTypeIds.push({ id: existing.rows[0].id, name: typeName });
        }
      }
    }
    console.log(`   ✓ ${projectTypeIds.length} project types ready`);

    // =====================================================
    // 6. INSERT COURSES
    // =====================================================
    console.log('\n📚 STEP 6: Inserting courses...');
    const courseIds = [];
    
    for (const program of programIds) {
      // Each program has 1-2 courses
      const numCourses = randomInt(1, 2);
      for (let i = 0; i < numCourses; i++) {
        const courseCode = `${randomFrom(courseCodes)} ${randomInt(100, 400)}`;
        const faculty = `Dr. ${randomFrom(firstNames)} ${randomFrom(lastNames)}`;
        
        try {
          const result = await pool.query(
            `INSERT INTO course (program_id, course_code, course_name, faculty_names, schedule, credits, includes_dairy_content)
             VALUES ($1, $2, $3, $4, $5, $6, $7)
             RETURNING id`,
            [
              program.id,
              courseCode,
              `${randomFrom(['Introduction to', 'Advanced', 'Applied', 'Foundations of'])} ${randomFrom(['Nutrition', 'Health Science', 'Food Systems', 'Public Health', 'Wellness'])}`,
              faculty,
              `${randomFrom(['Mon/Wed', 'Tue/Thu', 'MWF'])} ${randomInt(8, 16)}:00`,
              randomInt(2, 4),
              randomBool()
            ]
          );
          courseIds.push({ id: result.rows[0].id, programId: program.id });
        } catch (e) {
          // Course conflict
        }
      }
    }
    console.log(`   ✓ ${courseIds.length} courses created`);

    // =====================================================
    // 7. INSERT PARTNERSHIPS (Program + Semester)
    // =====================================================
    console.log('\n🤝 STEP 7: Creating partnerships...');
    const partnershipIds = [];
    const partnershipStatuses = ['On Track', 'Completed', 'On Track', 'On Track', 'Concerning'];
    
    // Each program participates in 2-4 semesters
    for (const program of programIds) {
      const numSemesters = randomInt(2, 4);
      const selectedSems = new Set();
      
      for (let i = 0; i < numSemesters && i < semesterIds.length; i++) {
        let sem;
        let attempts = 0;
        do {
          sem = randomFrom(semesterIds);
          attempts++;
        } while (selectedSems.has(sem.id) && attempts < 10);
        
        if (selectedSems.has(sem.id)) continue;
        selectedSems.add(sem.id);
        
        const programCourses = courseIds.filter(c => c.programId === program.id);
        const courseId = programCourses.length > 0 ? randomFrom(programCourses).id : null;
        
        try {
          const studentsParticipating = randomInt(5, 30);
          const result = await pool.query(
            `INSERT INTO partnership (program_id, semester_id, course_id, students_participating, total_in_class, status, ty_note_sent, notes)
             VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
             RETURNING id`,
            [
              program.id,
              sem.id,
              courseId,
              studentsParticipating,
              studentsParticipating + randomInt(5, 20),
              randomFrom(partnershipStatuses),
              randomBool(),
              `${sem.name} partnership with ${program.name}`
            ]
          );
          partnershipIds.push({ id: result.rows[0].id, programId: program.id, semesterId: sem.id, semesterName: sem.name });
        } catch (e) {
          // Duplicate partnership
        }
      }
    }
    console.log(`   ✓ ${partnershipIds.length} partnerships created`);

    // =====================================================
    // 8. INSERT PROJECTS
    // =====================================================
    console.log('\n📁 STEP 8: Creating projects...');
    const projectIds = [];
    
    // Each partnership has 1-3 projects
    for (const partnership of partnershipIds) {
      const numProjects = randomInt(1, 3);
      
      for (let i = 0; i < numProjects; i++) {
        const projectType = randomFrom(projectTypeIds);
        const year = parseInt(partnership.semesterName.split(' ')[1]);
        
        try {
          const result = await pool.query(
            `INSERT INTO project (partnership_id, project_type_id, name, description, start_date, end_date, max_students, deliverable_description)
             VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
             RETURNING id`,
            [
              partnership.id,
              projectType.id,
              `${projectType.name} - ${partnership.semesterName}`,
              `${projectType.name} project for the ${partnership.semesterName} semester`,
              randomDate(year),
              randomDate(year),
              randomInt(3, 10),
              `Complete ${projectType.name.toLowerCase()} deliverables by semester end`
            ]
          );
          projectIds.push({ id: result.rows[0].id, partnershipId: partnership.id, semesterName: partnership.semesterName });
        } catch (e) {
          // Project error
        }
      }
    }
    console.log(`   ✓ ${projectIds.length} projects created`);

    // =====================================================
    // 9. INSERT STUDENTS
    // =====================================================
    console.log('\n👨‍🎓 STEP 9: Inserting students (120+ records)...');
    const studentIds = [];
    const usedEmails = new Set();
    
    for (let i = 0; i < 130; i++) {
      const firstName = randomFrom(firstNames);
      const lastName = randomFrom(lastNames);
      let email = `${firstName.toLowerCase()}.${lastName.toLowerCase()}${randomInt(1, 999)}@email.com`;
      
      while (usedEmails.has(email)) {
        email = `${firstName.toLowerCase()}.${lastName.toLowerCase()}${randomInt(1000, 9999)}@email.com`;
      }
      usedEmails.add(email);
      
      try {
        const result = await pool.query(
          `INSERT INTO student_pii (first_name, last_name, email, phone, pronouns, tshirt_size, year_in_school, major, areas_of_interest)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
           RETURNING id`,
          [
            firstName,
            lastName,
            email,
            `(${randomInt(200, 999)}) ${randomInt(100, 999)}-${randomInt(1000, 9999)}`,
            randomFrom(pronounsList),
            randomFrom(tshirtSizes),
            randomFrom(yearsInSchool),
            randomFrom(majors),
            `${randomFrom(areasOfInterest)}, ${randomFrom(areasOfInterest)}`
          ]
        );
        studentIds.push({ id: result.rows[0].id, name: `${firstName} ${lastName}` });
      } catch (e) {
        // Duplicate email, skip
      }
    }
    console.log(`   ✓ ${studentIds.length} students created`);

    // =====================================================
    // 10. INSERT STUDENT REGISTRATIONS
    // =====================================================
    console.log('\n📊 STEP 10: Creating student registrations...');
    let registrationCount = 0;
    const registrationStatuses = ['Active', 'Completed', 'Active', 'Completed', 'Active'];
    
    // Each student registers for 1-3 projects
    for (const student of studentIds) {
      const numRegistrations = randomInt(1, 3);
      const registeredProjects = new Set();
      
      for (let i = 0; i < numRegistrations && projectIds.length > 0; i++) {
        let project;
        let attempts = 0;
        do {
          project = randomFrom(projectIds);
          attempts++;
        } while (registeredProjects.has(project.id) && attempts < 10);
        
        if (registeredProjects.has(project.id)) continue;
        registeredProjects.add(project.id);
        
        const staff = randomFrom(staffIds);
        const year = parseInt(project.semesterName.split(' ')[1]) || 2024;
        
        try {
          await pool.query(
            `INSERT INTO student_registration 
             (student_id, project_id, s4g_staff_id, registration_date, success_metric, 
              intro_email_date, attended_orientation, sent_headshot, completed_deliverables, status)
             VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)`,
            [
              student.id,
              project.id,
              staff.id,
              randomDate(year),
              randomFrom(['Complete all assigned tasks', 'Lead team project', 'Submit final report', 'Conduct research', 'Create content']),
              randomDate(year),
              randomBool(),
              randomBool(),
              randomBool(),
              randomFrom(registrationStatuses)
            ]
          );
          registrationCount++;
        } catch (e) {
          // Duplicate registration
        }
      }
    }
    console.log(`   ✓ ${registrationCount} student registrations created`);

    // =====================================================
    // 11. INSERT OUTREACH CONTACTS
    // =====================================================
    console.log('\n📧 STEP 11: Creating outreach contacts...');
    let outreachCount = 0;
    
    for (let i = 0; i < 40; i++) {
      const uni = randomFrom(universityIds);
      const firstName = randomFrom(firstNames);
      const lastName = randomFrom(lastNames);
      
      try {
        await pool.query(
          `INSERT INTO outreach_contact 
           (university_id, name, title, email, phone, department, is_primary, notes)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8)`,
          [
            uni.id,
            `${firstName} ${lastName}`,
            randomFrom(['Professor', 'Department Chair', 'Program Director', 'Dean', 'Coordinator']),
            `${firstName.toLowerCase()}.${lastName.toLowerCase()}@${uni.abbr.toLowerCase()}.edu`,
            `(${randomInt(200, 999)}) ${randomInt(100, 999)}-${randomInt(1000, 9999)}`,
            randomFrom(['Nutrition', 'Public Health', 'Biology', 'Health Sciences', 'Environmental Studies']),
            randomBool(),
            randomFrom(['Initial outreach completed', 'Interested in partnership', 'Follow-up scheduled', 'Active collaborator'])
          ]
        );
        outreachCount++;
      } catch (e) {
        // Duplicate contact
      }
    }
    console.log(`   ✓ ${outreachCount} outreach contacts created`);

    // =====================================================
    // SUMMARY
    // =====================================================
    console.log('\n═══════════════════════════════════════════════════════════');
    console.log('🎉 DEMO DATA SEED COMPLETE!');
    console.log('═══════════════════════════════════════════════════════════');
    console.log('');
    console.log('   📅 Semesters:              ' + semesterIds.length);
    console.log('   👥 Staff Members:          ' + staffIds.length);
    console.log('   🏫 Universities:           ' + universityIds.length);
    console.log('   📋 Programs:               ' + programIds.length);
    console.log('   🏷️  Project Types:          ' + projectTypeIds.length);
    console.log('   📚 Courses:                ' + courseIds.length);
    console.log('   🤝 Partnerships:           ' + partnershipIds.length);
    console.log('   📁 Projects:               ' + projectIds.length);
    console.log('   👨‍🎓 Students:               ' + studentIds.length);
    console.log('   📊 Registrations:          ' + registrationCount);
    console.log('   📧 Outreach Contacts:      ' + outreachCount);
    console.log('   ─────────────────────────────────────────────');
    const total = semesterIds.length + staffIds.length + universityIds.length + 
                  programIds.length + projectTypeIds.length + courseIds.length +
                  partnershipIds.length + projectIds.length + studentIds.length +
                  registrationCount + outreachCount;
    console.log('   TOTAL RECORDS:             ' + total);
    console.log('');
    console.log('═══════════════════════════════════════════════════════════');
    console.log('✅ Your database is now ready for the sponsor demo!');
    console.log('═══════════════════════════════════════════════════════════\n');

  } catch (err) {
    console.error('❌ Error seeding data:', err.message);
    console.error(err);
  } finally {
    await pool.end();
  }
}

// Run the seed
seedData();

