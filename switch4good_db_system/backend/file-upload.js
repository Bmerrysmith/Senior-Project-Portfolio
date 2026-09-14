/**
 * File Upload Handler for CSV/Excel Import
 * Switch4Good Impact Tracking System
 * 
 * Handles parsing and importing data from Excel/CSV files
 * into the appropriate database tables based on column detection.
 */

const multer = require('multer');
const XLSX = require('xlsx');
const { parse } = require('csv-parse/sync');
const path = require('path');
const fs = require('fs');
const pool = require('./db');

// Configure multer for file uploads
const storage = multer.memoryStorage(); // Store in memory for processing

const fileFilter = (req, file, cb) => {
  const allowedTypes = [
    'text/csv',
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/csv',
    'text/plain'
  ];
  
  const allowedExtensions = ['.csv', '.xls', '.xlsx'];
  const ext = path.extname(file.originalname).toLowerCase();
  
  if (allowedExtensions.includes(ext) || allowedTypes.includes(file.mimetype)) {
    cb(null, true);
  } else {
    cb(new Error('Invalid file type. Only CSV, XLS, and XLSX files are allowed.'), false);
  }
};

const upload = multer({
  storage: storage,
  fileFilter: fileFilter,
  limits: {
    fileSize: 10 * 1024 * 1024 // 10MB max
  }
});

// ============================================================================
// TABLE DETECTION & COLUMN MAPPING
// ============================================================================

/**
 * Column patterns for each table
 * Maps Excel/CSV column headers to database columns
 */
const TABLE_MAPPINGS = {
  // Schools table
  schools: {
    identifyColumns: ['school', 'university', 'institution', 'college'],
    requiredColumns: ['school_name'],
    primaryKey: 'school_id',
    columnMap: {
      'school': 'school_name',
      'school name': 'school_name',
      'university': 'school_name',
      'university name': 'school_name',
      'institution': 'school_name',
      'college': 'school_name',
      'name': 'school_name'
    },
    tableName: 'schools',
    uniqueConstraint: 'school_name'
  },

  // Programs table
  programs: {
    identifyColumns: ['program', 'program name', 'program type'],
    requiredColumns: ['program_name'],
    primaryKey: 'program_id',
    columnMap: {
      'program': 'program_name',
      'program name': 'program_name',
      'name': 'program_name',
      'school': 'school_name',
      'university': 'school_name',
      'website': 'website',
      'url': 'website',
      'type': 'program_type',
      'program type': 'program_type',
      'needs formalization': 'needs_formalization',
      'needs_formalization': 'needs_formalization',
      'notes': 'notes'
    },
    tableName: 'programs',
    lookupFields: {
      'school_name': { table: 'schools', column: 'school_name', fk: 'school_id', pk: 'school_id' }
    }
  },

  // Students table
  students: {
    identifyColumns: ['student', 'student name', 'full name', 'pronouns', 't-shirt', 'areas of interest'],
    requiredColumns: ['full_name'],
    primaryKey: 'student_id',
    columnMap: {
      'name': 'full_name',
      'full name': 'full_name',
      'student name': 'full_name',
      'student': 'full_name',
      'email': 'email',
      'email address': 'email',
      'student email': 'email',
      'pronouns': 'pronouns',
      't-shirt': 'tshirt_size',
      't-shirt size': 'tshirt_size',
      'tshirt': 'tshirt_size',
      'shirt size': 'tshirt_size',
      'tshirt size': 'tshirt_size',
      'year': 'year_in_school',
      'year in school': 'year_in_school',
      'class year': 'year_in_school',
      'grade': 'year_in_school',
      'areas of interest': 'areas_of_interest',
      'interests': 'areas_of_interest'
    },
    tableName: 'students',
    uniqueConstraint: 'email'
  },

  // CAN Metrics table
  can_metrics: {
    identifyColumns: ['impression', 'touchpoints', 'engagements', 'conversions', 'can metric'],
    requiredColumns: ['impression'],
    primaryKey: 'metric_id',
    columnMap: {
      'date': 'metric_date',
      'metric date': 'metric_date',
      'is ongoing': 'is_ongoing',
      'ongoing': 'is_ongoing',
      'impression': 'impression',
      'touchpoints': 'touchpoints',
      'engagements': 'engagements',
      'conversions': 'conversions',
      'notes': 'notes'
    },
    tableName: 'can_metrics'
  },

  // Staff contacts table
  staff_contacts: {
    identifyColumns: ['staff', 'staff name', 'coordinator', 'sg4 staff', 'role title'],
    requiredColumns: ['full_name'],
    primaryKey: 'staff_id',
    columnMap: {
      'name': 'full_name',
      'full name': 'full_name',
      'staff name': 'full_name',
      'staff': 'full_name',
      'sg4 staff': 'full_name',
      'coordinator': 'full_name',
      'email': 'email',
      'staff email': 'email',
      'role': 'role_title',
      'role title': 'role_title',
      'position': 'role_title',
      'title': 'role_title',
      'organization': 'organization',
      'notes': 'notes'
    },
    tableName: 'staff_contacts'
  }
};

