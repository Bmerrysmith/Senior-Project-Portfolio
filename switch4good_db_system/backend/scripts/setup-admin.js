/**
 * Admin User Setup Script
 * 
 * This script creates or resets admin users in the database.
 * Run with: node setup-admin.js
 * 
 * Usage:
 *   node setup-admin.js create <username> <password> <name> [role] [email]
 *   node setup-admin.js reset-password <username> <new-password>
 *   node setup-admin.js list
 *   node setup-admin.js init  (creates default admin if no users exist)
 */

const pool = require("../db");
const bcrypt = require("bcryptjs");
const readline = require("readline");

const rl = readline.createInterface({
  input: process.stdin,
  output: process.stdout,
});

function prompt(question) {
  return new Promise((resolve) => {
    rl.question(question, (answer) => {
      resolve(answer);
    });
  });
}

async function createAdminUser(username, password, name, role = "admin", email = null) {
  try {
    // Validate inputs
    if (!username || !password || !name) {
      console.error("Error: Username, password, and name are required");
      return false;
    }

    if (password.length < 8) {
      console.error("Error: Password must be at least 8 characters");
      return false;
    }

    const validRoles = ["admin", "staff", "viewer"];
    if (!validRoles.includes(role)) {
      console.error("Error: Role must be admin, staff, or viewer");
      return false;
    }

    // Check if username exists
    const existing = await pool.query(
      "SELECT id FROM admin_users WHERE username = $1",
      [username.toLowerCase()]
    );

    if (existing.rows.length > 0) {
      console.error(`Error: Username '${username}' already exists`);
      return false;
    }

    // Hash password with cost factor 12
    const passwordHash = await bcrypt.hash(password, 12);

    // Insert user
    const result = await pool.query(
      `INSERT INTO admin_users (username, password_hash, email, name, role) 
       VALUES ($1, $2, $3, $4, $5) 
       RETURNING id, username, name, role`,
      [username.toLowerCase(), passwordHash, email?.toLowerCase(), name, role]
    );

    console.log("\n✓ Admin user created successfully!");
    console.log(`  ID: ${result.rows[0].id}`);
    console.log(`  Username: ${result.rows[0].username}`);
    console.log(`  Name: ${result.rows[0].name}`);
    console.log(`  Role: ${result.rows[0].role}`);
    return true;
  } catch (err) {
    console.error("Error creating admin user:", err.message);
    return false;
  }
}

async function resetPassword(username, newPassword) {
  try {
    if (!username || !newPassword) {
      console.error("Error: Username and new password are required");
      return false;
    }

    if (newPassword.length < 8) {
      console.error("Error: Password must be at least 8 characters");
      return false;
    }

    // Check if user exists
    const existing = await pool.query(
      "SELECT id, name FROM admin_users WHERE username = $1",
      [username.toLowerCase()]
    );

    if (existing.rows.length === 0) {
      console.error(`Error: Username '${username}' not found`);
      return false;
    }

    // Hash new password
    const passwordHash = await bcrypt.hash(newPassword, 12);

    // Update password
    await pool.query(
      `UPDATE admin_users 
       SET password_hash = $1, 
           password_changed_at = CURRENT_TIMESTAMP,
           failed_login_attempts = 0,
           locked_until = NULL
       WHERE username = $2`,
      [passwordHash, username.toLowerCase()]
    );

    console.log(`\n✓ Password reset for user '${username}' (${existing.rows[0].name})`);
    return true;
  } catch (err) {
    console.error("Error resetting password:", err.message);
    return false;
  }
}

async function listUsers() {
  try {
    const result = await pool.query(`
      SELECT id, username, name, email, role, is_active, 
             last_login, failed_login_attempts, locked_until
      FROM admin_users 
      ORDER BY id
    `);

    if (result.rows.length === 0) {
      console.log("\nNo admin users found in the database.");
      return;
    }

    console.log("\n=== Admin Users ===\n");
    result.rows.forEach((user) => {
      const status = user.is_active ? "Active" : "Disabled";
      const locked = user.locked_until && new Date(user.locked_until) > new Date() 
        ? " (LOCKED)" 
        : "";
      console.log(`ID: ${user.id}`);
      console.log(`  Username: ${user.username}`);
      console.log(`  Name: ${user.name}`);
      console.log(`  Email: ${user.email || "(not set)"}`);
      console.log(`  Role: ${user.role}`);
      console.log(`  Status: ${status}${locked}`);
      console.log(`  Last Login: ${user.last_login ? new Date(user.last_login).toLocaleString() : "Never"}`);
      console.log("");
    });
  } catch (err) {
    console.error("Error listing users:", err.message);
  }
}

