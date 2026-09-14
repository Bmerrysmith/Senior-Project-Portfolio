# Impact Tracking Database - Schema Reference

## Overview

This database replaces multiple Excel tabs with a properly normalized relational structure for tracking:
- University partnerships by semester
- Students, projects, and deliverables
- Service hours
- Course details with dairy content tracking
- Outreach touchpoints/engagements/conversions

---

## Entity Relationship Diagram (Simplified)

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   SEMESTER   │     │  UNIVERSITY  │     │  S4G_STAFF   │
└──────┬───────┘     └──────┬───────┘     └──────┬───────┘
       │                    │                    │
       │    ┌───────────────┴───────────┐       │
       │    │                           │       │
       ▼    ▼                           │       │
┌──────────────┐                        │       │
│   PROGRAM    │◄───────────────────────┴───────┘
└──────┬───────┘
       │
       │    ┌──────────────┐
       │    │    COURSE    │
       │    └──────┬───────┘
       │           │
┌──────▼───────────▼──┐
│    PARTNERSHIP      │ (Program + Semester + Course)
└──────────┬──────────┘
           │
           ▼
┌──────────────────┐     ┌──────────────┐
│     PROJECT      │     │ STUDENT_PII  │ (Restricted)
└──────────┬───────┘     └──────┬───────┘
           │                    │
           └────────┬───────────┘
                    ▼
        ┌───────────────────────┐
        │ STUDENT_REGISTRATION  │
        └───────────┬───────────┘
                    │
        ┌───────────┼───────────┐
        ▼           ▼           ▼
┌──────────────┐  ┌──────────────┐
│ WEEKLY_HOURS │  │ DELIVERABLE  │
└──────────────┘  └──────────────┘
```

---

## Tables Reference

### Dimension Tables

| Table | Description | Key Fields |
|-------|-------------|------------|
| `semester` | Academic semesters (replaces "one tab per semester") | name, start_date, end_date, is_current |
| `s4g_staff` | Switch4Good staff members | name, email, role |
| `university` | Partner universities | name, city, state, contact info |
| `project_type` | Categories of projects | name, description |

### Core Tables

| Table | Description | Key Relationships |
|-------|-------------|-------------------|
| `program` | Programs within universities | FK: university_id, s4g_staff_id |
| `course` | Courses linked to programs | FK: program_id. Tracks dairy_content |
| `partnership` | Program active in a semester | FK: program_id, semester_id, course_id |
| `project` | Specific projects in partnerships | FK: partnership_id, project_type_id |

### Student Tables (PII Separated)

| Table | Description | Access |
|-------|-------------|--------|
| `student_pii` | Personal info (name, email, etc.) | **Admin/Staff only** |
| `student_registration` | Student enrolled in project | Links student to project |
| `weekly_hours` | Service hours logged | FK: registration_id |
| `deliverable` | Project deliverables | FK: registration_id |

### Outreach Tables

| Table | Description |
|-------|-------------|
| `outreach_contact` | Contacts at universities |
| `outreach_event` | Touchpoints, engagements, conversions |

---

## Reporting Views

### Privacy-Safe Views (No PII)

| View | Description | Access |
|------|-------------|--------|
| `v_student_registrations_anon` | De-identified student data | Student team, Reporting |
| `v_current_semester_activity` | Current semester partnerships | Staff, Reporting |
| `v_student_hours_totals` | Hours by project (no names) | Staff, Reporting |
| `v_partnership_history` | Which programs were active when | Staff, Reporting |
| `v_outreach_funnel` | Touchpoint/engagement/conversion counts | Staff, Reporting |

### Funder Dashboard Metrics

| View | Metric | Chart Type |
|------|--------|------------|
| `v_metric_active_partnerships` | Total active partnerships | Number card |
| `v_metric_students_engaged` | Students per semester | Bar chart |
| `v_metric_service_hours` | Total hours by semester | Bar chart |
| `v_metric_completion_rate` | Deliverable completion % | Gauge |
| `v_metric_university_reach` | Universities covered | Map/card |
| `v_metric_program_types` | Program type distribution | Pie chart |
| `v_metric_course_impact` | Courses with dairy content | Number + list |
| `v_metric_outreach_funnel` | Conversion pipeline | Funnel |
| `v_metric_project_performance` | Hours by project type | Bar chart |
| `v_metric_retention` | Returning students | Number card |
| `v_metric_staff_workload` | Work per staff member | Stacked bars |
| `v_metric_milestones` | Student milestone progress | Progress bars |

---

## Excel Column Mapping

### Old "Service Learning Programs" Tab → New Tables

| Excel Column | New Location |
|--------------|--------------|
| Semester | `semester.name` (via `partnership.semester_id`) |
| School | `university.name` |
| S4G Staff | `s4g_staff.name` |
| Program | `program.name` |
| Faculty/Staff | `course.faculty_names` |
| TY Note Sent | `partnership.ty_note_sent` |
| Students Participating | `partnership.students_participating` |
| Total in Class | `partnership.total_in_class` |
| Status | `partnership.status` |
| Notes | `partnership.notes` |
| Course Details | `course.course_code`, `schedule`, `description` |

### Old "Students" Tab → New Tables

| Excel Column | New Location |
|--------------|--------------|
| Name | `student_pii.first_name`, `last_name` **[RESTRICTED]** |
| Email | `student_pii.email` **[RESTRICTED]** |
| Pronouns | `student_pii.pronouns` **[RESTRICTED]** |
| T-Shirt Size | `student_pii.tshirt_size` **[RESTRICTED]** |
| Year in School | `student_pii.year_in_school` |
| Projects | `project.name` (via registration) |
| Total Hours | `SUM(weekly_hours.hours_worked)` **[COMPUTED]** |
| Attended Orientation | `student_registration.attended_orientation` |
| Completed Deliverables | `student_registration.completed_deliverables` |

---

## Security Roles

| Role | Access |
|------|--------|
| `impact_admin` | Full access to all tables |
| `impact_staff` | Read/write to operational tables, read PII |
| `impact_student_team` | Read anonymous views only, no PII |
| `impact_reporting` | Read-only, no PII |

---

## Data Quality Rules

### CHECK Constraints

- `semester.name` must match pattern `Spring|Summer|Fall|Winter YYYY`
- `partnership.status` must be one of: 'On Track', 'Concerning', 'No longer participating', 'Completed', 'On Hold'
- `weekly_hours.hours_worked` must be 0-80
- `outreach_event.event_type` must be: 'touchpoint', 'engagement', 'conversion'

### UNIQUE Constraints

- One partnership per program per semester
- One student registration per student per project
- One hours entry per registration per week

### Triggers

- Only one semester can have `is_current = TRUE`
- `updated_at` auto-updates on any row change
- `students_participating` auto-updates when registrations change

---

## Sample Queries

See `schema-complete.sql` Section 7 for five pre-written queries:

1. **Programs that went quiet** - Active before but not in current semester
2. **Dairy content courses** - Courses that added content after partnership
3. **Students by program/school/type** - With ROLLUP subtotals
4. **Registration trends** - Average per project over time
5. **Top projects by hours** - Ranked by service hours

---

## Files

| File | Purpose |
|------|---------|
| `schema-complete.sql` | Full DDL, seed data, views, queries |
| `run-schema.js` | Script to execute schema |
| `setup-admin.js` | Manage admin login users |
| `init-admin-table.js` | Initialize admin auth table |

---

## Quick Start

```bash
# Deploy schema (creates tables + seed data)
cd backend
node run-schema.js

# Manage admin users
node setup-admin.js list
node setup-admin.js create
```