// ============================================================================
// FILE PARSING FUNCTIONS
// ============================================================================

/**
 * Parse uploaded file to extract data
 */
function parseFile(buffer, filename) {
  const ext = path.extname(filename).toLowerCase();
  
  if (ext === '.csv') {
    return parseCSV(buffer);
  } else if (ext === '.xlsx' || ext === '.xls') {
    return parseExcel(buffer);
  }
  throw new Error('Unsupported file type');
}

/**
 * Parse CSV file
 */
function parseCSV(buffer) {
  const content = buffer.toString('utf-8');
  const records = parse(content, {
    columns: true,
    skip_empty_lines: true,
    trim: true,
    relax_column_count: true
  });
  return records;
}

/**
 * Parse Excel file (supports multiple sheets)
 */
function parseExcel(buffer) {
  const workbook = XLSX.read(buffer, { type: 'buffer', cellDates: true });
  const allData = {};
  
  workbook.SheetNames.forEach(sheetName => {
    const worksheet = workbook.Sheets[sheetName];
    const data = XLSX.utils.sheet_to_json(worksheet, { 
      defval: null,
      dateNF: 'yyyy-mm-dd'
    });
    if (data.length > 0) {
      allData[sheetName] = data;
    }
  });
  
  return allData;
}

/**
 * Normalize column headers for matching
 */
function normalizeHeader(header) {
  return header
    .toLowerCase()
    .trim()
    .replace(/[_-]/g, ' ')
    .replace(/\s+/g, ' ');
}

/**
 * Detect table type based on column headers
 */
function detectTableType(columns) {
  const normalizedColumns = columns.map(normalizeHeader);
  let bestMatch = null;
  let bestScore = 0;
  
  for (const [tableKey, mapping] of Object.entries(TABLE_MAPPINGS)) {
    let score = 0;
    
    // Check for identifying columns
    for (const identifyCol of mapping.identifyColumns) {
      if (normalizedColumns.some(col => col.includes(identifyCol))) {
        score += 3;
      }
    }
    
    // Check for mapped columns
    for (const [excelCol, dbCol] of Object.entries(mapping.columnMap)) {
      if (normalizedColumns.some(col => col === excelCol || col.includes(excelCol))) {
        score += 1;
      }
    }
    
    if (score > bestScore) {
      bestScore = score;
      bestMatch = tableKey;
    }
  }
  
  return bestScore >= 2 ? bestMatch : null;
}

/**
 * Map row data to database columns
 */
function mapRowToDatabase(row, tableKey) {
  const mapping = TABLE_MAPPINGS[tableKey];
  if (!mapping) return null;
  
  const dbRow = {};
  
  for (const [excelCol, value] of Object.entries(row)) {
    const normalizedCol = normalizeHeader(excelCol);
    
    for (const [mappedCol, dbCol] of Object.entries(mapping.columnMap)) {
      if (normalizedCol === mappedCol || normalizedCol.includes(mappedCol)) {
        dbRow[dbCol] = cleanValue(value, dbCol);
        break;
      }
    }
  }
  
  return dbRow;
}

/**
 * Clean and format values for database
 */
function cleanValue(value, columnName) {
  if (value === null || value === undefined || value === '') {
    return null;
  }
  
  // Handle boolean columns
  if (columnName.includes('is_') || ['ty_note_sent', 'includes_dairy_content', 'is_active', 'is_current'].includes(columnName)) {
    if (typeof value === 'boolean') return value;
    const strVal = String(value).toLowerCase().trim();
    return ['yes', 'true', '1', 'y', 'x', '✓', '✔'].includes(strVal);
  }
  
  // Handle date columns
  if (columnName.includes('date') || columnName.includes('_at')) {
    if (value instanceof Date) {
      return value.toISOString().split('T')[0];
    }
    const dateStr = String(value).trim();
    const parsed = new Date(dateStr);
    return isNaN(parsed.getTime()) ? null : parsed.toISOString().split('T')[0];
  }
  
  // Handle numeric columns
  if (['students_participating', 'total_in_class', 'credits', 'max_students'].includes(columnName)) {
    const num = parseInt(value, 10);
    return isNaN(num) ? null : num;
  }
  
  // Handle full name splitting
  if (columnName === 'full_name') {
    return String(value).trim();
  }
  
  // Default: return as string
  return String(value).trim();
}

// ============================================================================
// DATABASE IMPORT FUNCTIONS
// ============================================================================

