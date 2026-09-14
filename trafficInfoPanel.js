/**
 * Traffic Info Panel - Interactive road information display
 * Shows road details, traffic metrics, forecasts, and PCI data
 */

class TrafficInfoPanel {
  constructor() {
    this.panelElement = null;
    this.isVisible = false;
    this.currentRoad = null;
    this.createPanel();
    console.log("📊 TrafficInfoPanel initialized");
  }

  // Create the info panel HTML structure
  createPanel() {
    const panel = document.createElement("div");
    panel.id = "traffic-info-panel";
    panel.className = "traffic-info-panel";
    panel.innerHTML = `
            <div class="panel-header">
                <h3 id="panel-title">Road Information</h3>
                <button id="panel-close" class="close-btn">&times;</button>
            </div>
            <div class="panel-content">
                <div class="road-info">
                    <div class="info-row">
                        <span class="label">Type:</span>
                        <span id="road-type" class="value">-</span>
                    </div>
                    <div class="info-row">
                        <span class="label">Length:</span>
                        <span id="road-length" class="value">-</span>
                    </div>
                </div>

                <div class="traffic-section">
                    <h4>🚦 Current Traffic</h4>
                    <div class="traffic-level">
                        <span id="traffic-level" class="level-badge">-</span>
                        <span id="current-volume" class="volume">- veh/hr</span>
                    </div>
                </div>

                <div class="forecast-section">
                    <h4>📈 Traffic Forecast</h4>
                    <div class="forecast-grid">
                        <div class="forecast-item">
                            <span class="forecast-time">1 Hour</span>
                            <span id="forecast-1h" class="forecast-value">-</span>
                        </div>
                        <div class="forecast-item">
                            <span class="forecast-time">4 Hours</span>
                            <span id="forecast-4h" class="forecast-value">-</span>
                        </div>
                        <div class="forecast-item">
                            <span class="forecast-time">24 Hours</span>
                            <span id="forecast-24h" class="forecast-value">-</span>
                        </div>
                    </div>
                    <div class="forecast-chart" id="forecast-chart">
                        <canvas id="forecast-canvas" width="280" height="80"></canvas>
                    </div>
                </div>

                <div class="pci-section">
                    <h4>🛣️ Pavement Condition</h4>
                    <div class="pci-info">
                        <div class="pci-score">
                            <span id="pci-value" class="pci-number">-</span>
                            <span id="pci-condition" class="pci-label">Unknown</span>
                        </div>
                        <div class="pci-details">
                            <div class="detail-row">
                                <span class="label">Surface:</span>
                                <span id="pci-surface" class="value">-</span>
                            </div>
                            <div class="detail-row">
                                <span class="label">Last Inspection:</span>
                                <span id="pci-inspection" class="value">-</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="sensors-section">
                    <h4>📡 Traffic Sensors</h4>
                    <div class="sensor-info">
                        <span id="sensor-count" class="sensor-count">0</span>
                        <span class="sensor-label">signals on this road</span>
                    </div>
                </div>
            </div>
        `;

    // Add CSS styles
    const style = document.createElement("style");
    style.textContent = `
            .traffic-info-panel {
                position: absolute;
                top: 20px;
                right: 20px;
                width: 320px;
                background: rgba(20, 20, 20, 0.95);
                color: white;
                border-radius: 12px;
                box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                z-index: 1001;
                transform: translateX(100%);
                transition: transform 0.3s ease-in-out;
                backdrop-filter: blur(10px);
                border: 1px solid rgba(255, 255, 255, 0.1);
            }

            .traffic-info-panel.visible {
                transform: translateX(0);
            }

            .panel-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 16px 20px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.1);
            }

            .panel-header h3 {
                margin: 0;
                color: #00d4ff;
                font-size: 18px;
                font-weight: 600;
            }

            .close-btn {
                background: none;
                border: none;
                color: #aaa;
                font-size: 24px;
                cursor: pointer;
                padding: 0;
                width: 30px;
                height: 30px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: 50%;
                transition: all 0.2s;
            }

            .close-btn:hover {
                background: rgba(255, 255, 255, 0.1);
                color: white;
            }

            .panel-content {
                padding: 20px;
                max-height: 600px;
                overflow-y: auto;
            }

            .panel-content h4 {
                margin: 20px 0 12px 0;
                font-size: 14px;
                color: #00d4ff;
                font-weight: 600;
            }

            .panel-content h4:first-child {
                margin-top: 0;
            }

            .info-row, .detail-row {
                display: flex;
                justify-content: space-between;
                margin: 8px 0;
                font-size: 13px;
            }

            .label {
                color: #aaa;
            }

            .value {
                color: white;
                font-weight: 500;
            }

            .traffic-level {
                display: flex;
                align-items: center;
                gap: 12px;
                margin: 12px 0;
            }

            .level-badge {
                padding: 4px 12px;
                border-radius: 20px;
                font-size: 12px;
                font-weight: 600;
                text-transform: uppercase;
            }

            .level-badge.heavy { background: #ff4444; }
            .level-badge.moderate { background: #ff8c00; }
            .level-badge.light { background: #ffd700; color: #000; }
            .level-badge.minimal { background: #32cd32; color: #000; }

            .volume {
                color: white;
                font-weight: 600;
            }

            .forecast-grid {
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 12px;
                margin: 12px 0;
            }

            .forecast-item {
                text-align: center;
                padding: 8px;
                background: rgba(255, 255, 255, 0.05);
                border-radius: 8px;
                border: 1px solid rgba(255, 255, 255, 0.1);
            }

            .forecast-time {
                display: block;
                font-size: 11px;
                color: #aaa;
                margin-bottom: 4px;
            }

            .forecast-value {
                display: block;
                font-size: 14px;
                font-weight: 600;
                color: white;
            }

            .forecast-chart {
                margin-top: 16px;
                text-align: center;
            }

            .forecast-canvas {
                border-radius: 4px;
                background: rgba(255, 255, 255, 0.02);
            }

            .pci-info {
                display: flex;
                align-items: center;
                gap: 16px;
                margin: 12px 0;
            }

            .pci-score {
                text-align: center;
                min-width: 80px;
            }

            .pci-number {
                display: block;
                font-size: 32px;
                font-weight: 700;
                line-height: 1;
            }

            .pci-number.excellent { color: #00ff00; }
            .pci-number.good { color: #90ee90; }
            .pci-number.fair { color: #ffd700; }
            .pci-number.poor { color: #ff4444; }
            .pci-number.unknown { color: #888; }

            .pci-label {
                display: block;
                font-size: 12px;
                color: #aaa;
                margin-top: 4px;
                text-transform: uppercase;
            }

            .pci-details {
                flex: 1;
            }

            .sensor-info {
                display: flex;
                align-items: center;
                gap: 8px;
                margin: 12px 0;
            }

            .sensor-count {
                font-size: 24px;
                font-weight: 700;
                color: #7CFC00;
            }

            .sensor-label {
                color: #aaa;
                font-size: 13px;
            }

            /* Scrollbar styling */
            .panel-content::-webkit-scrollbar {
                width: 4px;
            }

            .panel-content::-webkit-scrollbar-track {
                background: rgba(255, 255, 255, 0.1);
                border-radius: 2px;
            }

            .panel-content::-webkit-scrollbar-thumb {
                background: rgba(0, 212, 255, 0.5);
                border-radius: 2px;
            }
        `;

    document.head.appendChild(style);
    document.body.appendChild(panel);
    this.panelElement = panel;

    // Setup event handlers
    this.setupEventHandlers();
  }

