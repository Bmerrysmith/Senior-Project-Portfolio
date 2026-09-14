-- ============================================================================
-- Team 1: Switch4Good Impact Tracking Database
-- DML (Data Manipulation Language) - Data Population
-- ============================================================================
-- This file contains all INSERT statements to populate the Switch4Good
-- Service Learning Program tracking database with sample data.
-- ============================================================================

-- ============================================================================
-- SECTION 1: Reference/Dimension Tables
-- ============================================================================

-- Schools (Universities partnered with Switch4Good)
INSERT INTO schools (school_name) VALUES
('University of California, Los Angeles'),
('Arizona State University'),
('Stanford University'),
('University of Southern California'),
('Cal State Long Beach');

-- Semesters (Academic Terms)
INSERT INTO semesters (season, year) VALUES
('Fall', 2024),
('Spring', 2025),
('Fall', 2025);

-- Staff Contacts (S4G Staff and University Partners)
INSERT INTO staff_contacts (full_name, email, role_title, organization, notes) VALUES
('Lucy Whitney', 'lucy@switch4good.org', 'Program Coordinator', 'Switch4Good', 'Primary student liaison'),
('Gianna Klein', 'gianna@switch4good.org', 'Outreach Director', 'Switch4Good', 'Manages university partnerships'),
('Marcus Chen', 'marcus@switch4good.org', 'Data Analyst', 'Switch4Good', 'Dashboard and reporting'),
('Dr. Patricia Nguyen', 'pnguyen@ucla.edu', 'Professor', 'UCLA', 'Environmental Studies faculty lead'),
('Prof. Robert Martinez', 'rmartinez@asu.edu', 'Department Chair', 'Arizona State University', 'Community engagement lead'),
('Dr. Sarah Mitchell', 'smitchell@ucla.edu', 'Faculty Advisor', 'UCLA', 'Public health programs'),
('Dr. Lisa Chen', 'lchen@asu.edu', 'Program Director', 'Arizona State University', 'Sustainability school');

-- Deliverables Reference (Types of student deliverables)
INSERT INTO deliverables (deliverable_name, description) VALUES
('Research Paper', 'Academic research paper on assigned topic'),
('Social Media Campaign', 'Series of social media posts with engagement metrics'),
('Policy Brief', 'Policy analysis and recommendations document'),
('Data Dashboard', 'Interactive data visualization dashboard'),
('Community Workshop', 'Planning and facilitating community education workshops'),
('Survey Report', 'Survey design, collection, and analysis report'),
('Presentation', 'Final presentation of project findings');

-- ============================================================================
-- SECTION 2: Programs Data
-- ============================================================================

-- Programs (Service Learning Programs at Universities)
INSERT INTO programs (program_name, school_id, website, program_type, season_hint, needs_formalization, notes) VALUES
('Sustainability Studies Service Learning', 1, 'https://environment.ucla.edu', 'Service Learning', 'Fall/Spring', FALSE, 'Strong partnership since 2023'),
('Public Health Internship Program', 1, 'https://ph.ucla.edu', 'Internship', 'Spring', FALSE, 'New internship track'),
('Community Engagement Fellows', 2, 'https://sfis.asu.edu', 'Fellowship', 'Fall/Spring', FALSE, 'Fellowship for food justice work'),
('Nutrition Science Research', 2, 'https://chs.asu.edu', 'Research', 'Spring', TRUE, 'Research collaboration on dairy alternatives'),
('Food Systems Initiative', 3, NULL, 'Service Learning', 'Fall', TRUE, 'Prospective partnership');

