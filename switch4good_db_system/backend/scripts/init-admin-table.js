/**
 * One-time setup script to create admin_users table and seed default users
 */
const pool = require('../db');
const bcrypt = require('bcryptjs');

async function setup() {
  try {
    console.log('Creating admin_users table...');
    
    await pool.query(`
      CREATE TABLE IF NOT EXISTS admin_users (
        id SERIAL PRIMARY KEY,
        username VARCHAR(50) UNIQUE NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        email VARCHAR(255) UNIQUE,
        name VARCHAR(255) NOT NULL,
        role VARCHAR(50) NOT NULL DEFAULT 'viewer',
        is_active BOOLEAN DEFAULT TRUE,
        failed_login_attempts INTEGER DEFAULT 0,
        locked_until TIMESTAMP,
        last_login TIMESTAMP,
        password_changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
    `);
    console.log('✓ Table created');

    await pool.query('CREATE INDEX IF NOT EXISTS idx_admin_users_username ON admin_users(username)');
    await pool.query('CREATE INDEX IF NOT EXISTS idx_admin_users_email ON admin_users(email)');
    console.log('✓ Indexes created');

    // Check if users already exist
    const existing = await pool.query('SELECT COUNT(*) FROM admin_users');
    if (parseInt(existing.rows[0].count) > 0) {
      console.log('✓ Admin users already exist, skipping seed data');
    } else {
      // Insert default users with password 'ChangeMe123!'
      const hash = await bcrypt.hash('ChangeMe123!', 12);
      
      await pool.query(`
        INSERT INTO admin_users (username, password_hash, email, name, role, is_active) VALUES
        ('admin', $1, 'admin@switch4good.org', 'Admin User', 'admin', TRUE),
        ('lucy', $1, 'lucy@switch4good.org', 'Lucy Whitney', 'staff', TRUE),
        ('gianna', $1, 'gianna@switch4good.org', 'Gianna Klein', 'staff', TRUE),
        ('viewer', $1, 'viewer@switch4good.org', 'Viewer Account', 'viewer', TRUE)
      `, [hash]);
      console.log('✓ Default users created:');
      console.log('  - admin (role: admin)');
      console.log('  - lucy (role: staff)');
      console.log('  - gianna (role: staff)');
      console.log('  - viewer (role: viewer)');
      console.log('\nDefault password for all users: ChangeMe123!');
      console.log('Please change these passwords immediately!');
    }

    await pool.end();
    console.log('\n✓ Setup complete!');
  } catch (err) {
    console.error('Error:', err.message);
    process.exit(1);
  }
}

setup();

