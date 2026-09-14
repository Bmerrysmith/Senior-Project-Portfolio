# Switch4Good Database System

A full-stack application for managing Switch4Good's educational partnerships, student tracking, and program metrics.

## 📁 Project Structure

```
project/
├── backend/                    # Express.js API Server
│   ├── src/                    # Application source code
│   │   ├── config/             # Configuration modules
│   │   │   ├── database.js     # PostgreSQL connection pool
│   │   │   └── index.js        # Environment config exports
│   │   ├── middleware/         # Express middleware
│   │   │   └── auth.js         # JWT authentication & authorization
│   │   ├── routes/             # API route handlers
│   │   │   ├── index.js        # Route aggregator
│   │   │   ├── auth.routes.js  # Login, verify, password change
│   │   │   ├── admin.routes.js # User management (admin only)
│   │   │   ├── schools.routes.js
│   │   │   ├── programs.routes.js
│   │   │   ├── students.routes.js
│   │   │   ├── staging.routes.js
│   │   │   ├── metrics.routes.js
│   │   │   └── upload.routes.js
│   │   ├── app.js              # Express app configuration
│   │   └── server.js           # Server entry point
│   ├── scripts/                # Database & setup scripts
│   │   ├── setup-admin.js      # Create admin users
│   │   ├── run-schema.js       # Apply database schema
│   │   ├── seed-demo-data.js   # Generate demo data
│   │   └── test-db.js          # Test database connection
│   ├── sql/                    # SQL schema files
│   │   ├── schema-complete.sql # Full database schema
│   │   └── init.sql            # Initial setup SQL
│   ├── db.js                   # Legacy database connection
│   ├── file-upload.js          # File upload processing
│   ├── .env.example            # Environment template
│   └── package.json
│
├── frontend/                   # React + Vite Frontend
│   ├── src/
│   │   ├── components/         # Reusable UI components
│   │   ├── hooks/              # Custom React hooks
│   │   │   ├── useAuth.js      # Authentication hook
│   │   │   ├── useApi.js       # API fetching hook
│   │   │   └── index.js
│   │   ├── services/           # API service layer
│   │   │   └── api.js          # Centralized API calls
│   │   ├── utils/              # Utility functions
│   │   ├── App.jsx             # Main application component
│   │   ├── main.jsx            # React entry point
│   │   └── index.css           # Global styles
│   ├── vite.config.js
│   └── package.json
│
└── db/                         # Database migrations (legacy)
    ├── schema.sql
    └── seed.sql
```

## 🚀 Getting Started

### Prerequisites

- Node.js 18+
- PostgreSQL 14+
- npm or yarn

### Backend Setup

1. **Navigate to backend:**
   ```bash
   cd backend
   ```

2. **Install dependencies:**
   ```bash
   npm install
   ```

3. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your database credentials
   ```

4. **Set up database:**
   ```bash
   npm run db:schema    # Apply schema
   npm run db:seed      # Add demo data (optional)
   npm run admin:setup  # Create admin user
   ```

5. **Start server:**
   ```bash
   npm run dev          # Development (with hot reload)
   npm start            # Production
   ```

### Frontend Setup

1. **Navigate to frontend:**
   ```bash
   cd frontend
   ```

2. **Install dependencies:**
   ```bash
   npm install
   ```

3. **Start development server:**
   ```bash
   npm run dev
   ```

4. **Open browser:**
   - Frontend: http://localhost:3000
   - Backend API: http://localhost:5000

## 📜 NPM Scripts

### Backend

| Script | Description |
|--------|-------------|
| `npm run dev` | Start with nodemon (auto-reload) |
| `npm start` | Start production server |
| `npm run db:schema` | Apply database schema |
| `npm run db:seed` | Seed demo data |
| `npm run db:test` | Test database connection |
| `npm run admin:setup` | Create or manage admin users |

### Frontend

| Script | Description |
|--------|-------------|
| `npm run dev` | Start Vite dev server |
| `npm run build` | Build for production |
| `npm run preview` | Preview production build |

## 🔐 Environment Variables

Create a `.env` file in the backend folder:

```env
# Database
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=your-password
DB_NAME=switch4good
DB_SSL=false              # Set to 'true' for cloud databases

# Server
PORT=5000
NODE_ENV=development

# Authentication
JWT_SECRET=your-secret-key
JWT_EXPIRY=24h
```

## 🔌 API Endpoints

### Authentication
- `POST /api/auth/login` - User login
- `GET /api/auth/verify` - Verify JWT token
- `PATCH /api/auth/password` - Change password

### Admin (requires admin role)
- `GET /api/admin/users` - List all admin users
- `POST /api/admin/users` - Create user
- `PUT /api/admin/users/:id` - Update user
- `DELETE /api/admin/users/:id` - Delete user

### Core Resources
- `/api/schools` - Schools CRUD
- `/api/programs` - Programs CRUD
- `/api/students` - Students CRUD
- `/api/can-metrics` - CAN Metrics CRUD

### Staging Tables
- `/api/staging/program-course`
- `/api/staging/student-tracker`
- `/api/staging/can-metrics`
- `/api/staging/program-directory`

### V2 API (Normalized Schema)
- `/api/v2/semesters`
- `/api/v2/universities`
- `/api/v2/programs`
- `/api/v2/partnerships`
- `/api/v2/dashboard` - Combined metrics

## 👥 User Roles

| Role | Permissions |
|------|-------------|
| `admin` | Full access, user management |
| `staff` | Create, read, update, delete data |
| `viewer` | Read-only access |

## 🛠️ Development

### Adding New Routes

1. Create route file in `backend/src/routes/`
2. Export router from the file
3. Import and mount in `routes/index.js`

### Adding API Services (Frontend)

1. Add method to `frontend/src/services/api.js`
2. Use with `useApi` hook or call directly

## 📝 License

Private - Switch4Good Internal Use Only
