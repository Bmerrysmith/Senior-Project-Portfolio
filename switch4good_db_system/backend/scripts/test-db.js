require('dotenv').config();
const { Pool } = require('pg');

const pool = new Pool({
  user: process.env.DB_USER,
  password: process.env.DB_PASSWORD,
  host: process.env.DB_HOST,
  port: process.env.DB_PORT,
  database: process.env.DB_NAME,
  ssl: { rejectUnauthorized: false }
});

async function test() {
  try {
    // Test connection
    const result = await pool.query('SELECT current_database(), current_user');
    console.log('Connected to:', result.rows[0]);
    
    // List all databases
    const dbs = await pool.query(`SELECT datname FROM pg_database WHERE datistemplate = false`);
    console.log('\nDatabases available:', dbs.rows.map(r => r.datname).join(', '));
    
    // List all tables in public schema
    const publicTables = await pool.query(`
      SELECT table_name 
      FROM information_schema.tables 
      WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
      ORDER BY table_name
    `);
    
    console.log('\nTables in public schema:');
    if (publicTables.rows.length === 0) {
      console.log('  (No tables in public schema)');
    } else {
      publicTables.rows.forEach(t => console.log(`  - ${t.table_name}`));
    }
    
    // Try to find any user tables
    const anyTables = await pool.query(`
      SELECT schemaname, tablename 
      FROM pg_tables 
      WHERE schemaname NOT IN ('pg_catalog', 'information_schema', 'auth', 'storage', 'realtime', 'vault', 'extensions', 'graphql', 'graphql_public', 'pgbouncer')
      ORDER BY schemaname, tablename
    `);
    
    console.log('\nUser tables (non-system):');
    if (anyTables.rows.length === 0) {
      console.log('  (No user tables found)');
    } else {
      anyTables.rows.forEach(t => console.log(`  - ${t.schemaname}.${t.tablename}`));
    }
    
  } catch (err) {
    console.error('Error:', err.message);
  } finally {
    pool.end();
  }
}

test();