  // Setup event handlers
  setupEventHandlers() {
    const closeBtn = document.getElementById("panel-close");
    closeBtn.addEventListener("click", () => this.hide());

    // Close on escape key
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && this.isVisible) {
        this.hide();
      }
    });
  }

  // Show panel with road data
  show(road, trafficData, signalCount = 0) {
    this.currentRoad = road;
    this.updateContent(road, trafficData, signalCount);

    this.panelElement.classList.add("visible");
    this.isVisible = true;

    console.log("📊 Showing traffic info for:", road.name);
  }

  // Hide panel
  hide() {
    this.panelElement.classList.remove("visible");
    this.isVisible = false;
    this.currentRoad = null;

    console.log("📊 Traffic info panel hidden");
  }

  // Update panel content
  updateContent(road, trafficData, signalCount = 0) {
    // Update header
    document.getElementById("panel-title").textContent = road.name;

    // Update road info
    document.getElementById("road-type").textContent = this.formatRoadType(
      road.kind
    );
    document.getElementById("road-length").textContent = `${Math.round(
      road.length
    )}m`;

    // Update traffic info
    if (trafficData) {
      const levelElement = document.getElementById("traffic-level");
      levelElement.textContent = trafficData.level;
      levelElement.className = `level-badge ${trafficData.level.toLowerCase()}`;

      document.getElementById(
        "current-volume"
      ).textContent = `${trafficData.currentVolume} veh/hr`;
      document.getElementById(
        "forecast-1h"
      ).textContent = `${trafficData.forecast1h}`;
      document.getElementById(
        "forecast-4h"
      ).textContent = `${trafficData.forecast4h}`;
      document.getElementById(
        "forecast-24h"
      ).textContent = `${trafficData.forecast24h}`;

      // Draw forecast chart
      this.drawForecastChart([
        trafficData.currentVolume,
        trafficData.forecast1h,
        trafficData.forecast4h,
        trafficData.forecast24h,
      ]);
    } else {
      // No traffic data available
      document.getElementById("traffic-level").textContent = "-";
      document.getElementById("current-volume").textContent = "- veh/hr";
      document.getElementById("forecast-1h").textContent = "-";
      document.getElementById("forecast-4h").textContent = "-";
      document.getElementById("forecast-24h").textContent = "-";
    }

    // Update PCI info
    if (road.metadata && road.metadata.pci !== null) {
      const pciElement = document.getElementById("pci-value");
      pciElement.textContent = road.metadata.pci;
      pciElement.className = `pci-number ${road.metadata.pciCondition.toLowerCase()}`;

      document.getElementById("pci-condition").textContent =
        road.metadata.pciCondition;
      document.getElementById("pci-surface").textContent =
        road.metadata.pciSurface || "-";
      document.getElementById("pci-inspection").textContent =
        road.metadata.pciLastInspection || "Unknown";
    } else {
      document.getElementById("pci-value").textContent = "-";
      document.getElementById("pci-value").className = "pci-number unknown";
      document.getElementById("pci-condition").textContent = "Unknown";
      document.getElementById("pci-surface").textContent = "-";
      document.getElementById("pci-inspection").textContent = "-";
    }

    // Update sensor info
    document.getElementById("sensor-count").textContent = signalCount;
  }

  // Format road type for display
  formatRoadType(roadKind) {
    const types = {
      trunk: "Major Highway",
      primary: "Primary Road",
      secondary: "Secondary Road",
      tertiary: "Tertiary Road",
      residential: "Residential Street",
      service: "Service Road",
      unclassified: "Local Road",
    };
    return (
      types[roadKind] || roadKind.charAt(0).toUpperCase() + roadKind.slice(1)
    );
  }

  // Draw simple forecast sparkline chart
  drawForecastChart(data) {
    const canvas = document.getElementById("forecast-canvas");
    const ctx = canvas.getContext("2d");

    // Clear canvas
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    if (!data || data.length === 0) return;

    const width = canvas.width;
    const height = canvas.height;
    const padding = 10;
    const chartWidth = width - 2 * padding;
    const chartHeight = height - 2 * padding;

    // Find data range
    const maxVal = Math.max(...data);
    const minVal = Math.min(...data);
    const range = maxVal - minVal || 1;

    // Draw grid lines
    ctx.strokeStyle = "rgba(255, 255, 255, 0.1)";
    ctx.lineWidth = 1;

    // Horizontal lines
    for (let i = 0; i <= 4; i++) {
      const y = padding + (i * chartHeight) / 4;
      ctx.beginPath();
      ctx.moveTo(padding, y);
      ctx.lineTo(width - padding, y);
      ctx.stroke();
    }

    // Draw data line
    ctx.strokeStyle = "#00d4ff";
    ctx.lineWidth = 2;
    ctx.beginPath();

    for (let i = 0; i < data.length; i++) {
      const x = padding + (i * chartWidth) / (data.length - 1);
      const y =
        padding + chartHeight - ((data[i] - minVal) / range) * chartHeight;

      if (i === 0) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
    }

    ctx.stroke();

    // Draw data points
    ctx.fillStyle = "#00d4ff";
    for (let i = 0; i < data.length; i++) {
      const x = padding + (i * chartWidth) / (data.length - 1);
      const y =
        padding + chartHeight - ((data[i] - minVal) / range) * chartHeight;

      ctx.beginPath();
      ctx.arc(x, y, 3, 0, 2 * Math.PI);
      ctx.fill();
    }
  }

  // Update with new traffic data (for live updates)
  updateTrafficData(trafficData) {
    if (!this.isVisible || !this.currentRoad) return;

    const signalCount =
      parseInt(document.getElementById("sensor-count").textContent) || 0;
    this.updateContent(this.currentRoad, trafficData, signalCount);
  }

  // Check if panel is currently visible
  isShowing() {
    return this.isVisible;
  }

  // Get current road
  getCurrentRoad() {
    return this.currentRoad;
  }
}

// Global traffic info panel instance
const trafficInfoPanel = new TrafficInfoPanel();