-- Program Semester Activity (Which programs are active each semester)
INSERT INTO program_semester_activity (program_id, semester_id, is_active, most_recent_contact_date, sg4_staff_contact_id, partner_staff_contact_id, partner_email, notes) VALUES
-- Fall 2024
(1, 1, TRUE, '2024-08-15', 1, 4, 'pnguyen@ucla.edu', 'Strong first semester partnership'),
(3, 1, TRUE, '2024-08-20', 1, 5, 'rmartinez@asu.edu', 'Good engagement from ASU students'),
-- Spring 2025
(1, 2, TRUE, '2025-01-10', 1, 4, 'pnguyen@ucla.edu', 'Expanded from Fall'),
(2, 2, TRUE, '2025-01-15', 2, 6, 'smitchell@ucla.edu', 'New internship pilot'),
(4, 2, TRUE, '2025-01-20', 1, 7, 'lchen@asu.edu', 'Research collaboration starting'),
-- Fall 2025 (Current)
(1, 3, TRUE, '2025-08-25', 1, 4, 'pnguyen@ucla.edu', 'Largest cohort yet'),
(2, 3, TRUE, '2025-08-28', 2, 6, 'smitchell@ucla.edu', 'Growing interest'),
(3, 3, TRUE, '2025-08-22', 1, 5, 'rmartinez@asu.edu', 'Reactivated after Spring hiatus'),
(4, 3, TRUE, '2025-09-01', 1, 7, 'lchen@asu.edu', 'Improved engagement');

-- ============================================================================
-- SECTION 3: Students Data
-- ============================================================================

-- Students (Student Information)
INSERT INTO students (full_name, email, pronouns, tshirt_size, year_in_school, areas_of_interest) VALUES
('Alex Johnson', 'alex.johnson@ucla.edu', 'they/them', 'M', 'Junior', 'Data analysis, sustainability research'),
('Samantha Williams', 'sam.williams@ucla.edu', 'she/her', 'S', 'Senior', 'Nutrition policy, community health'),
('Jordan Davis', 'jordan.davis@asu.edu', 'he/him', 'L', 'Senior', 'Community organizing, food justice'),
('Emily Chen', 'emily.chen@ucla.edu', 'she/her', 'M', 'Graduate', 'Plant-based diets, biochemistry'),
('Marcus Brown', 'marcus.brown@ucla.edu', 'he/him', 'XL', 'Junior', 'Social media, digital marketing'),
('Priya Patel', 'priya.patel@asu.edu', 'she/her', 'S', 'Sophomore', 'Public health, data visualization'),
('Kevin Lee', 'kevin.lee@ucla.edu', 'he/him', 'M', 'Senior', 'Data science, machine learning'),
('Sofia Rodriguez', 'sofia.rodriguez@asu.edu', 'she/her', 'M', 'Junior', 'Climate change, agriculture'),
('David Kim', 'david.kim@ucla.edu', 'he/him', 'L', 'Junior', 'Nutrition, research methods'),
('Aisha Mohammed', 'aisha.mohammed@asu.edu', 'she/her', 'S', 'Senior', 'Food policy, advocacy'),
('Ryan Thompson', 'ryan.thompson@ucla.edu', 'he/him', 'M', 'Sophomore', 'Brand strategy, content creation'),
('Jessica Garcia', 'jessica.garcia@ucla.edu', 'she/her', 'S', 'Graduate', 'Environmental health, data analysis');