async function initializeAdmin() {
  try {
    // Check if any admin users exist
    const existing = await pool.query("SELECT COUNT(*) FROM admin_users");
    
    if (parseInt(existing.rows[0].count) > 0) {
      console.log("\nAdmin users already exist. Use 'list' to see them.");
      return;
    }

    console.log("\n=== Initial Admin Setup ===\n");
    console.log("No admin users found. Let's create the first admin account.\n");

    const username = await prompt("Enter admin username: ");
    const password = await prompt("Enter admin password (min 8 chars): ");
    const name = await prompt("Enter admin's full name: ");
    const email = await prompt("Enter admin email (optional, press Enter to skip): ");

    await createAdminUser(
      username.trim(),
      password,
      name.trim(),
      "admin",
      email.trim() || null
    );
  } catch (err) {
    console.error("Error initializing admin:", err.message);
  }
}

async function interactiveCreate() {
  console.log("\n=== Create Admin User ===\n");

  const username = await prompt("Username: ");
  const password = await prompt("Password (min 8 chars): ");
  const name = await prompt("Full name: ");
  const role = await prompt("Role (admin/staff/viewer) [viewer]: ");
  const email = await prompt("Email (optional): ");

  await createAdminUser(
    username.trim(),
    password,
    name.trim(),
    role.trim() || "viewer",
    email.trim() || null
  );
}

async function interactiveReset() {
  console.log("\n=== Reset Password ===\n");

  const username = await prompt("Username: ");
  const password = await prompt("New password (min 8 chars): ");

  await resetPassword(username.trim(), password);
}

async function showHelp() {
  console.log(`
Admin User Setup Script
=======================

Commands:
  node setup-admin.js                    Interactive menu
  node setup-admin.js init               Initialize first admin (if none exist)
  node setup-admin.js list               List all admin users
  node setup-admin.js create             Interactive user creation
  node setup-admin.js reset              Interactive password reset

With arguments:
  node setup-admin.js create <username> <password> <name> [role] [email]
  node setup-admin.js reset-password <username> <new-password>

Roles:
  - admin:  Full access, can manage other users
  - staff:  Can view and edit data
  - viewer: Read-only access

Security Notes:
  - Passwords must be at least 8 characters
  - Passwords are hashed with bcrypt (cost factor 12)
  - Failed login attempts lock accounts after 5 tries
  `);
}

async function main() {
  const args = process.argv.slice(2);
  const command = args[0];

  try {
    // Test database connection first
    await pool.query("SELECT 1");

    switch (command) {
      case "create":
        if (args.length >= 4) {
          await createAdminUser(args[1], args[2], args[3], args[4] || "admin", args[5]);
        } else {
          await interactiveCreate();
        }
        break;

      case "reset-password":
        if (args.length >= 3) {
          await resetPassword(args[1], args[2]);
        } else {
          await interactiveReset();
        }
        break;

      case "reset":
        await interactiveReset();
        break;

      case "list":
        await listUsers();
        break;

      case "init":
        await initializeAdmin();
        break;

      case "help":
      case "--help":
      case "-h":
        await showHelp();
        break;

      default:
        // Interactive menu
        console.log("\n=== Admin User Management ===\n");
        console.log("1. List users");
        console.log("2. Create user");
        console.log("3. Reset password");
        console.log("4. Initialize (first admin)");
        console.log("5. Help");
        console.log("6. Exit");
        
        const choice = await prompt("\nSelect option (1-6): ");
        
        switch (choice.trim()) {
          case "1":
            await listUsers();
            break;
          case "2":
            await interactiveCreate();
            break;
          case "3":
            await interactiveReset();
            break;
          case "4":
            await initializeAdmin();
            break;
          case "5":
            await showHelp();
            break;
          case "6":
            console.log("Goodbye!");
            break;
          default:
            console.log("Invalid option");
        }
    }
  } catch (err) {
    console.error("Database connection error:", err.message);
    console.error("Make sure PostgreSQL is running and .env is configured correctly.");
  } finally {
    rl.close();
    await pool.end();
  }
}

main();


