-- ============================================================================
-- SWITCH4GOOD IMPACT TRACKING DATABASE
-- Complete Normalized Schema Design
-- ============================================================================
-- 
-- This file contains the complete database redesign replacing Excel workflows
-- with a proper relational structure.
--
-- TABLE OF CONTENTS:
-- 1. ERD Overview (Comments)
-- 2. Core DDL (CREATE TABLE statements)
-- 3. Privacy/Security Model (Roles, RLS, Views)
-- 4. Reporting Views
-- 5. Data Quality Constraints & Triggers
-- 6. Seed Data
-- 7. Sample Queries
--
-- ============================================================================


-- ============================================================================
-- SECTION 1: ENTITY RELATIONSHIP DIAGRAM (TEXT FORM)
-- ============================================================================
/*
NORMALIZED ERD OVERVIEW
=======================

┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│    SEMESTER     │     │   UNIVERSITY    │     │  S4G_STAFF      │
├─────────────────┤     ├─────────────────┤     ├─────────────────┤
│ PK: id          │     │ PK: id          │     │ PK: id          │
│ name            │     │ name            │     │ name            │
│ start_date      │     │ city, state     │     │ email           │
│ end_date        │     │ contact_name    │     │ role            │
│ is_current      │     │ contact_email   │     └────────┬────────┘
└────────┬────────┘     └────────┬────────┘              │
         │                       │                       │
         │    ┌──────────────────┴───────────────┐      │
         │    │                                   │      │
         ▼    ▼                                   │      │
┌─────────────────┐                               │      │
│    PROGRAM      │◄──────────────────────────────┘      │
├─────────────────┤         (s4g_staff_id)              │
│ PK: id          │                                      │
│ FK: university_id│                                     │
│ FK: s4g_staff_id │                                     │
│ name            │                                      │
│ program_type    │                                      │
└────────┬────────┘                                      │
         │                                               │
         │    ┌─────────────────┐                        │
         │    │     COURSE      │                        │
         │    ├─────────────────┤                        │
         │    │ PK: id          │                        │
         │    │ FK: program_id  │                        │
         ▼    │ course_code     │                        │
┌─────────────────┐    │ includes_dairy_content │       │
│  PARTNERSHIP    │    └────────┬────────┘              │
├─────────────────┤             │                        │
│ PK: id          │             │                        │
│ FK: program_id  │◄────────────┘                        │
│ FK: semester_id │                                      │
│ FK: course_id   │                                      │
│ status          │                                      │
│ students_participating │                               │
│ total_in_class  │                                      │
└────────┬────────┘                                      │
         │                                               │
         │         ┌─────────────────┐                   │
         │         │  STUDENT_PII    │ (Restricted)      │
         │         ├─────────────────┤                   │
         │         │ PK: id          │                   │
         │         │ name            │                   │
         │         │ email           │                   │
         │         │ pronouns        │                   │
         ▼         └────────┬────────┘                   │
┌─────────────────┐         │                            │
│    PROJECT      │         │                            │
├─────────────────┤         │                            │
│ PK: id          │         │                            │
│ FK: partnership_id│        │                            │
│ name            │         │                            │
│ project_type    │         │                            │
│ start_date      │         │                            │
│ end_date        │         │                            │
└────────┬────────┘         │                            │
         │                  │                            │
         ▼                  ▼                            │
┌─────────────────────────────────────┐                  │
│       STUDENT_REGISTRATION          │◄─────────────────┘
├─────────────────────────────────────┤   (s4g_staff_id)
│ PK: id                              │
│ FK: student_id (to STUDENT_PII)     │
│ FK: project_id                      │
│ FK: s4g_staff_id                    │
│ success_metric                      │
│ attended_orientation                │
│ completed_deliverables              │
└────────┬────────────────────────────┘
         │
         ▼
┌─────────────────┐     ┌─────────────────┐
│  WEEKLY_HOURS   │     │   DELIVERABLE   │
├─────────────────┤     ├─────────────────┤
│ PK: id          │     │ PK: id          │
│ FK: registration_id │  │ FK: registration_id │
│ week_start_date │     │ name            │
│ hours_worked    │     │ due_date        │
│ notes           │     │ completed       │
└─────────────────┘     └─────────────────┘


OUTREACH MODULE
===============

┌─────────────────┐     ┌─────────────────┐
│ OUTREACH_CONTACT│     │  OUTREACH_EVENT │
├─────────────────┤     ├─────────────────┤
│ PK: id          │     │ PK: id          │
│ FK: university_id│     │ FK: contact_id  │
│ contact_name    │     │ FK: semester_id │
│ contact_email   │     │ event_type      │
│ contact_role    │     │ (touchpoint/    │
└────────┬────────┘     │  engagement/    │
         │              │  conversion)    │
         └──────────────┤ event_date      │
                        │ notes           │
                        └─────────────────┘


EXCEL COLUMN MAPPING
====================

OLD EXCEL "Service Learning Programs" TAB:
------------------------------------------
Excel Column              → New Table.Column
---------------------------------------------------------------------------
Semester                  → semester.name (via partnership.semester_id)
School                    → university.name (via program.university_id)
S4G Staff                 → s4g_staff.name (via program.s4g_staff_id)
Program                   → program.name
Faculty/Staff             → course.faculty_names
TY Note Sent              → partnership.ty_note_sent
Students Participating    → partnership.students_participating
Total Students in Class   → partnership.total_in_class
Status                    → partnership.status
Notes                     → partnership.notes
Next Steps                → partnership.next_steps
Course Details            → course.course_code + course.schedule + course.description


OLD EXCEL "Students" TAB:
-------------------------
Excel Column              → New Table.Column
---------------------------------------------------------------------------
Semester                  → (derived from project → partnership → semester)
Name                      → student_pii.name [RESTRICTED]
S4G Staff                 → s4g_staff.name (via student_registration.s4g_staff_id)
Pronouns                  → student_pii.pronouns [RESTRICTED]
T-Shirt Size              → student_pii.tshirt_size [RESTRICTED]
School/Program            → (derived from registration → project → partnership → program → university)
Email                     → student_pii.email [RESTRICTED]
Year in School            → student_pii.year_in_school
Areas of Interest         → student_pii.areas_of_interest
Projects                  → project.name (via student_registration.project_id)
Project Duration          → project.start_date + project.end_date
Conflicting Dates         → student_registration.conflicting_dates
Success Metric            → student_registration.success_metric
Date Intro Email Sent     → student_registration.intro_email_date
Attended Orientation      → student_registration.attended_orientation
Sent Headshot             → student_registration.sent_headshot
Completed Deliverables    → student_registration.completed_deliverables
Total Hours Worked        → SUM(weekly_hours.hours_worked) [COMPUTED]


OLD AIRTABLE "Outreach" FIELDS:
-------------------------------
Airtable Field            → New Table.Column
---------------------------------------------------------------------------
Program                   → program.name
Program Type              → program.program_type
Most Recent Contact       → MAX(outreach_event.event_date)
Staff                     → s4g_staff.name
Notes                     → outreach_event.notes
Touchpoints               → COUNT(outreach_event) WHERE type='touchpoint'
Engagements               → COUNT(outreach_event) WHERE type='engagement'
Conversions               → COUNT(outreach_event) WHERE type='conversion'

*/


-- ============================================================================
-- SECTION 2: DDL - CREATE TABLES
-- ============================================================================

-- Drop existing tables if doing a full reset (comment out in production)
-- DROP SCHEMA public CASCADE; CREATE SCHEMA public;

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ----------------------------------------
-- DIMENSION TABLES
-- ----------------------------------------

-- Semester dimension: replaces "one tab per semester" approach
CREATE TABLE IF NOT EXISTS semester (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE,  -- e.g., 'Spring 2025', 'Fall 2025'
    academic_year VARCHAR(20),         -- e.g., '2024-2025'
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    is_current BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT chk_semester_dates CHECK (end_date > start_date),
    CONSTRAINT chk_semester_name CHECK (name ~ '^(Spring|Summer|Fall|Winter) \d{4}$')
);

CREATE INDEX idx_semester_name ON semester(name);
CREATE INDEX idx_semester_current ON semester(is_current) WHERE is_current = TRUE;
CREATE INDEX idx_semester_dates ON semester(start_date, end_date);