-- Student Participation (Links students to programs and projects)
INSERT INTO student_participation (student_id, program_id, semester_id, sg4_staff_id, project_name, project_start_date, project_end_date, meeting_cadence, conflicting_datetimes, success_metric, created_at) VALUES
-- Fall 2024 Participations
(1, 1, 1, 1, 'Dairy Environmental Impact Study', '2024-09-02', '2024-12-06', 'Weekly', 'Thanksgiving break Nov 25-29', 'Complete analysis section of research paper', '2024-08-28'),
(2, 1, 1, 1, 'Dairy Environmental Impact Study', '2024-09-02', '2024-12-06', 'Weekly', 'Finals Dec 9-13', 'Lead literature review section', '2024-08-28'),
(5, 1, 1, 2, 'Campus Awareness Campaign', '2024-09-09', '2024-11-22', 'Bi-weekly', NULL, 'Create 5 Instagram posts with 500+ engagement', '2024-09-05'),
(3, 3, 1, 1, 'Community Food Access Survey', '2024-09-15', '2024-12-01', 'Weekly', 'Fall break Oct 14-18', 'Collect 50 survey responses', '2024-09-10'),
-- Spring 2025 Participations
(1, 1, 2, 1, 'Plant-Based Nutrition Meta-Analysis', '2025-01-20', '2025-04-25', 'Weekly', 'Spring break Mar 24-28', 'Meta-analysis methodology section', '2025-01-15'),
(4, 1, 2, 1, 'Plant-Based Nutrition Meta-Analysis', '2025-01-20', '2025-04-25', 'Weekly', NULL, 'Results and discussion sections', '2025-01-15'),
(7, 1, 2, 1, 'Student Dining Data Analysis', '2025-02-01', '2025-05-02', 'Bi-weekly', NULL, 'Build data visualization dashboard', '2025-01-25'),
(5, 2, 2, 2, 'Social Media Internship', '2025-01-27', '2025-05-05', 'Weekly', 'Spring break Mar 24-28', 'Manage Instagram account', '2025-01-22'),
(11, 2, 2, 2, 'Social Media Internship', '2025-01-27', '2025-05-05', 'Weekly', NULL, 'Create TikTok content', '2025-01-22'),
(4, 4, 2, 1, 'Dairy Alternative Research', '2025-02-03', '2025-04-28', 'Weekly', NULL, 'Lab analysis of oat milk proteins', '2025-02-01'),
-- Fall 2025 Participations (Current Semester)
(1, 1, 3, 1, 'Food Systems Research Project', '2025-09-01', '2025-12-05', 'Weekly', 'Thanksgiving Nov 24-28', 'Lead research methodology', '2025-08-26'),
(2, 1, 3, 1, 'Food Systems Research Project', '2025-09-01', '2025-12-05', 'Weekly', 'Finals Dec 8-12', 'Policy analysis section', '2025-08-26'),
(12, 1, 3, 1, 'Food Systems Research Project', '2025-09-01', '2025-12-05', 'Bi-weekly', NULL, 'Data collection and analysis', '2025-08-26'),
(5, 1, 3, 2, 'Campus Outreach Initiative', '2025-09-08', '2025-11-21', 'Weekly', NULL, 'Tabling events coordinator', '2025-09-02'),
(11, 2, 3, 2, 'Plant-Based Promotion Campaign', '2025-09-15', '2025-12-01', 'Weekly', NULL, 'Lead campaign strategy', '2025-09-08'),
(6, 3, 3, 1, 'Community Health Workshop Series', '2025-09-22', '2025-11-30', 'Bi-weekly', 'Fall break Oct 13-17', 'Host 3 workshops with 30+ attendees', '2025-09-15'),
(8, 3, 3, 1, 'Community Health Workshop Series', '2025-09-22', '2025-11-30', 'Bi-weekly', NULL, 'Community outreach coordination', '2025-09-15'),
(10, 3, 3, 1, 'Community Health Workshop Series', '2025-09-22', '2025-11-30', 'Bi-weekly', NULL, 'Policy brief on food access', '2025-09-15'),
(7, 4, 3, 1, 'Nutrition Data Dashboard', '2025-09-08', '2025-12-08', 'Weekly', NULL, 'Full stack development', '2025-09-05'),
(9, 4, 3, 1, 'Nutrition Data Dashboard', '2025-09-08', '2025-12-08', 'Weekly', NULL, 'Data pipeline design', '2025-09-05');

-- Student Checklist Items (Onboarding Tasks Completion)
INSERT INTO student_checklist_item (participation_id, item_type, status, completed_at, notes) VALUES
-- Fall 2024 students (completed)
(1, 'attended_orientation', TRUE, '2024-08-30', NULL),
(1, 'sent_headshot', TRUE, '2024-09-01', NULL),
(1, 'signed_media_release', TRUE, '2024-08-30', NULL),
(2, 'attended_orientation', TRUE, '2024-08-30', NULL),
(2, 'sent_headshot', TRUE, '2024-09-02', NULL),
(2, 'signed_media_release', TRUE, '2024-08-30', NULL),
(3, 'attended_orientation', TRUE, '2024-09-06', NULL),
(3, 'sent_headshot', TRUE, '2024-09-08', NULL),
(4, 'attended_orientation', TRUE, '2024-09-12', NULL),
(4, 'sent_headshot', FALSE, NULL, 'Reminder sent'),
-- Spring 2025 students
(5, 'attended_orientation', TRUE, '2025-01-16', NULL),
(5, 'sent_headshot', TRUE, '2025-01-18', NULL),
(6, 'attended_orientation', TRUE, '2025-01-16', NULL),
(6, 'sent_headshot', TRUE, '2025-01-19', NULL),
(7, 'attended_orientation', TRUE, '2025-01-26', NULL),
(7, 'sent_headshot', TRUE, '2025-01-28', NULL),
-- Fall 2025 students (current semester - in progress)
(11, 'attended_orientation', TRUE, '2025-08-27', NULL),
(11, 'sent_headshot', TRUE, '2025-08-29', NULL),
(12, 'attended_orientation', TRUE, '2025-08-27', NULL),
(12, 'sent_headshot', TRUE, '2025-08-30', NULL),
(13, 'attended_orientation', TRUE, '2025-08-27', NULL),
(13, 'sent_headshot', FALSE, NULL, 'Pending');

