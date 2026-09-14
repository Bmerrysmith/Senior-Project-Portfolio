const jwt = require("jsonwebtoken");
const { JWT_SECRET } = require("../config");

/**
 * Authentication Middleware
 * Verifies JWT token from Authorization header
 */
const authenticate = (req, res, next) => {
  const token = req.headers.authorization?.split(" ")[1];

  if (!token) {
    return res.status(401).json({ error: "Authentication required" });
  }

  try {
    const decoded = jwt.verify(token, JWT_SECRET);
    req.user = decoded;
    next();
  } catch (err) {
    res.status(401).json({ error: "Invalid token" });
  }
};

/**
 * Admin-only Middleware
 * Must be used after authenticate middleware
 */
const requireAdmin = (req, res, next) => {
  if (req.user.role !== "admin") {
    return res.status(403).json({ error: "Admin access required" });
  }
  next();
};

/**
 * Staff or Admin Middleware
 * Blocks viewers from modifying data
 */
const requireStaff = (req, res, next) => {
  if (req.user.role === "viewer") {
    return res.status(403).json({ error: "Insufficient permissions" });
  }
  next();
};

module.exports = {
  authenticate,
  requireAdmin,
  requireStaff,
};
