-- =========================================================
-- update_can_metrics_v2.sql
-- Replaces existing can_metrics data with CAN Metrics v2
-- =========================================================

-- ---------------------------------------------------------
-- 1) Backup current data
-- ---------------------------------------------------------
DROP TABLE IF EXISTS can_metrics_backup_20260415;

CREATE TABLE can_metrics_backup_20260415 AS
SELECT *
FROM can_metrics;

-- ---------------------------------------------------------
-- 2) Clear current can_metrics data
-- ---------------------------------------------------------
TRUNCATE TABLE can_metrics RESTART IDENTITY;

-- ---------------------------------------------------------
-- 3) Insert updated CAN metrics data
-- ---------------------------------------------------------
INSERT INTO can_metrics
(metric_date, is_ongoing, impression, touchpoints, engagements, conversions, program_id, school_id, notes)
VALUES

-- =========================================================
-- LIVE EVENTS
-- =========================================================
('2025-11-13', FALSE, 'UCLA Sustainable Food Futures: Career and Networking Fair', 100, 30, 14, NULL, NULL, 'Source: Live Events'),
('2025-10-22', FALSE, 'AASHE Conference', 761, 80, 5, NULL, NULL, 'Source: Live Events; Original date range: 10/22-24/25'),
('2025-09-03', FALSE, 'Stony Brook University Volunteer Fair', 600, 51, 17, NULL, NULL, 'Source: Live Events'),
('2025-04-30', FALSE, 'Boston College Earth Day Cooking Class', 40, 40, 20, NULL, NULL, 'Source: Live Events'),
('2025-04-23', FALSE, 'NYU Plant-Based Food Festival', 400, 67, 4, NULL, NULL, 'Source: Live Events'),

-- =========================================================
-- STUDENTS
-- =========================================================
(NULL, FALSE, 'Student Team Metrics', 6, 6, 0, NULL, NULL, 'Semester: Fall 2025; School: Duquesne University'),
(NULL, FALSE, 'Student Team Metrics', 56, 30, 2, NULL, NULL, 'Semester: Fall 2025; School: University of California, Berkeley'),
(NULL, FALSE, 'Student Team Metrics', 147, 89, 0, NULL, NULL, 'Semester: Fall 2025; School: Northeastern University'),
(NULL, FALSE, 'Student Team Metrics', 18, 0, 0, NULL, NULL, 'Semester: Fall 2025; School: Northeastern University'),
(NULL, FALSE, 'Student Team Metrics', 133, 55, 2, NULL, NULL, 'Semester: Fall 2025; School: Western Michigan University'),
(NULL, FALSE, 'Student Team Metrics', 2716, 92, 30, NULL, NULL, 'Semester: Fall 2025; School: University of Missouri'),
(NULL, FALSE, 'Student Team Metrics', 45, 15, 13, NULL, NULL, 'Semester: Fall 2025; School: University of Missouri'),
(NULL, FALSE, 'Student Team Metrics', 45, 22, 0, NULL, NULL, 'Semester: Fall 2025; School: University of Missouri'),
(NULL, FALSE, 'Student Team Metrics', 400, 116, 40, NULL, NULL, 'Semester: Fall 2025; School: University of Missouri'),
(NULL, FALSE, 'Student Team Metrics', 500, 199, 0, NULL, NULL, 'Semester: Fall 2025; School: University of Missouri'),
(NULL, FALSE, 'Student Team Metrics', 5, 1, 1, NULL, NULL, 'Semester: Fall 2025; School: University of Missouri'),
(NULL, FALSE, 'Student Team Metrics', 5, 0, 0, NULL, NULL, 'Semester: Fall 2025; School: University of Missouri'),
(NULL, FALSE, 'Student Team Metrics', 45, 5, 0, NULL, NULL, 'Semester: Fall 2025; School: Stony Brook University'),
(NULL, FALSE, 'Student Team Metrics', 40, 0, 0, NULL, NULL, 'Semester: Fall 2025; School: Stony Brook University'),
(NULL, FALSE, 'Student Team Metrics', 0, 0, 0, NULL, NULL, 'Semester: Fall 2025; School: Seattle Central College'),
(NULL, FALSE, 'Student Team Metrics', 22, 22, 0, NULL, NULL, 'Semester: Fall 2025; School: Seattle Central College'),
(NULL, FALSE, 'Student Team Metrics', 41, 19, 0, NULL, NULL, 'Semester: Fall 2025; School: Cal State University Long Beach'),
(NULL, FALSE, 'Student Team Metrics', 2, 0, 0, NULL, NULL, 'Semester: Fall 2025; School: Florida Gulf Coast University'),
(NULL, FALSE, 'Student Team Metrics', 0, 0, 0, NULL, NULL, 'Semester: Fall 2025; School: Florida Gulf Coast University'),
(NULL, FALSE, 'Student Team Metrics', 1, 1, 0, NULL, NULL, 'Semester: Fall 2025; School: Fisk University'),
(NULL, FALSE, 'Student Team Metrics', 2, 2, 0, NULL, NULL, 'Semester: Fall 2025; School: Washington and Lee University'),