-- ============================================================================
-- SECTION 4: Hours and Check-in Data
-- ============================================================================

-- Hours Log (Weekly Hours Worked by Students)
INSERT INTO hours_log (participation_id, period_number, week_start_date, hours, notes) VALUES
-- Fall 2024 Hours
(1, 1, '2024-09-02', 5.5, 'Started data collection'),
(1, 2, '2024-09-09', 6.0, 'Data cleaning'),
(1, 3, '2024-09-16', 7.5, 'Analysis phase'),
(1, 4, '2024-09-23', 8.0, 'Presented preliminary findings'),
(1, 5, '2024-09-30', 6.5, 'Writing draft'),
(1, 6, '2024-10-07', 7.0, 'Revisions'),
(1, 7, '2024-10-14', 5.0, 'Final edits'),
(2, 1, '2024-09-02', 4.0, 'Literature search'),
(2, 2, '2024-09-09', 5.5, 'Reading papers'),
(2, 3, '2024-09-16', 6.0, 'Synthesizing findings'),
(2, 4, '2024-09-23', 7.0, 'Draft review'),
(2, 5, '2024-09-30', 5.5, 'Revisions'),
(3, 1, '2024-09-09', 3.5, 'Content planning'),
(3, 2, '2024-09-16', 4.0, 'Created 2 posts'),
(3, 3, '2024-09-23', 4.5, 'Created 2 posts'),
(3, 4, '2024-09-30', 3.0, 'Final post and analytics'),
(4, 1, '2024-09-16', 5.0, 'Survey design'),
(4, 2, '2024-09-23', 6.5, 'Collecting responses'),
(4, 3, '2024-09-30', 7.0, 'More responses'),
(4, 4, '2024-10-07', 6.0, 'Analysis'),
(4, 5, '2024-10-14', 5.5, 'Final report'),
-- Spring 2025 Hours
(5, 1, '2025-01-20', 6.0, 'Methods development'),
(5, 2, '2025-01-27', 7.5, 'Paper screening'),
(5, 3, '2025-02-03', 8.0, 'Data extraction'),
(5, 4, '2025-02-10', 6.5, 'Analysis'),
(5, 5, '2025-02-17', 7.0, 'Writing'),
(6, 1, '2025-01-20', 5.0, 'Literature review'),
(6, 2, '2025-01-27', 6.0, 'Data synthesis'),
(6, 3, '2025-02-03', 7.5, 'Writing results'),
(6, 4, '2025-02-10', 8.0, 'Revisions'),
(7, 1, '2025-01-27', 8.0, 'Dashboard design'),
(7, 2, '2025-02-03', 10.0, 'Development'),
(7, 3, '2025-02-10', 9.5, 'Testing'),
(7, 4, '2025-02-17', 7.0, 'Deployment'),
-- Fall 2025 Hours (Current Semester)
(11, 1, '2025-09-01', 5.0, 'Project kickoff'),
(11, 2, '2025-09-08', 6.5, 'Research planning'),
(11, 3, '2025-09-15', 7.0, 'Data collection started'),
(11, 4, '2025-09-22', 6.0, 'Continued data collection'),
(12, 1, '2025-09-01', 4.5, 'Policy review'),
(12, 2, '2025-09-08', 5.5, 'Framework development'),
(12, 3, '2025-09-15', 6.0, 'Writing'),
(12, 4, '2025-09-22', 5.0, 'Team sync'),
(13, 1, '2025-09-01', 5.0, 'Setup'),
(13, 2, '2025-09-08', 7.0, 'Data processing'),
(13, 3, '2025-09-15', 8.0, 'Analysis'),
(19, 1, '2025-09-08', 8.0, 'Architecture design'),
(19, 2, '2025-09-15', 10.0, 'Frontend development'),
(19, 3, '2025-09-22', 9.0, 'Backend integration'),
(20, 1, '2025-09-08', 6.0, 'Data modeling'),
(20, 2, '2025-09-15', 7.5, 'ETL pipeline'),
(20, 3, '2025-09-22', 8.0, 'Testing');

