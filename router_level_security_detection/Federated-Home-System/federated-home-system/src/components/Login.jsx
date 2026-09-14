import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import Container from "react-bootstrap/Container";
import Form from "react-bootstrap/Form";
import Button from "react-bootstrap/Button";
import Card from "react-bootstrap/Card";
import { FormCheck } from "react-bootstrap";

// Predefined router configurations
const ROUTER_CONFIGS = {
  mango: {
    name: "Mango",
    id: "mango-001",
    ip: "192.168.1.1",
    defaultUsername: "root",
    defaultPassword: "Paulo@123",
  },
  beryl: {
    name: "GLI Beryl",
    id: "beryl-001",
    ip: "192.168.1.1",
    defaultUsername: "root",
    defaultPassword: "Paulo@123",
  },
};

function Login() {
  const navigate = useNavigate();
  // State for form data
  const [credentials, setCredentials] = useState({
    username: "",
    password: "",
  });
  // State for router configuration
  const [routerConfig, setRouterConfig] = useState({
    name: "",
    id: "",
    ip: "192.168.1.1",
  });
  // State for guest mode
  const [isGuestMode, setIsGuestMode] = useState(false);
  // State for selected router value
  const [selectedRouterValue, setSelectedRouterValue] = useState("");

  const handleRouterSelect = (event) => {
    const value = event.target.value;
    setSelectedRouterValue(value);

    if (value === "") {
      // If "Choose a router..." is selected, clear all router-related data
      setRouterConfig({
        name: "",
        id: "",
        ip: "192.168.1.1",
      });
      setCredentials({
        username: "",
        password: "",
      });
    } else {
      // If a specific router is selected
      const selectedRouter = ROUTER_CONFIGS[value];
      if (selectedRouter) {
        setRouterConfig({
          name: selectedRouter.name,
          id: selectedRouter.id,
          ip: selectedRouter.ip,
        });
        setCredentials({
          username: selectedRouter.defaultUsername,
          password: selectedRouter.defaultPassword,
        });
      }
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();

    if (isGuestMode) {
      // Guest login
      localStorage.setItem("authToken", "guest-token");
      localStorage.setItem("isGuest", "true");
    } else {
      // Regular login
      localStorage.setItem("authToken", "demo-token");
      localStorage.setItem("isGuest", "false");
    }

    // Store router configuration
    if (selectedRouterValue === "") {
      // If no specific router is selected, store a default config
      localStorage.setItem(
        "routerConfig",
        JSON.stringify({
          name: "Default Router",
          id: "default-001",
          ip: "192.168.1.1",
          status: "active",
          info: { message: "Using default router configuration" },
        })
      );
    } else {
      // Store selected router configuration
      localStorage.setItem("routerConfig", JSON.stringify(routerConfig));
    }

    navigate("/");
  };

  return (
    <Container
      className="d-flex align-items-center justify-content-center"
      style={{ minHeight: "100vh" }}
    >
      <Card style={{ width: "500px" }}>
        <Card.Body>
          <h2 className="text-center mb-4">FrED IoT Home System</h2>

          {/* Router Configuration Section */}
          <div className="mb-4">
            <h4 className="mb-3">Router Configuration</h4>
            <Form.Group className="mb-3">
              <Form.Label>Select Router Model</Form.Label>
              <Form.Select
                value={selectedRouterValue}
                onChange={handleRouterSelect}
                required
              >
                <option value="">Choose a router...</option>
                <option value="mango">Mango</option>
                <option value="beryl">GLI Beryl</option>
              </Form.Select>
            </Form.Group>
            {selectedRouterValue !== "" && (
              <>
                <Form.Group className="mb-3">
                  <Form.Label>Router ID</Form.Label>
                  <Form.Control
                    type="text"
                    placeholder="Enter router ID"
                    value={routerConfig.id}
                    onChange={(e) =>
                      setRouterConfig({ ...routerConfig, id: e.target.value })
                    }
                    required
                  />
                </Form.Group>
                <Form.Group className="mb-3">
                  <Form.Label>Router IP</Form.Label>
                  <Form.Control
                    type="text"
                    placeholder="Enter router IP"
                    value={routerConfig.ip}
                    onChange={(e) =>
                      setRouterConfig({ ...routerConfig, ip: e.target.value })
                    }
                    required
                  />
                </Form.Group>
              </>
            )}
          </div>

          {/* Guest Mode Toggle */}
          <FormCheck
            type="switch"
            id="guest-mode-switch"
            label="Continue as Guest"
            checked={isGuestMode}
            onChange={(e) => setIsGuestMode(e.target.checked)}
            className="mb-4"
          />

          {/* Login Form (hidden when in guest mode) */}
          {!isGuestMode && (
            <div className="mb-4">
              <h4 className="mb-3">Login (Optional)</h4>
              <Form.Group className="mb-3">
                <Form.Label>Username</Form.Label>
                <Form.Control
                  type="text"
                  placeholder="Enter username (optional)"
                  value={credentials.username}
                  onChange={(e) =>
                    setCredentials({ ...credentials, username: e.target.value })
                  }
                />
              </Form.Group>
              <Form.Group className="mb-3">
                <Form.Label>Password</Form.Label>
                <Form.Control
                  type="password"
                  placeholder="Enter password (optional)"
                  value={credentials.password}
                  onChange={(e) =>
                    setCredentials({ ...credentials, password: e.target.value })
                  }
                />
              </Form.Group>
            </div>
          )}

          {/* Submit Button */}
          <Button
            variant="primary"
            type="submit"
            className="w-100"
            onClick={handleSubmit}
          >
            {isGuestMode
              ? "Continue as Guest"
              : selectedRouterValue === ""
              ? "Continue Without Router"
              : "Login"}
          </Button>
        </Card.Body>
      </Card>
    </Container>
  );
}

export default Login;
