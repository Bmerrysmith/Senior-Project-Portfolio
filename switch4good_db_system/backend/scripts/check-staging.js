require("dotenv").config();
const { Pool } = require("pg");

const pool = new Pool({
  user: process.env.DB_USER,
  password: process.env.DB_PASSWORD,
  host: process.env.DB_HOST,
  port: process.env.DB_PORT,
  database: process.env.DB_NAME,
  ssl: { rejectUnauthorized: false },
});

async function checkStagingTables() {
  try {
    const stagingTables = [
      "stg_ss1_program_course_tab",
      "stg_ss1_student_tracker",
      "stg_ss2_can_metrics",
      "stg_ss3_program_directory",
    ];

    console.log("\n=== Staging Tables Structure ===\n");

    for (const tableName of stagingTables) {
      console.log(`\n📋 ${tableName}`);
      console.log("=".repeat(50));

      // Get columns
      const columnsResult = await pool.query(
        `
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_schema = 'public' AND table_name = $1
        ORDER BY ordinal_position
      `,
        [tableName],
      );

      columnsResult.rows.forEach((col, idx) => {
        console.log(`   ${idx + 1}. ${col.column_name} (${col.data_type})`);
      });

      // Get row count
      try {
        const countResult = await pool.query(
          `SELECT COUNT(*) as count FROM ${tableName}`,
        );
        console.log(`\n   Total rows: ${countResult.rows[0].count}`);
      } catch (e) {
        console.log(`   Could not count rows: ${e.message}`);
      }

      // Get sample data
      try {
        const sampleResult = await pool.query(
          `SELECT * FROM ${tableName} LIMIT 2`,
        );
        if (sampleResult.rows.length > 0) {
          console.log("\n   Sample data:");
          console.log(JSON.stringify(sampleResult.rows[0], null, 2));
        }
      } catch (e) {
        console.log(`   Could not get sample: ${e.message}`);
      }
    }
  } catch (err) {
    console.log("Error:", err.message);
  } finally {
    pool.end();
  }
}

checkStagingTables();