-- S4G Staff members
CREATE TABLE IF NOT EXISTS s4g_staff (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE,
    phone VARCHAR(50),
    role VARCHAR(100),  -- e.g., 'Program Coordinator', 'Director'
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_s4g_staff_active ON s4g_staff(is_active) WHERE is_active = TRUE;

-- Universities/Schools
CREATE TABLE IF NOT EXISTS university (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    abbreviation VARCHAR(20),
    city VARCHAR(100),
    state VARCHAR(50),
    website VARCHAR(500),
    primary_contact_name VARCHAR(255),
    primary_contact_email VARCHAR(255),
    primary_contact_phone VARCHAR(50),
    partnership_start_date DATE,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_university_name ON university(name);
CREATE INDEX idx_university_state ON university(state);

-- Programs within universities
CREATE TABLE IF NOT EXISTS program (
    id SERIAL PRIMARY KEY,
    university_id INTEGER NOT NULL REFERENCES university(id) ON DELETE CASCADE,
    s4g_staff_id INTEGER REFERENCES s4g_staff(id) ON DELETE SET NULL,
    name VARCHAR(255) NOT NULL,
    program_type VARCHAR(100),  -- 'Service Learning', 'Internship', 'Fellowship', 'Research', 'Other'
    department VARCHAR(255),
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT chk_program_type CHECK (
        program_type IN ('Service Learning', 'Internship', 'Fellowship', 'Research', 'Other')
    ),
    CONSTRAINT uq_program_university UNIQUE (university_id, name)
);

CREATE INDEX idx_program_university ON program(university_id);
CREATE INDEX idx_program_staff ON program(s4g_staff_id);
CREATE INDEX idx_program_type ON program(program_type);

-- Courses associated with programs
CREATE TABLE IF NOT EXISTS course (
    id SERIAL PRIMARY KEY,
    program_id INTEGER NOT NULL REFERENCES program(id) ON DELETE CASCADE,
    course_code VARCHAR(50),           -- e.g., 'CE101', 'NUTR 201'
    course_name VARCHAR(255) NOT NULL,
    faculty_names TEXT,                -- Comma-separated faculty
    schedule VARCHAR(255),             -- e.g., 'Mon/Wed 2:00-3:30pm'
    description TEXT,                  -- Catalog description
    credits INTEGER,
    includes_dairy_content BOOLEAN DEFAULT FALSE,  -- Key tracking field
    dairy_content_added_date DATE,     -- When dairy content was added (after partnership)
    dairy_content_notes TEXT,          -- What dairy content was added
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT chk_credits CHECK (credits IS NULL OR credits > 0)
);

CREATE INDEX idx_course_program ON course(program_id);
CREATE INDEX idx_course_dairy ON course(includes_dairy_content) WHERE includes_dairy_content = TRUE;

-- ----------------------------------------
-- PARTNERSHIP & PROJECT TABLES
-- ----------------------------------------

-- Partnership: Links Program to Semester (the core "activity" record)
CREATE TABLE IF NOT EXISTS partnership (
    id SERIAL PRIMARY KEY,
    program_id INTEGER NOT NULL REFERENCES program(id) ON DELETE CASCADE,
    semester_id INTEGER NOT NULL REFERENCES semester(id) ON DELETE RESTRICT,
    course_id INTEGER REFERENCES course(id) ON DELETE SET NULL,
    
    -- Participation metrics
    students_participating INTEGER DEFAULT 0,
    total_in_class INTEGER DEFAULT 0,
    
    -- Status tracking
    status VARCHAR(50) DEFAULT 'On Track',
    ty_note_sent BOOLEAN DEFAULT FALSE,
    ty_note_sent_date DATE,
    
    -- Notes and follow-up
    notes TEXT,
    next_steps TEXT,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT chk_partnership_status CHECK (
        status IN ('On Track', 'Concerning', 'No longer participating', 'Completed', 'On Hold')
    ),
    CONSTRAINT chk_students_count CHECK (students_participating >= 0),
    CONSTRAINT chk_class_count CHECK (total_in_class >= 0),
    CONSTRAINT chk_participation CHECK (students_participating <= total_in_class OR total_in_class = 0),
    CONSTRAINT uq_partnership_semester UNIQUE (program_id, semester_id)
);

CREATE INDEX idx_partnership_program ON partnership(program_id);
CREATE INDEX idx_partnership_semester ON partnership(semester_id);
CREATE INDEX idx_partnership_status ON partnership(status);
CREATE INDEX idx_partnership_program_semester ON partnership(program_id, semester_id);

-- Project types lookup
CREATE TABLE IF NOT EXISTS project_type (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE
);

-- Projects within partnerships
CREATE TABLE IF NOT EXISTS project (
    id SERIAL PRIMARY KEY,
    partnership_id INTEGER NOT NULL REFERENCES partnership(id) ON DELETE CASCADE,
    project_type_id INTEGER REFERENCES project_type(id) ON DELETE SET NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    start_date DATE,
    end_date DATE,
    max_students INTEGER,
    deliverable_description TEXT,  -- What defines "success"
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT chk_project_dates CHECK (end_date IS NULL OR start_date IS NULL OR end_date >= start_date)
);

CREATE INDEX idx_project_partnership ON project(partnership_id);
CREATE INDEX idx_project_type ON project(project_type_id);
CREATE INDEX idx_project_dates ON project(start_date, end_date);

-- ----------------------------------------
-- STUDENT TABLES (PII SEPARATED)
-- ----------------------------------------

-- Student PII - RESTRICTED ACCESS
-- Only admin/staff roles should access this table
CREATE TABLE IF NOT EXISTS student_pii (
    id SERIAL PRIMARY KEY,
    -- Identifying information (PII)
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE,
    phone VARCHAR(50),
    pronouns VARCHAR(50),
    tshirt_size VARCHAR(20),
    
    -- Non-sensitive demographic (still somewhat sensitive)
    year_in_school VARCHAR(50),  -- 'Freshman', 'Sophomore', 'Junior', 'Senior', 'Graduate'
    major VARCHAR(255),
    areas_of_interest TEXT,
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT chk_year_in_school CHECK (
        year_in_school IS NULL OR 
        year_in_school IN ('Freshman', 'Sophomore', 'Junior', 'Senior', 'Graduate', 'Other')
    ),
    CONSTRAINT chk_tshirt_size CHECK (
        tshirt_size IS NULL OR
        tshirt_size IN ('XS', 'S', 'M', 'L', 'XL', '2XL', '3XL')
    )
);

CREATE INDEX idx_student_pii_email ON student_pii(email);
CREATE INDEX idx_student_pii_name ON student_pii(last_name, first_name);

-- Student Registration: Links Student to Project (de-identified for reporting)
CREATE TABLE IF NOT EXISTS student_registration (
    id SERIAL PRIMARY KEY,
    student_id INTEGER NOT NULL REFERENCES student_pii(id) ON DELETE CASCADE,
    project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    s4g_staff_id INTEGER REFERENCES s4g_staff(id) ON DELETE SET NULL,
    
    -- Registration details
    registration_date DATE DEFAULT CURRENT_DATE,
    success_metric TEXT,           -- What this student needs to accomplish
    conflicting_dates TEXT,        -- School breaks, exams
    
    -- Milestones
    intro_email_date DATE,
    attended_orientation BOOLEAN DEFAULT FALSE,
    orientation_date DATE,
    sent_headshot BOOLEAN DEFAULT FALSE,
    headshot_date DATE,
    completed_deliverables BOOLEAN DEFAULT FALSE,
    completion_date DATE,
    
    -- Status
    status VARCHAR(50) DEFAULT 'Active',
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT chk_registration_status CHECK (
        status IN ('Active', 'Completed', 'Withdrawn', 'Incomplete')
    ),
    CONSTRAINT uq_student_project UNIQUE (student_id, project_id)
);

CREATE INDEX idx_registration_student ON student_registration(student_id);
CREATE INDEX idx_registration_project ON student_registration(project_id);
CREATE INDEX idx_registration_staff ON student_registration(s4g_staff_id);
CREATE INDEX idx_registration_status ON student_registration(status);

-- Weekly Hours tracking
CREATE TABLE IF NOT EXISTS weekly_hours (
    id SERIAL PRIMARY KEY,
    registration_id INTEGER NOT NULL REFERENCES student_registration(id) ON DELETE CASCADE,
    week_start_date DATE NOT NULL,  -- Monday of the week
    hours_worked DECIMAL(5,2) NOT NULL DEFAULT 0,
    checkin_type VARCHAR(50),       -- 'survey', 'meeting', 'self-report'
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT chk_hours_positive CHECK (hours_worked >= 0),
    CONSTRAINT chk_hours_reasonable CHECK (hours_worked <= 80),  -- Max 80 hours/week
    CONSTRAINT uq_weekly_hours UNIQUE (registration_id, week_start_date)
);

CREATE INDEX idx_weekly_hours_registration ON weekly_hours(registration_id);
CREATE INDEX idx_weekly_hours_date ON weekly_hours(week_start_date);

-- Deliverables tracking
CREATE TABLE IF NOT EXISTS deliverable (
    id SERIAL PRIMARY KEY,
    registration_id INTEGER NOT NULL REFERENCES student_registration(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    due_date DATE,
    submitted_date DATE,
    is_completed BOOLEAN DEFAULT FALSE,
    feedback TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_deliverable_registration ON deliverable(registration_id);
CREATE INDEX idx_deliverable_due ON deliverable(due_date);
CREATE INDEX idx_deliverable_completed ON deliverable(is_completed);

-- ----------------------------------------
-- OUTREACH MODULE
-- ----------------------------------------

-- Outreach contacts at universities (separate from program faculty)
CREATE TABLE IF NOT EXISTS outreach_contact (
    id SERIAL PRIMARY KEY,
    university_id INTEGER REFERENCES university(id) ON DELETE SET NULL,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255),
    phone VARCHAR(50),
    role VARCHAR(255),              -- Their title/position
    department VARCHAR(255),
    preferred_contact_method VARCHAR(50),
    notes TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT chk_contact_method CHECK (
        preferred_contact_method IS NULL OR
        preferred_contact_method IN ('Email', 'Phone', 'In-Person', 'Video Call')
    )
);

CREATE INDEX idx_outreach_contact_university ON outreach_contact(university_id);
CREATE INDEX idx_outreach_contact_active ON outreach_contact(is_active) WHERE is_active = TRUE;

-- Outreach events: touchpoints, engagements, conversions
CREATE TABLE IF NOT EXISTS outreach_event (
    id SERIAL PRIMARY KEY,
    contact_id INTEGER REFERENCES outreach_contact(id) ON DELETE SET NULL,
    program_id INTEGER REFERENCES program(id) ON DELETE SET NULL,
    semester_id INTEGER REFERENCES semester(id) ON DELETE SET NULL,
    s4g_staff_id INTEGER REFERENCES s4g_staff(id) ON DELETE SET NULL,
    
    event_type VARCHAR(50) NOT NULL,  -- 'touchpoint', 'engagement', 'conversion'
    event_date DATE NOT NULL,
    contact_method VARCHAR(50),
    subject VARCHAR(500),
    notes TEXT,
    outcome VARCHAR(255),
    follow_up_date DATE,
    follow_up_completed BOOLEAN DEFAULT FALSE,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT chk_event_type CHECK (
        event_type IN ('touchpoint', 'engagement', 'conversion')
    ),
    CONSTRAINT chk_outreach_method CHECK (
        contact_method IS NULL OR
        contact_method IN ('Email', 'Phone', 'In-Person', 'Video Call', 'Conference', 'Other')
    )
);

CREATE INDEX idx_outreach_event_contact ON outreach_event(contact_id);
CREATE INDEX idx_outreach_event_program ON outreach_event(program_id);
CREATE INDEX idx_outreach_event_semester ON outreach_event(semester_id);
CREATE INDEX idx_outreach_event_type ON outreach_event(event_type);
CREATE INDEX idx_outreach_event_date ON outreach_event(event_date);
CREATE INDEX idx_outreach_event_staff ON outreach_event(s4g_staff_id);


-- ============================================================================
-- SECTION 3: PRIVACY & SECURITY MODEL
-- ============================================================================

-- Create application roles
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'impact_admin') THEN
        CREATE ROLE impact_admin;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'impact_staff') THEN
        CREATE ROLE impact_staff;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'impact_student_team') THEN
        CREATE ROLE impact_student_team;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'impact_reporting') THEN
        CREATE ROLE impact_reporting;
    END IF;
