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

async function checkTables() {
  try {
    // Get all tables
    const tablesResult = await pool.query(`
      SELECT table_name 
      FROM information_schema.tables 
      WHERE table_schema = 'public' 
      ORDER BY table_name
    `);

    console.log("\n=== Tables in your database ===\n");

    for (const row of tablesResult.rows) {
      console.log(`📋 ${row.table_name}`);

      // Get columns for each table
      const columnsResult = await pool.query(
        `
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_schema = 'public' AND table_name = $1
        ORDER BY ordinal_position
      `,
        [row.table_name],
      );

      columnsResult.rows.forEach((col) => {
        console.log(`   - ${col.column_name} (${col.data_type})`);
      });
      console.log("");
    }
  } catch (err) {
    console.log("Error:", err.message);
  } finally {
    pool.end();
  }
}

checkTables();