(NULL, FALSE, 'Student Team Metrics', 3, 3, 0, NULL, NULL, 'Semester: Spring 2025; School: Western Michigan University'),
(NULL, FALSE, 'Student Team Metrics', 18, 1, 0, NULL, NULL, 'Semester: Spring 2025; School: Western Michigan University'),
(NULL, FALSE, 'Student Team Metrics', 144, 63, 0, NULL, NULL, 'Semester: Spring 2025; School: Northeastern University'),
(NULL, FALSE, 'Student Team Metrics', 0, 0, 0, NULL, NULL, 'Semester: Spring 2025; School: Northeastern University'),
(NULL, FALSE, 'Student Team Metrics', 0, 0, 0, NULL, NULL, 'Semester: Spring 2025; School: Cedar Falls High School'),
(NULL, FALSE, 'Student Team Metrics', 220, 42, 0, NULL, NULL, 'Semester: Spring 2025; School: Boston College'),
(NULL, FALSE, 'Student Team Metrics', 2, 0, 0, NULL, NULL, 'Semester: Spring 2025; School: University of Missouri'),
(NULL, FALSE, 'Student Team Metrics', 0, 0, 0, NULL, NULL, 'Semester: Spring 2025; School: University of Missouri'),
(NULL, FALSE, 'Student Team Metrics', 13, 0, 0, NULL, NULL, 'Semester: Spring 2025; School: University of Missouri'),
(NULL, FALSE, 'Student Team Metrics', 35, 30, 0, NULL, NULL, 'Semester: Spring 2025; School: University of Missouri'),
(NULL, FALSE, 'Student Team Metrics', 0, 0, 0, NULL, NULL, 'Semester: Spring 2025; School: Portland State University'),
(NULL, FALSE, 'Student Team Metrics', 72, 2, 0, NULL, NULL, 'Semester: Spring 2025; School: University of California'),
(NULL, FALSE, 'Student Team Metrics', 41, 5, 0, NULL, NULL, 'Semester: Spring 2025; School: University of California'),

-- =========================================================
-- MEDIA CLUB
-- =========================================================
('2025-10-20', FALSE, 'Participants added to Circle', 29, 0, 0, NULL, NULL, 'Source: Media Club'),
('2025-11-05', FALSE, 'Meeting #1 RSVPs', 0, 10, 0, NULL, NULL, 'Source: Media Club'),
('2025-11-05', FALSE, 'Meeting #1 Attendance', 0, 0, 7, NULL, NULL, 'Source: Media Club'),
(NULL, TRUE, 'Participants'' Circle posts', 0, 0, 10, NULL, NULL, 'Source: Media Club; Ongoing'),
('2025-11-11', FALSE, 'Matt and TJ completed Lesson 1', 0, 2, 0, NULL, NULL, 'Source: Media Club'),
('2025-11-15', FALSE, 'TJ completed Lesson 2', 0, 1, 0, NULL, NULL, 'Source: Media Club'),
('2025-12-03', FALSE, 'Meeting #2 RSVPs', 0, 3, 0, NULL, NULL, 'Source: Media Club'),
('2025-12-03', FALSE, 'Meeting #2 Attendance', 0, 0, 5, NULL, NULL, 'Source: Media Club'),
(NULL, TRUE, 'Participants'' Circle comments', 0, 1, 0, NULL, NULL, 'Source: Media Club; Ongoing'),
('2025-12-05', FALSE, 'Calvin completed Lesson 1', 0, 1, 0, NULL, NULL, 'Source: Media Club'),
('2026-01-07', FALSE, 'GCal Invites for Meeting #3', 30, 0, 0, NULL, NULL, 'Source: Media Club'),
('2026-01-07', FALSE, 'Meeting #3 RSVPs', 0, 4, 0, NULL, NULL, 'Source: Media Club'),
('2026-01-07', FALSE, 'Meeting #3 Attendance', 0, 0, 7, NULL, NULL, 'Source: Media Club'),
('2026-01-09', FALSE, 'Hannah completed Lessons 1-3', 0, 3, 0, NULL, NULL, 'Source: Media Club'),
('2026-01-31', FALSE, 'GCal Invites for Meeting #4', 37, 0, 0, NULL, NULL, 'Source: Media Club'),
('2026-02-04', FALSE, 'Meeting #4 RSVPS', 0, 13, 0, NULL, NULL, 'Source: Media Club'),
('2026-02-04', FALSE, 'Meeting #4 Attendance', 0, 0, 7, NULL, NULL, 'Source: Media Club');

-- ---------------------------------------------------------
-- 4) Verification queries
-- ---------------------------------------------------------

-- Total row count
SELECT COUNT(*) AS final_row_count
FROM can_metrics;

-- Total metrics
SELECT
  COALESCE(SUM(touchpoints), 0) AS total_touchpoints,
  COALESCE(SUM(engagements), 0) AS total_engagements,
  COALESCE(SUM(conversions), 0) AS total_conversions
FROM can_metrics;

-- Breakdown by source group
SELECT
  CASE
    WHEN notes LIKE 'Source: Live Events%' THEN 'Live Events'
    WHEN notes LIKE 'Source: Media Club%' THEN 'Media Club'
    WHEN notes LIKE 'Semester:%' THEN 'Students'
    ELSE 'Other'
  END AS source_group,
  COUNT(*) AS row_count,
  COALESCE(SUM(touchpoints), 0) AS total_touchpoints,
  COALESCE(SUM(engagements), 0) AS total_engagements,
  COALESCE(SUM(conversions), 0) AS total_conversions
FROM can_metrics
GROUP BY 1
ORDER BY 1;

-- Full final data review
SELECT
  metric_id,
  metric_date,
  is_ongoing,
  impression,
  touchpoints,
  engagements,
  conversions,
  program_id,
  school_id,
  notes
FROM can_metrics
ORDER BY metric_id;