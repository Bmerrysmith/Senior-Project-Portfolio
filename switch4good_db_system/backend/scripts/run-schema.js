/**
 * Run the complete schema SQL file
 */
const pool = require('../db');
const fs = require('fs');

async function runSchema() {
    try {
        console.log('Reading schema file...');
        const schema = fs.readFileSync('../sql/schema-complete.sql', 'utf8');
        
        console.log('Executing schema (this may take a moment)...');
        await pool.query(schema);
        console.log('Schema executed successfully!');
        
        // List tables
        const tables = await pool.query(`
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_type = 'BASE TABLE'
            ORDER BY table_name
        `);
        console.log('\nTables in database:');
        tables.rows.forEach(r => console.log('  - ' + r.table_name));
        
        // List views
        const views = await pool.query(`
            SELECT table_name 
            FROM information_schema.views 
            WHERE table_schema = 'public' 
            ORDER BY table_name
        `);
        console.log('\nViews created:');
        views.rows.forEach(r => console.log('  - ' + r.table_name));
        
        // Count seed data
        const counts = await pool.query(`
            SELECT 
                (SELECT COUNT(*) FROM semester) as semesters,
                (SELECT COUNT(*) FROM university) as universities,
                (SELECT COUNT(*) FROM program) as programs,
                (SELECT COUNT(*) FROM course) as courses,
                (SELECT COUNT(*) FROM partnership) as partnerships,
                (SELECT COUNT(*) FROM project) as projects,
                (SELECT COUNT(*) FROM student_pii) as students,
                (SELECT COUNT(*) FROM student_registration) as registrations,
                (SELECT COUNT(*) FROM weekly_hours) as hour_entries
        `);
        console.log('\nSeed data counts:');
        Object.entries(counts.rows[0]).forEach(([k, v]) => console.log(`  ${k}: ${v}`));
        
        await pool.end();
        console.log('\nDone!');
    } catch (err) {
        console.error('Error:', err.message);
        console.error('Details:', err);
        process.exit(1);
    }
}

runSchema();