END
$$;

-- Grant base permissions to staff
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO impact_admin;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO impact_admin;

GRANT SELECT, INSERT, UPDATE ON partnership, project, student_registration, weekly_hours, deliverable, outreach_event TO impact_staff;
GRANT SELECT ON semester, university, program, course, project_type, s4g_staff, outreach_contact TO impact_staff;
GRANT SELECT ON student_pii TO impact_staff;  -- Staff can see PII
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO impact_staff;

-- Student team: NO access to PII
GRANT SELECT ON semester, university, program, course, project_type, partnership, project TO impact_student_team;
-- They'll use views for de-identified data

-- Reporting viewers: read-only, no PII
GRANT SELECT ON semester, university, program, course, project_type, partnership, project, s4g_staff TO impact_reporting;


-- ============================================================================
-- SECTION 4: REPORTING VIEWS
-- ============================================================================

-- View: De-identified student registrations (for student team / reporting)
CREATE OR REPLACE VIEW v_student_registrations_anon AS
SELECT 
    sr.id AS registration_id,
    sr.project_id,
    p.name AS project_name,
    pt.name AS project_type,
    part.id AS partnership_id,
    prog.name AS program_name,
    u.name AS university_name,
    sem.name AS semester,
    sr.status AS registration_status,
    sr.attended_orientation,
    sr.completed_deliverables,
    COALESCE(SUM(wh.hours_worked), 0) AS total_hours,
    -- Anonymized student info
    'Student ' || sr.id AS student_label,  -- No real name
    sp.year_in_school,
    sp.major
FROM student_registration sr
JOIN student_pii sp ON sr.student_id = sp.id
JOIN project p ON sr.project_id = p.id
LEFT JOIN project_type pt ON p.project_type_id = pt.id
JOIN partnership part ON p.partnership_id = part.id
JOIN program prog ON part.program_id = prog.id
JOIN university u ON prog.university_id = u.id
JOIN semester sem ON part.semester_id = sem.id
LEFT JOIN weekly_hours wh ON sr.id = wh.registration_id
GROUP BY sr.id, sr.project_id, p.name, pt.name, part.id, prog.name, 
         u.name, sem.name, sr.status, sr.attended_orientation, 
         sr.completed_deliverables, sp.year_in_school, sp.major;

GRANT SELECT ON v_student_registrations_anon TO impact_student_team, impact_reporting;

-- View: Current semester activity
CREATE OR REPLACE VIEW v_current_semester_activity AS
SELECT 
    u.name AS university,
    prog.name AS program,
    prog.program_type,
    c.course_code,
    c.course_name,
    part.status,
    part.students_participating,
    part.total_in_class,
    CASE 
        WHEN part.total_in_class > 0 
        THEN ROUND(100.0 * part.students_participating / part.total_in_class, 1)
        ELSE 0 
    END AS participation_rate,
    staff.name AS s4g_staff,
    part.notes,
    part.next_steps,
    sem.name AS semester
FROM partnership part
JOIN semester sem ON part.semester_id = sem.id AND sem.is_current = TRUE
JOIN program prog ON part.program_id = prog.id
JOIN university u ON prog.university_id = u.id
LEFT JOIN course c ON part.course_id = c.id
LEFT JOIN s4g_staff staff ON prog.s4g_staff_id = staff.id
ORDER BY u.name, prog.name;

GRANT SELECT ON v_current_semester_activity TO impact_staff, impact_reporting;

-- View: Student hours totals by project
CREATE OR REPLACE VIEW v_student_hours_totals AS
SELECT 
    sem.name AS semester,
    u.name AS university,
    prog.name AS program,
    p.name AS project_name,
    pt.name AS project_type,
    COUNT(DISTINCT sr.id) AS student_count,
    COALESCE(SUM(wh.hours_worked), 0) AS total_hours,
    COALESCE(AVG(wh.hours_worked), 0) AS avg_hours_per_entry,
    COALESCE(SUM(wh.hours_worked) / NULLIF(COUNT(DISTINCT sr.id), 0), 0) AS avg_hours_per_student
FROM project p
JOIN partnership part ON p.partnership_id = part.id
JOIN semester sem ON part.semester_id = sem.id
JOIN program prog ON part.program_id = prog.id
JOIN university u ON prog.university_id = u.id
LEFT JOIN project_type pt ON p.project_type_id = pt.id
LEFT JOIN student_registration sr ON p.id = sr.project_id
LEFT JOIN weekly_hours wh ON sr.id = wh.registration_id
GROUP BY sem.name, u.name, prog.name, p.name, pt.name
ORDER BY sem.name DESC, total_hours DESC;

GRANT SELECT ON v_student_hours_totals TO impact_staff, impact_reporting;

-- View: Partnership history (to find programs not active recently)
CREATE OR REPLACE VIEW v_partnership_history AS
SELECT 
    u.name AS university,
    prog.name AS program,
    prog.program_type,
    STRING_AGG(DISTINCT sem.name, ', ' ORDER BY sem.name) AS active_semesters,
    COUNT(DISTINCT sem.id) AS semester_count,
    MAX(sem.start_date) AS last_active_date,
    MAX(sem.name) AS last_active_semester,
    CASE 
        WHEN MAX(sem.is_current::int) = 1 THEN 'Active'
        ELSE 'Inactive'
    END AS current_status
FROM program prog
JOIN university u ON prog.university_id = u.id
LEFT JOIN partnership part ON prog.id = part.program_id
LEFT JOIN semester sem ON part.semester_id = sem.id
GROUP BY u.name, prog.name, prog.program_type
ORDER BY last_active_date DESC NULLS LAST;

GRANT SELECT ON v_partnership_history TO impact_staff, impact_reporting;

-- View: Outreach funnel metrics
CREATE OR REPLACE VIEW v_outreach_funnel AS
SELECT 
    sem.name AS semester,
    u.name AS university,
    prog.name AS program,
    staff.name AS s4g_staff,
    COUNT(*) FILTER (WHERE oe.event_type = 'touchpoint') AS touchpoints,
    COUNT(*) FILTER (WHERE oe.event_type = 'engagement') AS engagements,
    COUNT(*) FILTER (WHERE oe.event_type = 'conversion') AS conversions,
    MAX(oe.event_date) AS last_contact_date