-- Survey Check-ins
INSERT INTO survey_checkin (participation_id, checkin_number, completed, completed_at, notes) VALUES
(1, 1, TRUE, '2024-09-09', 'Week 1 check-in'),
(1, 2, TRUE, '2024-09-16', 'Week 2 check-in'),
(1, 3, TRUE, '2024-09-23', 'Week 3 check-in'),
(1, 4, TRUE, '2024-09-30', 'Week 4 check-in'),
(2, 1, TRUE, '2024-09-09', 'Week 1 check-in'),
(2, 2, TRUE, '2024-09-16', 'Week 2 check-in'),
(2, 3, TRUE, '2024-09-23', 'Week 3 check-in'),
(5, 1, TRUE, '2025-01-27', 'Week 1 check-in'),
(5, 2, TRUE, '2025-02-03', 'Week 2 check-in'),
(5, 3, TRUE, '2025-02-10', 'Week 3 check-in'),
(11, 1, TRUE, '2025-09-08', 'Week 1 check-in'),
(11, 2, TRUE, '2025-09-15', 'Week 2 check-in'),
(11, 3, FALSE, NULL, 'Week 3 - pending');

-- Meeting Check-ins
INSERT INTO meeting_checkin (participation_id, meeting_number, occurred, meeting_date, notes) VALUES
(1, 1, TRUE, '2024-09-05', 'Initial project meeting'),
(1, 2, TRUE, '2024-09-19', 'Progress check-in'),
(1, 3, TRUE, '2024-10-03', 'Mid-project review'),
(2, 1, TRUE, '2024-09-05', 'Initial project meeting'),
(2, 2, TRUE, '2024-09-19', 'Progress check-in'),
(5, 1, TRUE, '2025-01-23', 'Semester kickoff'),
(5, 2, TRUE, '2025-02-06', 'Progress review'),
(11, 1, TRUE, '2025-09-03', 'Semester kickoff'),
(11, 2, TRUE, '2025-09-17', 'Progress check-in');

-- ============================================================================
-- SECTION 5: Deliverables Completion
-- ============================================================================

-- Deliverable Completion (Student Deliverables Tracking)
INSERT INTO deliverable_completion (participation_id, deliverable_id, completed, completed_at, notes) VALUES
-- Fall 2024 Completions
(1, 1, TRUE, '2024-11-10', 'Excellent work on the statistical analysis'),
(2, 1, TRUE, '2024-10-28', 'Well-researched and thorough'),
(3, 2, TRUE, '2024-11-12', 'Great engagement rates - 650 total'),
(4, 6, TRUE, '2024-11-20', 'Survey report with 78 responses'),
-- Spring 2025 Completions
(5, 1, TRUE, '2025-04-20', 'Published in student journal'),
(6, 1, TRUE, '2025-04-22', 'Strong discussion section'),
(7, 4, TRUE, '2025-03-10', 'Beautiful Tableau visualizations'),
(8, 2, TRUE, '2025-04-25', 'Exceeded engagement targets'),
-- Fall 2025 (In Progress)
(11, 1, FALSE, NULL, 'Draft due 2025-10-15'),
(19, 4, FALSE, NULL, 'MVP due 2025-11-01');

-- ============================================================================
-- SECTION 6: Course Offerings Data
-- ============================================================================