/**
 * Look up foreign key ID from related table
 */
async function lookupForeignKey(table, column, value, pk) {
  if (!value) return null;
  
  try {
    const result = await pool.query(
      `SELECT ${pk} as id FROM ${table} WHERE LOWER(${column}) = LOWER($1)`,
      [String(value).trim()]
    );
    return result.rows.length > 0 ? result.rows[0].id : null;
  } catch (err) {
    console.error(`Error looking up ${table}.${column}:`, err.message);
    return null;
  }
}

/**
 * Insert data into database with conflict handling
 */
async function importToDatabase(data, tableKey, userId) {
  const mapping = TABLE_MAPPINGS[tableKey];
  if (!mapping) throw new Error(`Unknown table type: ${tableKey}`);
  
  const results = {
    success: 0,
    errors: [],
    skipped: 0,
    created: [],
    updated: []
  };
  
  for (let i = 0; i < data.length; i++) {
    const row = data[i];
    const rowNum = i + 2; // Account for header row
    
    try {
      const dbRow = mapRowToDatabase(row, tableKey);
      
      if (!dbRow || Object.keys(dbRow).length === 0) {
        results.skipped++;
        continue;
      }
      
      // Handle foreign key lookups
      if (mapping.lookupFields) {
        for (const [field, config] of Object.entries(mapping.lookupFields)) {
          if (dbRow[field]) {
            const fkId = await lookupForeignKey(config.table, config.column, dbRow[field], config.pk);
            if (fkId) {
              dbRow[config.fk] = fkId;
            } else {
              results.errors.push({
                row: rowNum,
                error: `${field} "${dbRow[field]}" not found in ${config.table}`
              });
              continue;
            }
            delete dbRow[field];
          }
        }
      }
      
      // Build dynamic INSERT query
      const columns = Object.keys(dbRow).filter(k => dbRow[k] !== undefined);
      const values = columns.map(k => dbRow[k]);
      const placeholders = columns.map((_, idx) => `$${idx + 1}`);
      
      if (columns.length === 0) {
        results.skipped++;
        continue;
      }
      
      // Use INSERT ... ON CONFLICT for upsert behavior where applicable
      let query = `INSERT INTO ${mapping.tableName} (${columns.join(', ')}) VALUES (${placeholders.join(', ')})`;
      
      // Add conflict handling for tables with unique constraints
      if (mapping.uniqueConstraint && columns.includes(mapping.uniqueConstraint)) {
        const uniqueCol = mapping.uniqueConstraint;
        const updateCols = columns.filter(c => c !== uniqueCol);
        if (updateCols.length > 0) {
          query += ` ON CONFLICT (${uniqueCol}) DO UPDATE SET `;
          query += updateCols.map(c => `${c} = EXCLUDED.${c}`).join(', ');
        } else {
          query += ` ON CONFLICT (${uniqueCol}) DO NOTHING`;
        }
      }
      
      query += ` RETURNING ${mapping.primaryKey}`;
      
      const result = await pool.query(query, values);
      results.success++;
      results.created.push({ id: result.rows[0][mapping.primaryKey], row: rowNum });
      
    } catch (err) {
      results.errors.push({
        row: rowNum,
        error: err.message,
        data: row
      });
    }
  }
  
  return results;
}

/**
 * Process uploaded file and import to database
 */
async function processUpload(buffer, filename, targetTable, userId) {
  const results = {
    filename,
    targetTable,
    sheets: [],
    totalRows: 0,
    imported: 0,
    errors: [],
    warnings: []
  };
  
  try {
    const ext = path.extname(filename).toLowerCase();
    
    if (ext === '.csv') {
      // Single CSV file
      const data = parseCSV(buffer);
      
      if (data.length === 0) {
        throw new Error('No data found in file');
      }
      
      const columns = Object.keys(data[0]);
      const detectedTable = targetTable || detectTableType(columns);
      
      if (!detectedTable) {
        throw new Error('Could not detect target table. Please specify the table type.');
      }
      
      results.targetTable = detectedTable;
      results.totalRows = data.length;
      
      const importResult = await importToDatabase(data, detectedTable, userId);
      
      results.sheets.push({
        name: 'CSV Data',
        table: detectedTable,
        rows: data.length,
        imported: importResult.success,
        skipped: importResult.skipped,
        errors: importResult.errors
      });
      
      results.imported = importResult.success;
      results.errors = importResult.errors;
      
    } else {
      // Excel file with potentially multiple sheets
      const sheetsData = parseExcel(buffer);
      
      for (const [sheetName, data] of Object.entries(sheetsData)) {
        if (data.length === 0) continue;
        
        const columns = Object.keys(data[0]);
        
        // Try to detect table from sheet name first, then from columns
        let detectedTable = null;
        const sheetNameLower = sheetName.toLowerCase();
        
        // Check if sheet name matches a table
        for (const [tableKey, mapping] of Object.entries(TABLE_MAPPINGS)) {
          if (sheetNameLower.includes(tableKey) || 
              sheetNameLower.includes(mapping.tableName) ||
              mapping.identifyColumns.some(col => sheetNameLower.includes(col))) {
            detectedTable = tableKey;
            break;
          }
        }
        
        // Fall back to column detection
        if (!detectedTable) {
          detectedTable = detectTableType(columns);
        }
        
        // Use specified target table if provided
        if (targetTable && !results.sheets.length) {
          detectedTable = targetTable;
        }
        
        if (!detectedTable) {
          results.warnings.push(`Sheet "${sheetName}" could not be mapped to a table`);
          continue;
        }
        
        results.totalRows += data.length;
        
        const importResult = await importToDatabase(data, detectedTable, userId);
        
        results.sheets.push({
          name: sheetName,
          table: detectedTable,
          rows: data.length,
          imported: importResult.success,
          skipped: importResult.skipped,
          errors: importResult.errors
        });
        
        results.imported += importResult.success;
        results.errors.push(...importResult.errors.map(e => ({ ...e, sheet: sheetName })));
      }
    }
    
  } catch (err) {
    results.errors.push({ error: err.message });
  }
  
  return results;
}