FROM outreach_event oe
LEFT JOIN semester sem ON oe.semester_id = sem.id
LEFT JOIN program prog ON oe.program_id = prog.id
LEFT JOIN university u ON prog.university_id = u.id
LEFT JOIN s4g_staff staff ON oe.s4g_staff_id = staff.id
GROUP BY sem.name, u.name, prog.name, staff.name
ORDER BY sem.name DESC, u.name;

GRANT SELECT ON v_outreach_funnel TO impact_staff, impact_reporting;


-- ============================================================================
-- SECTION 5: DATA QUALITY CONSTRAINTS & TRIGGERS
-- ============================================================================

-- Trigger: Only one current semester at a time
CREATE OR REPLACE FUNCTION fn_ensure_single_current_semester()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.is_current = TRUE THEN
        UPDATE semester SET is_current = FALSE WHERE id != NEW.id AND is_current = TRUE;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_single_current_semester ON semester;
CREATE TRIGGER trg_single_current_semester
    BEFORE INSERT OR UPDATE ON semester
    FOR EACH ROW
    WHEN (NEW.is_current = TRUE)
    EXECUTE FUNCTION fn_ensure_single_current_semester();

-- Trigger: Auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION fn_update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply to all tables with updated_at
DO $$
DECLARE
    t TEXT;
BEGIN
    FOR t IN 
        SELECT table_name 
        FROM information_schema.columns 
        WHERE column_name = 'updated_at' 
        AND table_schema = 'public'
    LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS trg_update_timestamp ON %I', t);
        EXECUTE format('CREATE TRIGGER trg_update_timestamp BEFORE UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION fn_update_timestamp()', t);
    END LOOP;
END
$$;

-- Trigger: Validate project dates within semester
CREATE OR REPLACE FUNCTION fn_validate_project_dates()
RETURNS TRIGGER AS $$
DECLARE
    sem_start DATE;
    sem_end DATE;
BEGIN
    -- Get semester dates from partnership
    SELECT s.start_date, s.end_date INTO sem_start, sem_end
    FROM partnership p
    JOIN semester s ON p.semester_id = s.id
    WHERE p.id = NEW.partnership_id;
    
    -- Warn if project dates don't overlap with semester (allow some flexibility)
    -- This is a soft validation - just log a notice, don't block
    IF NEW.start_date IS NOT NULL AND NEW.end_date IS NOT NULL THEN
        IF NEW.end_date < sem_start OR NEW.start_date > sem_end THEN
            RAISE NOTICE 'Project dates (% to %) are outside semester range (% to %)', 
                NEW.start_date, NEW.end_date, sem_start, sem_end;
        END IF;
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_validate_project_dates ON project;
CREATE TRIGGER trg_validate_project_dates
    BEFORE INSERT OR UPDATE ON project
    FOR EACH ROW
    EXECUTE FUNCTION fn_validate_project_dates();

-- Trigger: Recalculate students_participating on registration changes
CREATE OR REPLACE FUNCTION fn_update_partnership_counts()
RETURNS TRIGGER AS $$
DECLARE
    part_id INTEGER;
    new_count INTEGER;
BEGIN
    -- Get partnership_id from project
    IF TG_OP = 'DELETE' THEN
        SELECT p.partnership_id INTO part_id FROM project p WHERE p.id = OLD.project_id;
    ELSE
        SELECT p.partnership_id INTO part_id FROM project p WHERE p.id = NEW.project_id;
    END IF;
    
    -- Count active registrations for this partnership
    SELECT COUNT(DISTINCT sr.student_id) INTO new_count
    FROM student_registration sr
    JOIN project p ON sr.project_id = p.id
    WHERE p.partnership_id = part_id
    AND sr.status = 'Active';
    
    -- Update partnership
    UPDATE partnership SET students_participating = new_count WHERE id = part_id;
    
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_update_partnership_counts ON student_registration;
CREATE TRIGGER trg_update_partnership_counts
    AFTER INSERT OR UPDATE OR DELETE ON student_registration
    FOR EACH ROW
    EXECUTE FUNCTION fn_update_partnership_counts();


-- ============================================================================
-- SECTION 6: SEED DATA
-- ============================================================================

-- Clear existing seed data (if re-running)
TRUNCATE TABLE weekly_hours, deliverable, student_registration, student_pii,
               outreach_event, outreach_contact, project, partnership, course, 
               program, university, s4g_staff, project_type, semester CASCADE;

-- Reset sequences
ALTER SEQUENCE semester_id_seq RESTART WITH 1;
ALTER SEQUENCE s4g_staff_id_seq RESTART WITH 1;
ALTER SEQUENCE university_id_seq RESTART WITH 1;
ALTER SEQUENCE program_id_seq RESTART WITH 1;
ALTER SEQUENCE course_id_seq RESTART WITH 1;
ALTER SEQUENCE partnership_id_seq RESTART WITH 1;
ALTER SEQUENCE project_id_seq RESTART WITH 1;
ALTER SEQUENCE project_type_id_seq RESTART WITH 1;
ALTER SEQUENCE student_pii_id_seq RESTART WITH 1;
ALTER SEQUENCE student_registration_id_seq RESTART WITH 1;
ALTER SEQUENCE weekly_hours_id_seq RESTART WITH 1;
ALTER SEQUENCE deliverable_id_seq RESTART WITH 1;
ALTER SEQUENCE outreach_contact_id_seq RESTART WITH 1;
ALTER SEQUENCE outreach_event_id_seq RESTART WITH 1;

-- Semesters (3 semesters)
INSERT INTO semester (name, academic_year, start_date, end_date, is_current) VALUES
('Fall 2024', '2024-2025', '2024-08-26', '2024-12-13', FALSE),
('Spring 2025', '2024-2025', '2025-01-13', '2025-05-09', FALSE),
('Fall 2025', '2025-2026', '2025-08-25', '2025-12-12', TRUE);

-- S4G Staff
INSERT INTO s4g_staff (name, email, role) VALUES
('Lucy Whitney', 'lucy@switch4good.org', 'Program Coordinator'),
('Gianna Klein', 'gianna@switch4good.org', 'Outreach Director'),
('Marcus Chen', 'marcus@switch4good.org', 'Data Analyst');

-- Universities (2)
INSERT INTO university (name, abbreviation, city, state, partnership_start_date, primary_contact_name, primary_contact_email) VALUES
('University of California, Los Angeles', 'UCLA', 'Los Angeles', 'California', '2023-01-15', 'Dr. Patricia Nguyen', 'pnguyen@ucla.edu'),
('Arizona State University', 'ASU', 'Tempe', 'Arizona', '2024-08-01', 'Prof. Robert Martinez', 'rmartinez@asu.edu');

-- Project Types
INSERT INTO project_type (name, description) VALUES
('Research', 'Academic research projects on plant-based topics'),
('Social Media', 'Content creation and social media campaigns'),
('Community Outreach', 'Direct community engagement and education'),
('Data Analysis', 'Data collection, cleaning, and analysis projects'),
('Event Planning', 'Planning and executing awareness events');

-- Programs
INSERT INTO program (university_id, s4g_staff_id, name, program_type, department, description) VALUES
(1, 1, 'Sustainability Studies Service Learning', 'Service Learning', 'Institute of Environment and Sustainability', 'Service learning program focused on food systems sustainability'),
(1, 2, 'Public Health Internship Program', 'Internship', 'School of Public Health', 'Internships exploring plant-based nutrition and public health'),
(2, 1, 'Community Engagement Fellows', 'Fellowship', 'School for the Future of Innovation in Society', 'Fellowship program for community-based food justice work'),
(2, 2, 'Nutrition Science Research', 'Research', 'College of Health Solutions', 'Research collaborations on dairy alternatives');

-- Courses
INSERT INTO course (program_id, course_code, course_name, faculty_names, schedule, description, includes_dairy_content, dairy_content_added_date, dairy_content_notes) VALUES
(1, 'ENV 180', 'Food Systems and Sustainability', 'Dr. Patricia Nguyen, Dr. James Lee', 'Mon/Wed 2:00-3:30pm', 'Examines global food systems through environmental lens', TRUE, '2024-09-15', 'Added module on dairy industry environmental impact after S4G partnership'),
(1, 'ENV 195', 'Service Learning Practicum', 'Dr. Patricia Nguyen', 'Fri 10:00am-12:00pm', 'Hands-on service learning experience', FALSE, NULL, NULL),
(2, 'PH 250', 'Nutrition and Public Health', 'Dr. Maria Santos', 'Tue/Thu 1:00-2:30pm', 'Public health approaches to nutrition policy', TRUE, '2025-01-20', 'Incorporated plant-based nutrition section after engagement'),
(3, 'SOC 394', 'Community-Based Research Methods', 'Prof. Robert Martinez', 'Wed 3:00-5:30pm', 'Research methods for community engagement', FALSE, NULL, NULL),
(4, 'NUT 401', 'Advanced Nutrition Science', 'Dr. Sarah Kim', 'Mon/Wed/Fri 11:00am-12:00pm', 'Advanced topics in nutritional biochemistry', FALSE, NULL, NULL);

