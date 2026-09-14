// App.js
import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import "bootstrap/dist/css/bootstrap.min.css"; // Import Bootstrap CSS
import "./styles/styles.css"; // Import your custom CSS
import "./styles/layout.css";
import Navbar from "./components/Navbar";
import Login from "./components/Login";
import SecurityCard from "./components/SecurityCard";
import DeviceList from "./components/DeviceList";
import TrafficMonitoring from "./components/TrafficMonitoring";
import DevicesAtRisk from "./components/BandwidthUsage";
import ConsoleOutput from "./components/console";
import FetchDataButton from "./components/fetchData";
import SystemData from "./components/systemData";

// Protected Route component with guest access support
const ProtectedRoute = ({ children }) => {
  // Check for either regular auth token or guest token
  const isAuthenticated = localStorage.getItem("authToken");
  // Check if router configuration exists
  const hasRouterConfig = localStorage.getItem("routerConfig");
  // Allow access if either authenticated or has router config
  if (isAuthenticated && hasRouterConfig) {
    return children;
  }

  // Redirect to login if no authentication or router config
  return <Navigate to="/login" />;
};

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <>
                <Navbar />
                <div className="main-container">
                  <div className="container">
                    <div className="row">
                      <div className="col-md-4">
                        <h3 className="mb-4">🛡️ Network & Device Security</h3>
                        <SecurityCard />
                        <DevicesAtRisk />
                        <h3 className="mt-4 mb-3">🖳 System Console</h3>
                        <ConsoleOutput />
                      </div>
                      <div className="col-md-8">
                        <TrafficMonitoring />
                        <DeviceList />
                      </div>
                      <SystemData />
                    </div>
                  </div>
                </div>
              </>
            </ProtectedRoute>
          }
        />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
