-- Run this SQL in pgAdmin to create the Service Active Campus Connections database
-- Tables for tracking Service Learning Programs and Students

-- =============================================
-- TABLE 0: Admin Users (Authentication)
-- =============================================
CREATE TABLE IF NOT EXISTS admin_users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE,
    name VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL DEFAULT 'viewer',  -- 'admin', 'staff', 'viewer'
    is_active BOOLEAN DEFAULT TRUE,
    failed_login_attempts INTEGER DEFAULT 0,
    locked_until TIMESTAMP,
    last_login TIMESTAMP,
    password_changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create index for faster username lookups
CREATE INDEX IF NOT EXISTS idx_admin_users_username ON admin_users(username);
CREATE INDEX IF NOT EXISTS idx_admin_users_email ON admin_users(email);

-- =============================================
-- TABLE 1: Service Learning Programs
-- =============================================
CREATE TABLE IF NOT EXISTS service_learning_programs (
    id SERIAL PRIMARY KEY,
    semester VARCHAR(50) NOT NULL,  -- e.g., 'Spring 2025', 'Fall 2025'
    school VARCHAR(255) NOT NULL,  -- Name of university
    s4g_staff VARCHAR(255),  -- S4G staff point person
    program VARCHAR(255),  -- Program name within university
    faculty_staff TEXT,  -- University professors/administrators (comma-separated)
    ty_note_sent BOOLEAN DEFAULT FALSE,  -- Thank-you note mailed
    students_participating INTEGER DEFAULT 0,
    total_students_in_class INTEGER DEFAULT 0,
    status VARCHAR(50) DEFAULT 'On Track',  -- 'On Track', 'Concerning', 'No longer participating'
    notes TEXT,
    next_steps TEXT,
    course_details TEXT,  -- Course number, day/time, catalog description
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================
-- TABLE 2: Students
-- =============================================
CREATE TABLE IF NOT EXISTS students (
    id SERIAL PRIMARY KEY,
    semester VARCHAR(50) NOT NULL,  -- e.g., 'Spring 2025', 'Fall 2025'
    name VARCHAR(255) NOT NULL,
    s4g_staff VARCHAR(255),  -- S4G staff point person
    pronouns VARCHAR(50),
    tshirt_size VARCHAR(20),
    school_program VARCHAR(255),  -- University and program/course
    email VARCHAR(255),
    year_in_school VARCHAR(50),  -- Grade level
    areas_of_interest TEXT,  -- Major and other interests
    projects TEXT,  -- Project name(s)
    project_duration VARCHAR(100),  -- Start and end date
    conflicting_dates TEXT,  -- School breaks, exam periods
    success_metric TEXT,  -- Definition of deliverable
    date_intro_email_sent DATE,
    attended_orientation BOOLEAN DEFAULT FALSE,
    sent_headshot BOOLEAN DEFAULT FALSE,
    completed_deliverables BOOLEAN DEFAULT FALSE,
    total_hours_worked DECIMAL(10,2) DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================
-- TABLE 3: Student Check-ins (for tracking weekly surveys/meetings)
-- =============================================
CREATE TABLE IF NOT EXISTS student_checkins (
    id SERIAL PRIMARY KEY,
    student_id INTEGER REFERENCES students(id) ON DELETE CASCADE,
    checkin_date DATE NOT NULL,
    checkin_type VARCHAR(50),  -- 'survey' or 'meeting'
    hours_worked DECIMAL(5,2) DEFAULT 0,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================
-- Sample Data
-- =============================================

-- Sample Service Learning Programs
INSERT INTO service_learning_programs (semester, school, s4g_staff, program, faculty_staff, students_participating, total_students_in_class, status, notes, course_details) VALUES
('Spring 2025', 'University of Example', 'Jane Smith', 'Community Engagement 101', 'Dr. John Doe, Prof. Mary Johnson', 15, 30, 'On Track', 'Strong partnership, students engaged', 'CE101 - Mon/Wed 2:00-3:30pm - Introduction to community service learning'),
('Spring 2025', 'State College', 'Mike Wilson', 'Service Leadership Program', 'Dr. Sarah Lee', 8, 20, 'On Track', 'New partnership this semester', 'SLP200 - Tue/Thu 10:00-11:30am - Leadership through service');

-- Sample Students
INSERT INTO students (semester, name, s4g_staff, pronouns, tshirt_size, school_program, email, year_in_school, areas_of_interest, projects, project_duration, success_metric, attended_orientation, sent_headshot) VALUES
('Spring 2025', 'Alex Johnson', 'Jane Smith', 'they/them', 'M', 'University of Example - CE101', 'alex.j@example.edu', 'Junior', 'Environmental Science, Data Analysis', 'Community Garden Database', 'Jan 15 - Apr 30, 2025', 'Complete database with 50+ entries', TRUE, TRUE),
('Spring 2025', 'Sam Williams', 'Jane Smith', 'she/her', 'S', 'University of Example - CE101', 'sam.w@example.edu', 'Sophomore', 'Marketing, Social Media', 'Social Media Campaign', 'Feb 1 - Apr 15, 2025', 'Create 10 posts with 500+ engagement', TRUE, FALSE),
('Spring 2025', 'Jordan Davis', 'Mike Wilson', 'he/him', 'L', 'State College - SLP200', 'jordan.d@statecollege.edu', 'Senior', 'Public Policy, Research', 'Policy Brief Research', 'Jan 20 - May 1, 2025', 'Completed 10-page policy brief', FALSE, FALSE);

-- =============================================
-- Default Admin Users
-- NOTE: Use the setup-admin.js script to create admin users with properly hashed passwords
-- The passwords below are bcrypt hashes (cost factor 10):
--   admin123 -> $2a$10$rQZ5E5Q5E5Q5E5Q5E5Q5E.5Q5E5Q5E5Q5E5Q5E5Q5E5Q5E5Q5E5Q5
-- For security, change these passwords immediately after setup!
-- =============================================

-- Sample admin users (passwords should be changed after initial setup)
-- Default password for all sample users: "ChangeMe123!"
-- Hash: $2a$10$N9qo8uLOickgx2ZMRZoMy.MqrqzWBPCEYz9KLJhcM3WNTEYBKjziu
INSERT INTO admin_users (username, password_hash, email, name, role, is_active) VALUES
('admin', '$2a$10$N9qo8uLOickgx2ZMRZoMy.MqrqzWBPCEYz9KLJhcM3WNTEYBKjziu', 'admin@switch4good.org', 'Admin User', 'admin', TRUE),
('lucy', '$2a$10$N9qo8uLOickgx2ZMRZoMy.MqrqzWBPCEYz9KLJhcM3WNTEYBKjziu', 'lucy@switch4good.org', 'Lucy Whitney', 'staff', TRUE),
('gianna', '$2a$10$N9qo8uLOickgx2ZMRZoMy.MqrqzWBPCEYz9KLJhcM3WNTEYBKjziu', 'gianna@switch4good.org', 'Gianna Klein', 'staff', TRUE),
('viewer', '$2a$10$N9qo8uLOickgx2ZMRZoMy.MqrqzWBPCEYz9KLJhcM3WNTEYBKjziu', 'viewer@switch4good.org', 'Viewer Account', 'viewer', TRUE)
ON CONFLICT (username) DO NOTHING;
