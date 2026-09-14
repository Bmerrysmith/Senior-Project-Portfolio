import React, { useState } from "react";
import Container from "react-bootstrap/Container";
import Nav from "react-bootstrap/Nav";
import Navbar from "react-bootstrap/Navbar";
import NavDropdown from "react-bootstrap/NavDropdown";
import { useNavigate } from "react-router-dom";
import "../styles/layout.css";

function NavigationBar() {
  const navigate = useNavigate();
  const [expanded, setExpanded] = useState(false);

  // Sample notifications - replace with your actual notifications
  const notifications = [
    {
      id: 1,
      message: "Router Status Update",
      time: "5 minutes ago",
    },
    {
      id: 2,
      message: "Security Alert",
      time: "1 hour ago",
    },
  ];

  const handleExit = () => {
    localStorage.removeItem("authToken");
    sessionStorage.clear();
    navigate("/login");
  };

  const handleSelect = () => {
    setExpanded(false);
  };

  return (
    <Navbar
      expand="lg"
      className="custom-navbar"
      fixed="top"
      expanded={expanded}
      onSelect={handleSelect}
    >
      <Container>
        <Navbar.Brand href="/" className="brand-logo">
          <span className="brand-icon">🏠</span>
          <span>FrED IoT Home System</span>
        </Navbar.Brand>

        <Navbar.Toggle
          aria-controls="navbar-nav"
          onClick={() => setExpanded(!expanded)}
        />

        <Navbar.Collapse id="navbar-nav">
          <Nav className="me-auto">
            <Nav.Link href="#iot-devices">IoT Devices</Nav.Link>
            <Nav.Link href="#network-status">Network Status</Nav.Link>
            <NavDropdown
              title="More Options"
              id="nav-dropdown"
              onClick={(e) => {
                if (e.target.classList.contains("dropdown-item")) {
                  setExpanded(false);
                }
              }}
            >
              <NavDropdown.Item href="/settings">Settings</NavDropdown.Item>
              <NavDropdown.Item href="/activity">
                Activity Logs
              </NavDropdown.Item>
              <NavDropdown.Item href="/alerts">Alerts</NavDropdown.Item>
              <NavDropdown.Item href="/support">Support</NavDropdown.Item>
            </NavDropdown>
          </Nav>

          <Nav>
            <NavDropdown
              align="end"
              title={
                <div className="notification-icon">
                  <span>🔔</span>
                  {notifications.length > 0 && (
                    <span className="notification-badge" />
                  )}
                </div>
              }
              id="notifications-dropdown"
              onClick={(e) => {
                if (e.target.classList.contains("dropdown-item")) {
                  setExpanded(false);
                }
              }}
            >
              {notifications.map((notification) => (
                <NavDropdown.Item key={notification.id}>
                  <div className="notification-message">
                    {notification.message}
                  </div>
                  <div className="notification-time">{notification.time}</div>
                </NavDropdown.Item>
              ))}
              <NavDropdown.Divider />
              <NavDropdown.Item className="view-all">
                View All Notifications
              </NavDropdown.Item>
            </NavDropdown>

            <Nav.Link className="exit-button" onClick={handleExit}>
              Exit <span>↪</span>
            </Nav.Link>
          </Nav>
        </Navbar.Collapse>
      </Container>
    </Navbar>
  );
}

export default NavigationBar;
