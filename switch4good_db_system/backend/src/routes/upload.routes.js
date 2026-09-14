const router = require("express").Router();
const { upload, processUpload, previewUpload, getSupportedTables } = require("../../file-upload");
const { authenticate, requireAdmin } = require("../middleware/auth");

router.use(authenticate);

/**
 * @route   GET /api/upload/tables
 * @desc    Get list of supported tables for upload
 */
router.get("/tables", (req, res) => {
  const tables = getSupportedTables();
  res.json(tables);
});

/**
 * @route   POST /api/upload/preview
 * @desc    Preview file before importing (with column detection)
 */
router.post("/preview", upload.single("file"), async (req, res) => {
  try {
    if (!req.file) {
      return res.status(400).json({ error: "No file uploaded" });
    }

    const targetTable = req.body.targetTable || null;
    const preview = await previewUpload(req.file.buffer, req.file.originalname, targetTable);
    res.json(preview);
  } catch (err) {
    console.error("Preview error:", err);
    res.status(500).json({ error: err.message });
  }
});

/**
 * @route   POST /api/upload/import
 * @desc    Import file data to database (admin only)
 */
router.post("/import", requireAdmin, upload.single("file"), async (req, res) => {
  try {
    if (!req.file) {
      return res.status(400).json({ error: "No file uploaded" });
    }

    const targetTable = req.body.targetTable || null;
    const result = await processUpload(req.file.buffer, req.file.originalname, targetTable, req.user.id);

    console.log(`File import by ${req.user.username}:`, {
      filename: req.file.originalname,
      imported: result.imported,
      errors: result.errors.length,
    });

    res.json(result);
  } catch (err) {
    console.error("Import error:", err);
    res.status(500).json({ error: err.message });
  }
});

/**
 * @route   POST /api/upload/:table
 * @desc    Upload to specific table (admin only)
 */
router.post("/:table", requireAdmin, upload.single("file"), async (req, res) => {
  try {
    if (!req.file) {
      return res.status(400).json({ error: "No file uploaded" });
    }

    const targetTable = req.params.table;
    const supportedTables = getSupportedTables();

    if (!supportedTables[targetTable]) {
      return res.status(400).json({
        error: `Unsupported table: ${targetTable}`,
        supportedTables: Object.keys(supportedTables),
      });
    }

    const result = await processUpload(req.file.buffer, req.file.originalname, targetTable, req.user.id);
    res.json(result);
  } catch (err) {
    console.error("Import error:", err);
    res.status(500).json({ error: err.message });
  }
});

/**
 * @route   GET /api/upload/history
 * @desc    Get upload history (admin only)
 */
router.get("/history", requireAdmin, async (req, res) => {
  try {
    res.json({
      message: "Upload history feature - logs stored in server console",
      note: "Consider adding an upload_log table for persistent tracking",
    });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

module.exports = router;