-- Partnerships
-- Fall 2024: Both universities active
INSERT INTO partnership (program_id, semester_id, course_id, students_participating, total_in_class, status, notes) VALUES
(1, 1, 1, 12, 28, 'Completed', 'Strong first semester partnership with UCLA'),
(3, 1, 4, 8, 15, 'Completed', 'Good engagement from ASU students');

-- Spring 2025: UCLA active, ASU program 3 went quiet (no partnership record = inactive)
INSERT INTO partnership (program_id, semester_id, course_id, students_participating, total_in_class, status, notes) VALUES
(1, 2, 1, 15, 30, 'Completed', 'Expanded from Fall, great student projects'),
(2, 2, 3, 6, 20, 'Completed', 'New internship pilot program'),
(4, 2, 5, 4, 12, 'Concerning', 'Low engagement, need follow-up');
-- Note: ASU Community Engagement Fellows (program 3) NOT in Spring 2025 = "went quiet"

-- Fall 2025 (current): Both active again
INSERT INTO partnership (program_id, semester_id, course_id, students_participating, total_in_class, status, notes, next_steps) VALUES
(1, 3, 1, 18, 32, 'On Track', 'Largest cohort yet', 'Schedule mid-semester check-in'),
(2, 3, 3, 10, 25, 'On Track', 'Growing interest in internship track', 'Plan end-of-semester showcase'),
(3, 3, 4, 6, 18, 'On Track', 'Reactivated after Spring hiatus', 'Rebuild faculty relationship'),
(4, 3, 5, 5, 15, 'On Track', 'Improved from last semester', 'Monthly check-ins with Dr. Kim');

-- Projects
INSERT INTO project (partnership_id, project_type_id, name, description, start_date, end_date, deliverable_description) VALUES
-- Fall 2024
(1, 1, 'Dairy Environmental Impact Study', 'Research project analyzing local dairy farm environmental data', '2024-09-02', '2024-12-06', 'Complete research paper with data analysis'),
(1, 2, 'Campus Awareness Campaign', 'Social media campaign for plant-based options', '2024-09-09', '2024-11-22', '10 posts with 500+ total engagement'),
(2, 3, 'Community Food Access Survey', 'Survey local community about food access barriers', '2024-09-15', '2024-12-01', 'Survey report with 100+ responses'),
-- Spring 2025
(3, 1, 'Plant-Based Nutrition Meta-Analysis', 'Literature review of plant-based diet benefits', '2025-01-20', '2025-04-25', 'Published meta-analysis paper'),
(3, 4, 'Student Dining Data Analysis', 'Analyze dining hall plant-based option usage', '2025-02-01', '2025-05-02', 'Dashboard with usage trends'),
(4, 2, 'Social Media Internship', 'Create content for S4G social channels', '2025-01-27', '2025-05-05', '20 posts across platforms'),
(5, 1, 'Dairy Alternative Research', 'Lab research on dairy alternatives', '2025-02-03', '2025-04-28', 'Research findings presentation'),
-- Fall 2025 (current)
(6, 1, 'Food Systems Research Project', 'Comprehensive food systems analysis', '2025-09-01', '2025-12-05', 'Research paper and presentation'),
(6, 3, 'Campus Outreach Initiative', 'Direct student outreach and education', '2025-09-08', '2025-11-21', 'Reach 500 students'),
(7, 2, 'Plant-Based Promotion Campaign', 'Marketing campaign for dining plant-based options', '2025-09-15', '2025-12-01', 'Campaign strategy and execution'),
(8, 3, 'Community Health Workshop Series', 'Monthly workshops on plant-based cooking', '2025-09-22', '2025-11-30', 'Host 3 workshops with 30+ attendees each'),
(9, 4, 'Nutrition Data Dashboard', 'Build interactive nutrition data tool', '2025-09-08', '2025-12-08', 'Deployed dashboard application');

-- Students (10+)
INSERT INTO student_pii (first_name, last_name, email, pronouns, tshirt_size, year_in_school, major, areas_of_interest) VALUES
('Alex', 'Johnson', 'alex.johnson@ucla.edu', 'they/them', 'M', 'Junior', 'Environmental Science', 'Data analysis, sustainability research'),
('Samantha', 'Williams', 'sam.williams@ucla.edu', 'she/her', 'S', 'Senior', 'Public Health', 'Nutrition policy, community health'),
('Jordan', 'Davis', 'jordan.davis@asu.edu', 'he/him', 'L', 'Senior', 'Sociology', 'Community organizing, food justice'),
('Emily', 'Chen', 'emily.chen@ucla.edu', 'she/her', 'M', 'Graduate', 'Nutrition Science', 'Plant-based diets, biochemistry'),
('Marcus', 'Brown', 'marcus.brown@ucla.edu', 'he/him', 'XL', 'Junior', 'Communications', 'Social media, digital marketing'),
('Priya', 'Patel', 'priya.patel@asu.edu', 'she/her', 'S', 'Sophomore', 'Health Sciences', 'Public health, data visualization'),
('Kevin', 'Lee', 'kevin.lee@ucla.edu', 'he/him', 'M', 'Senior', 'Statistics', 'Data science, machine learning'),
('Sofia', 'Rodriguez', 'sofia.rodriguez@asu.edu', 'she/her', 'M', 'Junior', 'Environmental Studies', 'Climate change, agriculture'),
('David', 'Kim', 'david.kim@ucla.edu', 'he/him', 'L', 'Junior', 'Biology', 'Nutrition, research'),
('Aisha', 'Mohammed', 'aisha.mohammed@asu.edu', 'she/her', 'S', 'Senior', 'Public Policy', 'Food policy, advocacy'),
('Ryan', 'Thompson', 'ryan.thompson@ucla.edu', 'he/him', 'M', 'Sophomore', 'Marketing', 'Brand strategy, content creation'),
('Jessica', 'Garcia', 'jessica.garcia@ucla.edu', 'she/her', 'S', 'Graduate', 'Environmental Health', 'Research methods, data analysis');

-- Student Registrations
INSERT INTO student_registration (student_id, project_id, s4g_staff_id, registration_date, success_metric, attended_orientation, sent_headshot, completed_deliverables, status) VALUES
-- Fall 2024 registrations
(1, 1, 1, '2024-08-28', 'Complete analysis section of research paper', TRUE, TRUE, TRUE, 'Completed'),
(2, 1, 1, '2024-08-28', 'Lead literature review section', TRUE, TRUE, TRUE, 'Completed'),
(5, 2, 2, '2024-09-05', 'Create 5 Instagram posts', TRUE, TRUE, TRUE, 'Completed'),
(3, 3, 1, '2024-09-10', 'Collect 50 survey responses', TRUE, FALSE, TRUE, 'Completed'),
-- Spring 2025 registrations
(1, 4, 1, '2025-01-15', 'Meta-analysis methodology section', TRUE, TRUE, TRUE, 'Completed'),
(4, 4, 1, '2025-01-15', 'Results and discussion sections', TRUE, TRUE, TRUE, 'Completed'),
(7, 5, 1, '2025-01-25', 'Build data visualization dashboard', TRUE, TRUE, TRUE, 'Completed'),
(5, 6, 2, '2025-01-22', 'Manage Instagram account', TRUE, TRUE, TRUE, 'Completed'),
(11, 6, 2, '2025-01-22', 'Create TikTok content', TRUE, FALSE, TRUE, 'Completed'),
(4, 7, 1, '2025-02-01', 'Lab analysis of oat milk proteins', TRUE, TRUE, FALSE, 'Incomplete'),
-- Fall 2025 registrations (current - still active)
(1, 8, 1, '2025-08-26', 'Lead research methodology', TRUE, TRUE, FALSE, 'Active'),
(2, 8, 1, '2025-08-26', 'Policy analysis section', TRUE, TRUE, FALSE, 'Active'),
(12, 8, 1, '2025-08-26', 'Data collection and analysis', TRUE, FALSE, FALSE, 'Active'),
(5, 9, 2, '2025-09-02', 'Tabling events coordinator', TRUE, TRUE, FALSE, 'Active'),
(11, 10, 2, '2025-09-08', 'Lead campaign strategy', TRUE, TRUE, FALSE, 'Active'),
(6, 11, 1, '2025-09-15', 'Workshop planning and facilitation', TRUE, FALSE, FALSE, 'Active'),
(8, 11, 1, '2025-09-15', 'Community outreach coordination', TRUE, TRUE, FALSE, 'Active'),
(10, 11, 1, '2025-09-15', 'Policy brief on food access', TRUE, TRUE, FALSE, 'Active'),
(7, 12, 1, '2025-09-05', 'Full stack development', TRUE, TRUE, FALSE, 'Active'),
(9, 12, 1, '2025-09-05', 'Data pipeline design', TRUE, FALSE, FALSE, 'Active');