/**
 * Preview file contents without importing
 */
async function previewUpload(buffer, filename, targetTable) {
  const preview = {
    filename,
    sheets: [],
    suggestions: []
  };
  
  try {
    const ext = path.extname(filename).toLowerCase();
    
    if (ext === '.csv') {
      const data = parseCSV(buffer);
      const columns = Object.keys(data[0] || {});
      const detectedTable = targetTable || detectTableType(columns);
      
      preview.sheets.push({
        name: 'CSV Data',
        columns: columns,
        detectedTable: detectedTable,
        tableName: detectedTable ? TABLE_MAPPINGS[detectedTable].tableName : null,
        rowCount: data.length,
        preview: data.slice(0, 5),
        columnMapping: detectedTable ? mapColumnsToDb(columns, detectedTable) : null
      });
      
    } else {
      const sheetsData = parseExcel(buffer);
      
      for (const [sheetName, data] of Object.entries(sheetsData)) {
        if (data.length === 0) continue;
        
        const columns = Object.keys(data[0]);
        
        // Detect table from sheet name or columns
        let detectedTable = null;
        const sheetNameLower = sheetName.toLowerCase();
        
        for (const [tableKey, mapping] of Object.entries(TABLE_MAPPINGS)) {
          if (sheetNameLower.includes(tableKey) || 
              sheetNameLower.includes(mapping.tableName) ||
              mapping.identifyColumns.some(col => sheetNameLower.includes(col))) {
            detectedTable = tableKey;
            break;
          }
        }
        
        if (!detectedTable) {
          detectedTable = detectTableType(columns);
        }
        
        preview.sheets.push({
          name: sheetName,
          columns: columns,
          detectedTable: detectedTable,
          tableName: detectedTable ? TABLE_MAPPINGS[detectedTable].tableName : null,
          rowCount: data.length,
          preview: data.slice(0, 5),
          columnMapping: detectedTable ? mapColumnsToDb(columns, detectedTable) : null
        });
      }
    }
    
  } catch (err) {
    preview.error = err.message;
  }
  
  return preview;
}

/**
 * Map Excel columns to database columns for preview
 */
function mapColumnsToDb(excelColumns, tableKey) {
  const mapping = TABLE_MAPPINGS[tableKey];
  if (!mapping) return null;
  
  const result = {};
  
  for (const excelCol of excelColumns) {
    const normalizedCol = normalizeHeader(excelCol);
    let matched = false;
    
    for (const [mappedCol, dbCol] of Object.entries(mapping.columnMap)) {
      if (normalizedCol === mappedCol || normalizedCol.includes(mappedCol)) {
        result[excelCol] = { dbColumn: dbCol, matched: true };
        matched = true;
        break;
      }
    }
    
    if (!matched) {
      result[excelCol] = { dbColumn: null, matched: false };
    }
  }
  
  return result;
}

/**
 * Get list of supported tables with their expected columns
 */
function getSupportedTables() {
  const tables = {};
  
  for (const [key, mapping] of Object.entries(TABLE_MAPPINGS)) {
    tables[key] = {
      tableName: mapping.tableName,
      identifyColumns: mapping.identifyColumns,
      requiredColumns: mapping.requiredColumns,
      exampleHeaders: Object.keys(mapping.columnMap).slice(0, 10)
    };
  }
  
  return tables;
}

module.exports = {
  upload,
  processUpload,
  previewUpload,
  getSupportedTables,
  TABLE_MAPPINGS
};