-- Course Offerings (Service Learning Courses per Semester)
INSERT INTO course_offerings (school_id, program_id, semester_id, sg4_staff_id, faculty_staff_contact_id, ty_note, students_participating, total_classes_in_session, status, notes, next_steps, course_details) VALUES
-- Fall 2024
(1, 1, 1, 1, 4, 'Sent', 12, 28, 'Completed', 'Strong first semester partnership', NULL, 'ENV 180 - Food Systems and Sustainability - Mon/Wed 2:00-3:30pm'),
(2, 3, 1, 1, 5, 'Sent', 8, 15, 'Completed', 'Good engagement from ASU students', NULL, 'SOC 394 - Community-Based Research Methods - Wed 3:00-5:30pm'),
-- Spring 2025
(1, 1, 2, 1, 4, 'Sent', 15, 30, 'Completed', 'Expanded from Fall, great student projects', NULL, 'ENV 180 - Food Systems and Sustainability - Mon/Wed 2:00-3:30pm'),
(1, 2, 2, 2, 6, 'Sent', 6, 20, 'Completed', 'New internship pilot program', NULL, 'PH 250 - Nutrition and Public Health - Tue/Thu 1:00-2:30pm'),
(2, 4, 2, 1, 7, NULL, 4, 12, 'Concerning', 'Low engagement, need follow-up', 'Schedule meeting with Dr. Chen', 'NUT 401 - Advanced Nutrition Science - Mon/Wed/Fri 11:00am-12:00pm'),
-- Fall 2025 (Current)
(1, 1, 3, 1, 4, NULL, 18, 32, 'On Track', 'Largest cohort yet', 'Schedule mid-semester check-in', 'ENV 180 - Food Systems and Sustainability - Mon/Wed 2:00-3:30pm'),
(1, 2, 3, 2, 6, NULL, 10, 25, 'On Track', 'Growing interest in internship track', 'Plan end-of-semester showcase', 'PH 250 - Nutrition and Public Health - Tue/Thu 1:00-2:30pm'),
(2, 3, 3, 1, 5, NULL, 6, 18, 'On Track', 'Reactivated after Spring hiatus', 'Rebuild faculty relationship', 'SOC 394 - Community-Based Research Methods - Wed 3:00-5:30pm'),
(2, 4, 3, 1, 7, NULL, 5, 15, 'On Track', 'Improved from last semester', 'Monthly check-ins with Dr. Kim', 'NUT 401 - Advanced Nutrition Science - Mon/Wed/Fri 11:00am-12:00pm');

-- ============================================================================
-- SECTION 7: CAN Metrics (Touchpoints, Engagements, Conversions)
-- ============================================================================

-- CAN Metrics (Outreach Tracking)
INSERT INTO can_metrics (metric_date, is_ongoing, impression, touchpoints, engagements, conversions, program_id, school_id, notes) VALUES
-- UCLA Programs
('2024-07-15', FALSE, 'Very Positive', 1, 0, 0, 1, 1, 'Initial outreach to Dr. Nguyen'),
('2024-07-28', FALSE, 'Very Positive', 0, 1, 0, 1, 1, 'Program overview call'),
('2024-08-10', FALSE, 'Very Positive', 0, 0, 1, 1, 1, 'Partnership agreement signed'),
('2024-11-01', FALSE, 'Positive', 1, 0, 0, 2, 1, 'Internship program inquiry'),
('2024-11-20', FALSE, 'Positive', 0, 1, 0, 2, 1, 'Program planning call'),
('2024-12-15', FALSE, 'Very Positive', 0, 0, 1, 2, 1, 'Internship launch confirmed'),
-- ASU Programs
('2024-06-01', FALSE, 'Positive', 1, 0, 0, 3, 2, 'Cold outreach'),
('2024-06-20', FALSE, 'Positive', 0, 1, 0, 3, 2, 'Discussion about fellowship'),
('2024-07-15', FALSE, 'Very Positive', 0, 0, 1, 3, 2, 'Partnership formalized'),
('2024-10-05', FALSE, 'Positive', 1, 0, 0, 4, 2, 'Research collaboration inquiry'),
('2025-01-10', FALSE, 'Positive', 0, 1, 0, 4, 2, 'Research planning call'),
('2025-01-25', FALSE, 'Positive', 0, 0, 1, 4, 2, 'Research collaboration launched'),
-- Prospective (Stanford - not yet converted)
('2025-08-01', TRUE, 'Neutral', 1, 0, 0, NULL, 3, 'Initial outreach to Stanford'),
('2025-09-05', TRUE, 'Neutral', 1, 0, 0, NULL, 3, 'Follow-up email sent');

-- ============================================================================
-- END OF DATA POPULATION FILE
-- ============================================================================