-- Weekly Hours (multiple entries per student)
-- Fall 2024 hours (completed projects)
INSERT INTO weekly_hours (registration_id, week_start_date, hours_worked, checkin_type, notes) VALUES
(1, '2024-09-02', 5.5, 'survey', 'Started data collection'),
(1, '2024-09-09', 6.0, 'survey', 'Data cleaning'),
(1, '2024-09-16', 7.5, 'survey', 'Analysis phase'),
(1, '2024-09-23', 8.0, 'meeting', 'Presented preliminary findings'),
(1, '2024-09-30', 6.5, 'survey', 'Writing draft'),
(1, '2024-10-07', 7.0, 'survey', 'Revisions'),
(1, '2024-10-14', 5.0, 'survey', 'Final edits'),
(2, '2024-09-02', 4.0, 'survey', 'Literature search'),
(2, '2024-09-09', 5.5, 'survey', 'Reading papers'),
(2, '2024-09-16', 6.0, 'survey', 'Synthesizing findings'),
(2, '2024-09-23', 7.0, 'meeting', 'Draft review'),
(2, '2024-09-30', 5.5, 'survey', 'Revisions'),
(3, '2024-09-09', 3.5, 'survey', 'Content planning'),
(3, '2024-09-16', 4.0, 'survey', 'Created 2 posts'),
(3, '2024-09-23', 4.5, 'survey', 'Created 2 posts'),
(3, '2024-09-30', 3.0, 'survey', 'Final post and analytics'),
(4, '2024-09-16', 5.0, 'survey', 'Survey design'),
(4, '2024-09-23', 6.5, 'survey', 'Collecting responses'),
(4, '2024-09-30', 7.0, 'survey', 'More responses'),
(4, '2024-10-07', 6.0, 'survey', 'Analysis'),
(4, '2024-10-14', 5.5, 'meeting', 'Final report');

-- Spring 2025 hours
INSERT INTO weekly_hours (registration_id, week_start_date, hours_worked, checkin_type, notes) VALUES
(5, '2025-01-20', 6.0, 'survey', 'Methods development'),
(5, '2025-01-27', 7.5, 'survey', 'Paper screening'),
(5, '2025-02-03', 8.0, 'survey', 'Data extraction'),
(5, '2025-02-10', 6.5, 'meeting', 'Analysis'),
(5, '2025-02-17', 7.0, 'survey', 'Writing'),
(6, '2025-01-20', 5.0, 'survey', 'Literature review'),
(6, '2025-01-27', 6.0, 'survey', 'Data synthesis'),
(6, '2025-02-03', 7.5, 'survey', 'Writing results'),
(6, '2025-02-10', 8.0, 'meeting', 'Revisions'),
(7, '2025-01-27', 8.0, 'survey', 'Dashboard design'),
(7, '2025-02-03', 10.0, 'survey', 'Development'),
(7, '2025-02-10', 9.5, 'survey', 'Testing'),
(7, '2025-02-17', 7.0, 'meeting', 'Deployment'),
(8, '2025-01-27', 4.0, 'survey', 'Content calendar'),
(8, '2025-02-03', 5.0, 'survey', 'Creating posts'),
(8, '2025-02-10', 4.5, 'survey', 'Engagement tracking'),
(9, '2025-01-27', 3.5, 'survey', 'Video planning'),
(9, '2025-02-03', 4.0, 'survey', 'Filming'),
(9, '2025-02-10', 5.0, 'survey', 'Editing'),
(10, '2025-02-03', 6.0, 'survey', 'Lab work'),
(10, '2025-02-10', 7.5, 'survey', 'Analysis');

-- Fall 2025 hours (current semester - still accumulating)
INSERT INTO weekly_hours (registration_id, week_start_date, hours_worked, checkin_type, notes) VALUES
(11, '2025-09-01', 5.0, 'survey', 'Project kickoff'),
(11, '2025-09-08', 6.5, 'survey', 'Research planning'),
(11, '2025-09-15', 7.0, 'meeting', 'Data collection started'),
(11, '2025-09-22', 6.0, 'survey', 'Continued data collection'),
(12, '2025-09-01', 4.5, 'survey', 'Policy review'),
(12, '2025-09-08', 5.5, 'survey', 'Framework development'),
(12, '2025-09-15', 6.0, 'survey', 'Writing'),
(12, '2025-09-22', 5.0, 'meeting', 'Team sync'),
(13, '2025-09-01', 5.0, 'survey', 'Setup'),
(13, '2025-09-08', 7.0, 'survey', 'Data processing'),
(13, '2025-09-15', 8.0, 'survey', 'Analysis'),
(14, '2025-09-08', 4.0, 'survey', 'Event planning'),
(14, '2025-09-15', 6.0, 'survey', 'First tabling event'),
(14, '2025-09-22', 5.5, 'meeting', 'Debrief'),
(15, '2025-09-15', 5.0, 'survey', 'Campaign strategy'),
(15, '2025-09-22', 6.5, 'survey', 'Content creation'),
(16, '2025-09-22', 4.0, 'survey', 'Workshop prep'),
(17, '2025-09-22', 5.0, 'survey', 'Outreach calls'),
(18, '2025-09-22', 6.0, 'survey', 'Policy research'),
(19, '2025-09-08', 8.0, 'survey', 'Architecture design'),
(19, '2025-09-15', 10.0, 'survey', 'Frontend development'),
(19, '2025-09-22', 9.0, 'meeting', 'Backend integration'),
(20, '2025-09-08', 6.0, 'survey', 'Data modeling'),
(20, '2025-09-15', 7.5, 'survey', 'ETL pipeline'),
(20, '2025-09-22', 8.0, 'survey', 'Testing');

-- Deliverables
INSERT INTO deliverable (registration_id, name, description, due_date, submitted_date, is_completed, feedback) VALUES
(1, 'Data Analysis Section', 'Complete analysis of environmental data', '2024-11-15', '2024-11-10', TRUE, 'Excellent work on the statistical analysis'),
(2, 'Literature Review', 'Comprehensive lit review on dairy impacts', '2024-11-01', '2024-10-28', TRUE, 'Well-researched and thorough'),
(3, 'Social Media Posts', 'Create 5 engaging Instagram posts', '2024-11-15', '2024-11-12', TRUE, 'Great engagement rates!'),
(7, 'Data Dashboard', 'Interactive Tableau dashboard', '2025-03-15', '2025-03-10', TRUE, 'Beautiful visualizations'),
(11, 'Research Paper Draft', 'First draft of methodology section', '2025-10-15', NULL, FALSE, NULL),
(19, 'Dashboard MVP', 'Minimum viable product deployment', '2025-11-01', NULL, FALSE, NULL);

-- Outreach Contacts
INSERT INTO outreach_contact (university_id, name, email, role, department, preferred_contact_method) VALUES
(1, 'Dr. Sarah Mitchell', 'smitchell@ucla.edu', 'Department Chair', 'Environmental Science', 'Email'),
(1, 'Prof. James Wong', 'jwong@ucla.edu', 'Faculty Advisor', 'Public Health', 'Video Call'),
(2, 'Dr. Lisa Chen', 'lchen@asu.edu', 'Program Director', 'School of Sustainability', 'Phone'),
(2, 'Mark Thompson', 'mthompson@asu.edu', 'Community Partnerships', 'Office of Community Engagement', 'Email'),
(NULL, 'Dr. Amanda Foster', 'afoster@stanford.edu', 'Faculty', 'School of Medicine', 'Email');  -- Prospective

-- Outreach Events
INSERT INTO outreach_event (contact_id, program_id, semester_id, s4g_staff_id, event_type, event_date, contact_method, subject, notes, outcome) VALUES
-- UCLA touchpoints leading to engagement and conversion
(1, 1, 1, 2, 'touchpoint', '2024-07-15', 'Email', 'Introduction to S4G', 'Initial outreach to Dr. Mitchell', 'Interested in learning more'),
(1, 1, 1, 2, 'engagement', '2024-07-28', 'Video Call', 'Program Overview Call', 'Discussed service learning opportunities', 'Agreed to pilot in Fall'),
(1, 1, 1, 2, 'conversion', '2024-08-10', 'In-Person', 'Partnership Agreement', 'Signed MOU for Fall 2024', 'Partnership established'),
(2, 2, 2, 2, 'touchpoint', '2024-11-01', 'Email', 'Internship Program Inquiry', 'Reached out about internship track', 'Responded positively'),
(2, 2, 2, 2, 'engagement', '2024-11-20', 'Video Call', 'Program Planning', 'Designed internship structure', 'Moving forward'),
(2, 2, 2, 2, 'conversion', '2024-12-15', 'Email', 'Internship Launch Confirmed', 'Prof. Wong committed 6 students', 'Launch in Spring'),
-- ASU outreach
(3, 3, 1, 1, 'touchpoint', '2024-06-01', 'Email', 'Partnership Inquiry', 'Cold outreach', 'Initial interest'),
(3, 3, 1, 1, 'engagement', '2024-06-20', 'Phone', 'Discussion', 'Talked about fellowship program', 'Positive response'),
(3, 3, 1, 1, 'conversion', '2024-07-15', 'In-Person', 'Agreement', 'Formalized partnership', 'Students recruited'),
(4, 4, 2, 1, 'touchpoint', '2024-10-05', 'Email', 'Research Collaboration', 'Reached out about nutrition research', 'Interested'),
(4, 4, 2, 1, 'engagement', '2025-01-10', 'Video Call', 'Research Planning', 'Discussed project scope', 'Agreed to proceed'),
(4, 4, 2, 1, 'conversion', '2025-01-25', 'Email', 'Research Launch', 'Students assigned', 'Active'),
-- Prospective (touchpoints only, not converted)
(5, NULL, 3, 2, 'touchpoint', '2025-08-01', 'Email', 'Introduction', 'Exploring Stanford partnership', 'Waiting for response'),
(5, NULL, 3, 2, 'touchpoint', '2025-09-05', 'Email', 'Follow-up', 'Second outreach attempt', 'Brief response, busy this semester');


