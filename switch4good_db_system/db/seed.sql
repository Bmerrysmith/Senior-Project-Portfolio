-- Add a single test user
INSERT INTO users (name, email, role) VALUES
('Test User', 'test@example.com', 'admin');

-- Add a single test project
INSERT INTO projects (name, description, owner_id) VALUES
('Test Project', 'Just a sample project', 1);

-- Add a single test task
INSERT INTO tasks (project_id, title, completed) VALUES
(1, 'Sample Task', FALSE);