-- ============================================================================
-- SECTION 7: SAMPLE QUERIES (5 Key Reporting Questions)
-- ============================================================================

-- NOTE: These are EXAMPLE queries to run manually. They are commented out.
-- Copy and execute them in pgAdmin or psql as needed.

/*
============================================================================
QUERY 1: Programs active previously but NOT in most recent semester
============================================================================

-- This finds "partnerships that went quiet"
WITH current_sem AS (
    SELECT id FROM semester WHERE is_current = TRUE
),
active_programs AS (
    SELECT DISTINCT program_id 
    FROM partnership 
    WHERE semester_id = (SELECT id FROM current_sem)
)
SELECT 
    u.name AS university,
    p.name AS program,
    p.program_type,
    MAX(s.name) AS last_active_semester,
    MAX(s.end_date) AS last_active_date
FROM program p
JOIN university u ON p.university_id = u.id
JOIN partnership part ON p.id = part.program_id
JOIN semester s ON part.semester_id = s.id
WHERE p.id NOT IN (SELECT program_id FROM active_programs)
  AND p.is_active = TRUE
GROUP BY u.name, p.name, p.program_type
ORDER BY last_active_date DESC;


============================================================================
QUERY 2: Courses that now include dairy content due to partnership
============================================================================

SELECT 
    u.name AS university,
    p.name AS program,
    c.course_code,
    c.course_name,
    c.dairy_content_added_date,
    c.dairy_content_notes
FROM course c
JOIN program p ON c.program_id = p.id
JOIN university u ON p.university_id = u.id
WHERE c.includes_dairy_content = TRUE
  AND c.dairy_content_added_date IS NOT NULL
ORDER BY c.dairy_content_added_date;


============================================================================
QUERY 3: Students by program, school, and project type (with ROLLUP)
============================================================================

SELECT 
    COALESCE(u.name, '** ALL UNIVERSITIES **') AS university,
    COALESCE(prog.name, '** ALL PROGRAMS **') AS program,
    COALESCE(pt.name, '** ALL PROJECT TYPES **') AS project_type,
    COUNT(DISTINCT sr.student_id) AS unique_students,
    COUNT(DISTINCT sr.id) AS total_registrations,
    COALESCE(SUM(wh.hours_worked), 0) AS total_hours
FROM student_registration sr
JOIN project p ON sr.project_id = p.id
LEFT JOIN project_type pt ON p.project_type_id = pt.id
JOIN partnership part ON p.partnership_id = part.id
JOIN program prog ON part.program_id = prog.id
JOIN university u ON prog.university_id = u.id
LEFT JOIN weekly_hours wh ON sr.id = wh.registration_id
GROUP BY ROLLUP (u.name, prog.name, pt.name)
ORDER BY 
    GROUPING(u.name), u.name,
    GROUPING(prog.name), prog.name,
    GROUPING(pt.name), pt.name;


============================================================================
QUERY 4: Average registrations per project over semesters (trend)
============================================================================

SELECT 
    s.name AS semester,
    s.start_date,
    COUNT(DISTINCT p.id) AS total_projects,
    COUNT(DISTINCT sr.id) AS total_registrations,
    ROUND(COUNT(DISTINCT sr.id)::NUMERIC / NULLIF(COUNT(DISTINCT p.id), 0), 2) AS avg_registrations_per_project,
    COALESCE(SUM(wh.hours_worked), 0) AS total_hours,
    ROUND(COALESCE(SUM(wh.hours_worked), 0) / NULLIF(COUNT(DISTINCT sr.id), 0), 2) AS avg_hours_per_registration
FROM semester s
LEFT JOIN partnership part ON s.id = part.semester_id
LEFT JOIN project p ON part.id = p.partnership_id
LEFT JOIN student_registration sr ON p.id = sr.project_id
LEFT JOIN weekly_hours wh ON sr.id = wh.registration_id
GROUP BY s.id, s.name, s.start_date
ORDER BY s.start_date;


============================================================================
QUERY 5: Projects correlated to highest hours served
============================================================================

SELECT 
    s.name AS semester,
    u.name AS university,
    prog.name AS program,
    p.name AS project_name,
    pt.name AS project_type,
    COUNT(DISTINCT sr.id) AS student_count,
    COALESCE(SUM(wh.hours_worked), 0) AS total_hours,
    ROUND(COALESCE(AVG(wh.hours_worked), 0), 2) AS avg_hours_per_entry,
    ROUND(COALESCE(SUM(wh.hours_worked) / NULLIF(COUNT(DISTINCT sr.id), 0), 0), 2) AS avg_hours_per_student,
    RANK() OVER (ORDER BY COALESCE(SUM(wh.hours_worked), 0) DESC) AS hours_rank
FROM project p
JOIN partnership part ON p.partnership_id = part.id
JOIN semester s ON part.semester_id = s.id
JOIN program prog ON part.program_id = prog.id
JOIN university u ON prog.university_id = u.id
LEFT JOIN project_type pt ON p.project_type_id = pt.id
LEFT JOIN student_registration sr ON p.id = sr.project_id
LEFT JOIN weekly_hours wh ON sr.id = wh.registration_id
GROUP BY s.name, u.name, prog.name, p.name, pt.name
HAVING COALESCE(SUM(wh.hours_worked), 0) > 0
ORDER BY total_hours DESC
LIMIT 15;

*/


-- ============================================================================
-- SECTION 8: FUNDER DASHBOARD METRICS (12 Key Metrics)
-- ============================================================================

/*
IMPACT METRICS FOR FUNDERS
==========================

1. TOTAL ACTIVE PARTNERSHIPS (Current Semester)
   Definition: Count of unique program-semester partnerships currently active
   Chart: Single number card with trend arrow
*/
CREATE OR REPLACE VIEW v_metric_active_partnerships AS
SELECT 
    COUNT(*) AS active_partnerships,
    (SELECT COUNT(*) FROM partnership WHERE semester_id = (
        SELECT id FROM semester WHERE is_current = FALSE ORDER BY end_date DESC LIMIT 1
    )) AS previous_semester_count
FROM partnership 
WHERE semester_id = (SELECT id FROM semester WHERE is_current = TRUE);

/*
2. TOTAL STUDENTS ENGAGED (Current Semester)
   Definition: Count of unique students with active registrations
   Chart: Single number with semester comparison
*/
CREATE OR REPLACE VIEW v_metric_students_engaged AS
SELECT 
    sem.name AS semester,
    COUNT(DISTINCT sr.student_id) AS unique_students,
    COUNT(DISTINCT sr.id) AS total_registrations
FROM semester sem
JOIN partnership part ON sem.id = part.semester_id
JOIN project p ON part.id = p.partnership_id
JOIN student_registration sr ON p.id = sr.project_id
GROUP BY sem.id, sem.name
ORDER BY sem.start_date DESC;

/*
3. TOTAL SERVICE HOURS
   Definition: Sum of all weekly hours logged
   Chart: Bar chart by semester
*/
CREATE OR REPLACE VIEW v_metric_service_hours AS
SELECT 
    sem.name AS semester,
    sem.start_date,
    COALESCE(SUM(wh.hours_worked), 0) AS total_hours,
    COUNT(DISTINCT sr.student_id) AS students,
    ROUND(COALESCE(SUM(wh.hours_worked) / NULLIF(COUNT(DISTINCT sr.student_id), 0), 0), 1) AS avg_per_student
FROM semester sem
LEFT JOIN partnership part ON sem.id = part.semester_id
LEFT JOIN project p ON part.id = p.partnership_id
LEFT JOIN student_registration sr ON p.id = sr.project_id
LEFT JOIN weekly_hours wh ON sr.id = wh.registration_id
GROUP BY sem.id, sem.name, sem.start_date
ORDER BY sem.start_date;

/*
4. DELIVERABLES COMPLETION RATE
   Definition: Percentage of registrations with completed_deliverables = TRUE
   Chart: Gauge chart
*/
CREATE OR REPLACE VIEW v_metric_completion_rate AS
SELECT 
    sem.name AS semester,
    COUNT(*) AS total_registrations,
    COUNT(*) FILTER (WHERE sr.completed_deliverables = TRUE) AS completed,
    ROUND(100.0 * COUNT(*) FILTER (WHERE sr.completed_deliverables = TRUE) / NULLIF(COUNT(*), 0), 1) AS completion_rate
FROM semester sem
JOIN partnership part ON sem.id = part.semester_id
JOIN project p ON part.id = p.partnership_id
JOIN student_registration sr ON p.id = sr.project_id
GROUP BY sem.id, sem.name, sem.start_date
ORDER BY sem.start_date DESC;

/*
5. UNIVERSITY REACH
   Definition: Count of unique universities with partnerships
   Chart: Map / number card
*/
CREATE OR REPLACE VIEW v_metric_university_reach AS
SELECT 
    COUNT(DISTINCT u.id) AS total_universities,
    COUNT(DISTINCT u.state) AS states_covered,
    STRING_AGG(DISTINCT u.state, ', ' ORDER BY u.state) AS state_list
FROM university u
WHERE EXISTS (
    SELECT 1 FROM program p 
    JOIN partnership part ON p.id = part.program_id 
    WHERE p.university_id = u.id
);

/*
6. PROGRAM TYPE DISTRIBUTION
   Definition: Breakdown of partnerships by program type
   Chart: Pie/donut chart
*/
CREATE OR REPLACE VIEW v_metric_program_types AS
SELECT 
    p.program_type,
    COUNT(DISTINCT part.id) AS partnership_count,
    COUNT(DISTINCT sr.student_id) AS student_count,
    ROUND(100.0 * COUNT(DISTINCT part.id) / NULLIF(SUM(COUNT(DISTINCT part.id)) OVER (), 0), 1) AS percentage
FROM program p
JOIN partnership part ON p.id = part.program_id
LEFT JOIN project proj ON part.id = proj.partnership_id
LEFT JOIN student_registration sr ON proj.id = sr.project_id
GROUP BY p.program_type
ORDER BY partnership_count DESC;

/*
7. COURSES WITH DAIRY CONTENT IMPACT
   Definition: Count of courses that added dairy/plant-based content
   Chart: Number card with list
*/
CREATE OR REPLACE VIEW v_metric_course_impact AS
SELECT 
    COUNT(*) AS courses_with_dairy_content,
    STRING_AGG(c.course_code || ': ' || c.course_name, '; ') AS courses
FROM course c
WHERE c.includes_dairy_content = TRUE;

/*
8. OUTREACH FUNNEL (Conversion Rate)
   Definition: Touchpoints → Engagements → Conversions pipeline
   Chart: Funnel chart
*/
CREATE OR REPLACE VIEW v_metric_outreach_funnel AS
SELECT 
    sem.name AS semester,
    COUNT(*) FILTER (WHERE oe.event_type = 'touchpoint') AS touchpoints,
    COUNT(*) FILTER (WHERE oe.event_type = 'engagement') AS engagements,
    COUNT(*) FILTER (WHERE oe.event_type = 'conversion') AS conversions,
    ROUND(100.0 * COUNT(*) FILTER (WHERE oe.event_type = 'engagement') / 
          NULLIF(COUNT(*) FILTER (WHERE oe.event_type = 'touchpoint'), 0), 1) AS touchpoint_to_engagement_rate,
    ROUND(100.0 * COUNT(*) FILTER (WHERE oe.event_type = 'conversion') / 
          NULLIF(COUNT(*) FILTER (WHERE oe.event_type = 'engagement'), 0), 1) AS engagement_to_conversion_rate
FROM semester sem
LEFT JOIN outreach_event oe ON sem.id = oe.semester_id
GROUP BY sem.id, sem.name, sem.start_date
ORDER BY sem.start_date DESC;

/*
9. PROJECT TYPE PERFORMANCE
   Definition: Hours and completions by project type
   Chart: Horizontal bar chart
*/
CREATE OR REPLACE VIEW v_metric_project_performance AS
SELECT 
    pt.name AS project_type,
    COUNT(DISTINCT p.id) AS project_count,
    COUNT(DISTINCT sr.id) AS registrations,
    COALESCE(SUM(wh.hours_worked), 0) AS total_hours,
    ROUND(100.0 * COUNT(*) FILTER (WHERE sr.completed_deliverables = TRUE) / 
          NULLIF(COUNT(*), 0), 1) AS completion_rate
FROM project_type pt
LEFT JOIN project p ON pt.id = p.project_type_id
LEFT JOIN student_registration sr ON p.id = sr.project_id
LEFT JOIN weekly_hours wh ON sr.id = wh.registration_id
GROUP BY pt.id, pt.name
ORDER BY total_hours DESC;

/*
10. RETENTION METRIC (Returning Students)
    Definition: Students who participated in multiple semesters
    Chart: Number card with trend
*/
CREATE OR REPLACE VIEW v_metric_retention AS
SELECT 
    COUNT(DISTINCT sr.student_id) AS total_unique_students,
    COUNT(DISTINCT sr.student_id) FILTER (WHERE semester_count > 1) AS returning_students,
    ROUND(100.0 * COUNT(DISTINCT sr.student_id) FILTER (WHERE semester_count > 1) / 
          NULLIF(COUNT(DISTINCT sr.student_id), 0), 1) AS retention_rate
FROM (
    SELECT 
        sr.student_id,
        COUNT(DISTINCT sem.id) AS semester_count
    FROM student_registration sr
    JOIN project p ON sr.project_id = p.id
    JOIN partnership part ON p.partnership_id = part.id
    JOIN semester sem ON part.semester_id = sem.id
    GROUP BY sr.student_id
) sr;

/*
11. STAFF WORKLOAD DISTRIBUTION
    Definition: Registrations and hours by S4G staff member
    Chart: Stacked bar chart
*/
CREATE OR REPLACE VIEW v_metric_staff_workload AS
SELECT 
    s.name AS staff_name,
    COUNT(DISTINCT sr.id) AS registrations,
    COUNT(DISTINCT sr.student_id) AS students,
    COUNT(DISTINCT p.id) AS programs,
    COALESCE(SUM(wh.hours_worked), 0) AS total_hours_supervised
FROM s4g_staff s
LEFT JOIN program p ON s.id = p.s4g_staff_id
LEFT JOIN partnership part ON p.id = part.program_id
LEFT JOIN project proj ON part.id = proj.partnership_id
LEFT JOIN student_registration sr ON proj.id = sr.project_id
LEFT JOIN weekly_hours wh ON sr.id = wh.registration_id
WHERE s.is_active = TRUE
GROUP BY s.id, s.name
ORDER BY registrations DESC;

/*
12. ORIENTATION & MILESTONE TRACKING
    Definition: Progress through student milestones
    Chart: Progress bar / funnel
*/
CREATE OR REPLACE VIEW v_metric_milestones AS
SELECT 
    sem.name AS semester,
    COUNT(*) AS total_registrations,
    COUNT(*) FILTER (WHERE sr.attended_orientation = TRUE) AS oriented,
    COUNT(*) FILTER (WHERE sr.sent_headshot = TRUE) AS headshot_submitted,
    COUNT(*) FILTER (WHERE sr.completed_deliverables = TRUE) AS deliverables_complete,
    ROUND(100.0 * COUNT(*) FILTER (WHERE sr.attended_orientation = TRUE) / NULLIF(COUNT(*), 0), 1) AS orientation_rate,
    ROUND(100.0 * COUNT(*) FILTER (WHERE sr.completed_deliverables = TRUE) / NULLIF(COUNT(*), 0), 1) AS completion_rate
FROM semester sem
JOIN partnership part ON sem.id = part.semester_id
JOIN project p ON part.id = p.partnership_id
JOIN student_registration sr ON p.id = sr.project_id
GROUP BY sem.id, sem.name, sem.start_date
ORDER BY sem.start_date DESC;


-- Grant reporting views to appropriate roles
GRANT SELECT ON v_metric_active_partnerships TO impact_staff, impact_reporting;
GRANT SELECT ON v_metric_students_engaged TO impact_staff, impact_reporting;
GRANT SELECT ON v_metric_service_hours TO impact_staff, impact_reporting;
GRANT SELECT ON v_metric_completion_rate TO impact_staff, impact_reporting;
GRANT SELECT ON v_metric_university_reach TO impact_staff, impact_reporting;
GRANT SELECT ON v_metric_program_types TO impact_staff, impact_reporting;
GRANT SELECT ON v_metric_course_impact TO impact_staff, impact_reporting;
GRANT SELECT ON v_metric_outreach_funnel TO impact_staff, impact_reporting;
GRANT SELECT ON v_metric_project_performance TO impact_staff, impact_reporting;
GRANT SELECT ON v_metric_retention TO impact_staff, impact_reporting;
GRANT SELECT ON v_metric_staff_workload TO impact_staff, impact_reporting;
GRANT SELECT ON v_metric_milestones TO impact_staff, impact_reporting;


-- ============================================================================
-- END OF SCHEMA
-- ============================================================================
