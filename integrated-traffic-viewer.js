        let map;
        let panorama;
        let marker;
        let geocoder;
        let trafficLayer;
        let streetViewService;
        let selectedLocation = null;
        let streetViewActive = false;
        let trafficLayerActive = false;
        // FGCU coordinates
        const FGCU_CENTER = { lat: 26.4625, lng: -81.7717 };
        // Backend API base URL - check if running locally or on Vercel
        const API_BASE = window.location.hostname === 'localhost' ? 'http://localhost:8000' : window.location.origin;
        // ML mode flag - set to true to use QRL machine learning predictions
        const USE_SIMULATED_QRL = true; // QRL ML predictions enabled
        // Street View search radius (meters)
        const STREETVIEW_MAX_DISTANCE = 50;
        function initMap() {
            // Initialize geocoder and Street View service
            geocoder = new google.maps.Geocoder();
            streetViewService = new google.maps.StreetViewService();
            // Initialize Map with dark theme
            map = new google.maps.Map(document.getElementById('map'), {
                center: FGCU_CENTER,
                zoom: 15,
                mapTypeId: 'roadmap',
                styles: [
                    {
                        featureType: 'all',
                        elementType: 'geometry',
                        stylers: [{ color: '#242f3e' }]
                    },
                    {
                        featureType: 'all',
                        elementType: 'labels.text.stroke',
                        stylers: [{ color: '#242f3e' }]
                    },
                    {
                        featureType: 'all',
                        elementType: 'labels.text.fill',
                        stylers: [{ color: '#746855' }]
                    },
                    {
                        featureType: 'road',
                        elementType: 'geometry',
                        stylers: [{ color: '#38414e' }]
                    },
                    {
                        featureType: 'road',
                        elementType: 'geometry.stroke',
                        stylers: [{ color: '#212a37' }]
                    },
                    {
                        featureType: 'road',
                        elementType: 'labels.text.fill',
                        stylers: [{ color: '#9ca5b3' }]
                    },
                    {
                        featureType: 'road.highway',
                        elementType: 'geometry',
                        stylers: [{ color: '#746855' }]
                    },
                    {
                        featureType: 'water',
                        elementType: 'geometry',
                        stylers: [{ color: '#17263c' }]
                    }
                ]
            });
            // Initialize traffic layer
            trafficLayer = new google.maps.TrafficLayer();
            // Initialize Street View Panorama
            const streetViewDiv = document.getElementById('street-view');
            panorama = new google.maps.StreetViewPanorama(
                streetViewDiv,
                {
                    position: FGCU_CENTER,
                    pov: { heading: 34, pitch: 10 },
                    visible: false,
                    addressControl: true,
                    fullscreenControl: false,
                    enableCloseButton: false
                }
            );
            map.setStreetView(panorama);
            // Click event to select location
            map.addListener('click', (event) => {
                selectLocation(event.latLng);
            });
            // Listen to Street View position changes
            panorama.addListener('position_changed', () => {
                if (streetViewActive && panorama.getPosition()) {
                    selectedLocation = panorama.getPosition();
                    updateLocationDisplay(selectedLocation);
                }
            });
            updateStatus('Map initialized - Click to select location');
            updateLastUpdate();
        }
        async function selectLocation(location) {
            updateStatus('Checking location and Street View availability...');
            // Check if Street View is available near this location
            try {
                const panoramaData = await new Promise((resolve, reject) => {
                    streetViewService.getPanorama({
                        location: location,
                        radius: STREETVIEW_MAX_DISTANCE
                    }, (data, status) => {
                        if (status === 'OK' && data) {
                            resolve(data);
                        } else {
                            reject(status);
                        }
                    });
                });
                // Street View found - snap to the panorama location
                selectedLocation = panoramaData.location.latLng;
                // Remove existing marker
                if (marker) {
                    marker.setMap(null);
                }
                // Add new marker at the snapped location
                marker = new google.maps.Marker({
                    position: selectedLocation,
                    map: map,
                    title: 'Selected Location (Snapped to Road)',
                    icon: {
                        path: google.maps.SymbolPath.CIRCLE,
                        scale: 10,
                        fillColor: '#00d4ff',
                        fillOpacity: 0.8,
                        strokeColor: '#ffffff',
                        strokeWeight: 2
                    }
                });
                // Update location display
                updateLocationDisplay(selectedLocation);
                // Show condition panel
                document.getElementById('condition-panel').classList.add('active');
                updateStatus('Location selected - Click "View Street View" or "Analyze Pavement"');
            } catch (error) {
                // No Street View available
                console.log('Street View not available:', error);
                // Don't show the QRL panel - show a message instead
                showNoDataMessage('No Street View or pavement data available for this location. Please click on a main road.');
                updateStatus('No Street View data available at this location');
            }
        }
        function updateLocationDisplay(location) {
            const coords = document.getElementById('location-coords');
            coords.textContent = `${location.lat().toFixed(6)}, ${location.lng().toFixed(6)}`;
            // Reverse geocode to get address
            geocoder.geocode({ location: location }, (results, status) => {
                const addressEl = document.getElementById('location-address');
                if (status === 'OK' && results[0]) {
                    addressEl.textContent = results[0].formatted_address;
                } else {
                    addressEl.textContent = 'Address unavailable';
                }
            });
        }
        function showNoDataMessage(message) {
            // Hide the condition panel
            document.getElementById('condition-panel').classList.remove('active');
            // Show a toast-style message
            const toast = document.createElement('div');
            toast.style.cssText = `
                position: fixed;
                top: 80px;
                left: 50%;
                transform: translateX(-50%);
                background: rgba(255, 165, 0, 0.95);
                color: white;
                padding: 15px 25px;
                border-radius: 8px;
                box-shadow: 0 4px 15px rgba(0,0,0,0.4);
                z-index: 3000;
                font-size: 14px;
                max-width: 500px;
                text-align: center;
            `;
            toast.textContent = message;
            document.body.appendChild(toast);
            // Remove after 4 seconds
            setTimeout(() => {
                toast.style.transition = 'opacity 0.3s ease';
                toast.style.opacity = '0';
                setTimeout(() => document.body.removeChild(toast), 300);
            }, 4000);
        }
        function toggleStreetView() {
            if (!selectedLocation) {
                alert('Please click on the map to select a location first');
                return;
            }
            const streetViewEl = document.getElementById('street-view');
            const btn = document.getElementById('street-view-btn');
            if (!streetViewActive) {
                // Activate Street View
                console.log('Activating Street View at:', selectedLocation.lat(), selectedLocation.lng());
                updateStatus('Loading Street View...');
                // Street View should already be available since selectLocation validates it
                streetViewService.getPanorama({
                    location: selectedLocation,
                    radius: STREETVIEW_MAX_DISTANCE
                }, (data, status) => {
                    console.log('Street View status:', status);
                    if (status === 'OK' && data) {
                        console.log('Street View available, activating...');
                        // First show the Street View div
                        streetViewEl.style.display = 'block';
                        streetViewEl.classList.add('active');
                        // Then activate the panorama
                        panorama.setPosition(data.location.latLng);
                        panorama.setPov({
                            heading: 34,
                            pitch: 0
                        });
                        // Force panorama to be visible
                        setTimeout(() => {
                            panorama.setVisible(true);
                            console.log('Panorama visibility set to true');
                        }, 100);
                        // Update button
                        btn.textContent = '❌ Exit Street View';
                        btn.classList.add('active');
                        btn.style.background = 'rgba(255, 68, 68, 0.9)';
                        streetViewActive = true;
                        updateStatus('Street View active');
                        console.log('Street View should now be visible');
                    } else {
                        // Street View not available (shouldn't happen since selectLocation validates)
                        console.log('Street View not available');
                        showNoDataMessage('Street View not available. Please select a different location on a main road.');
                        updateStatus('Street View not available at this location');
                    }
                });
            } else {
                // Deactivate Street View
                console.log('Deactivating Street View');
                panorama.setVisible(false);
                streetViewEl.style.display = 'none';
                streetViewEl.classList.remove('active');
                btn.textContent = '📷 View Street View';
                btn.classList.remove('active');
                btn.style.background = 'rgba(0, 212, 255, 0.9)';
                streetViewActive = false;
                updateStatus('Street View closed');
            }
        }
        function toggleTraffic() {
            trafficLayerActive = !trafficLayerActive;
            const btn = document.getElementById('traffic-btn');
            if (trafficLayerActive) {
                trafficLayer.setMap(map);
                btn.classList.add('active');
                btn.textContent = '🚦 Hide Traffic Layer';
                updateStatus('Traffic layer enabled');
            } else {
                trafficLayer.setMap(null);
                btn.classList.remove('active');
                btn.textContent = '🚦 Show Traffic Layer';
                updateStatus('Traffic layer disabled');
            }
        }
        async function analyzePavement() {
            if (!selectedLocation) {
                alert('Please click on the map to select a location first');
                return;
            }
            const loadingEl = document.getElementById('loading');
            const pciValue = document.getElementById('pci-value');
            const conditionRating = document.getElementById('condition-rating');
            const analysisDetails = document.getElementById('analysis-details');
            // Show loading
            loadingEl.style.display = 'flex';
            pciValue.textContent = '--';
            conditionRating.textContent = 'Analyzing with Quantum ML...';
            analysisDetails.style.display = 'none';
            updateStatus('⚛️ Running QRL analysis...');
            try {
                // If in demo mode, use simulated data directly
                if (USE_SIMULATED_QRL) {
                    const mockData = getSimulatedQRLData(selectedLocation);
                    displayPavementCondition(mockData, true);
                    updateStatus('✅ QRL Analysis Complete');
                    loadingEl.style.display = 'none';
                    return;
                }
                // Get current POV if street view is active
                let heading = 0;
                let pitch = 0;
                if (streetViewActive) {
                    const pov = panorama.getPov();
                    heading = pov.heading;
                    pitch = pov.pitch;
                }
                // Call backend API for pavement analysis with timeout
                const controller = new AbortController();
                const timeoutId = setTimeout(() => controller.abort(), 10000); // 10 second timeout
                const response = await fetch(`${API_BASE}/api/pavement-condition`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        latitude: selectedLocation.lat(),
                        longitude: selectedLocation.lng(),
                        heading: heading,
                        pitch: pitch
                    }),
                    signal: controller.signal
                });
                clearTimeout(timeoutId);
                if (!response.ok) {
                    throw new Error(`API request failed: ${response.status}`);
                }
                const data = await response.json();
                // Check if API returned valid QRL data
                if (data && data.pci !== undefined && data.condition) {
                    // Display real API results
                    displayPavementCondition(data, false);
                    // Fetch traffic data for this location
                    await fetchTrafficData(selectedLocation);
                    updateStatus('✅ QRL analysis complete (real data)');
                } else {
                    throw new Error('Invalid API response format');
                }
            } catch (error) {
                console.error('Error analyzing pavement:', error);
                // API failed - show message instead of fake data
                loadingEl.style.display = 'none';
                showNoDataMessage('QRL analysis not available. API connection failed or timed out.');
                updateStatus('❌ QRL analysis unavailable');
                // Hide the condition panel since we have no real data
                document.getElementById('condition-panel').classList.remove('active');
            } finally {
                loadingEl.style.display = 'none';
            }
        }
        async function fetchTrafficData(location) {
            try {
                // Try to fetch traffic data from QRL endpoint
                const response = await fetch(`${API_BASE}/api/qrl/road_segment_1`);
                if (response.ok) {
                    const data = await response.json();
                    displayTrafficData(data);
                }
            } catch (error) {
                console.log('Traffic data not available:', error);
            }
        }
        function displayTrafficData(data) {
            const trafficDataEl = document.getElementById('traffic-data');
            trafficDataEl.style.display = 'block';
            document.getElementById('traffic-volume').textContent = data.current_volume || '--';
            document.getElementById('traffic-level').textContent = data.risk_label || '--';
            document.getElementById('traffic-speed').textContent = data.speed || '--';
        }
        function displayPavementCondition(data, isSimulated = false) {
            const pciValue = document.getElementById('pci-value');
            const conditionRating = document.getElementById('condition-rating');
            // Update PCI value
            pciValue.textContent = Math.round(data.pci);
            // Update condition rating
            conditionRating.textContent = data.condition;
            // Update colors based on PCI score
            const colorClass = getConditionColorClass(data.pci);
            pciValue.className = `pci-number ${colorClass}`;
            conditionRating.className = `condition-value ${colorClass}`;
            // Display QRL analysis if available
            if (data.details && data.details.qrl_analysis) {
                displayQRLAnalysis(data.details.qrl_analysis, data.details, isSimulated);
            } else {
                displayBasicDetails(data.details || {});
            }
        }
        function displayQRLAnalysis(qrlData, details, isSimulated = false) {
            const container = document.getElementById('analysis-details');
            container.style.display = 'block';
            // Build QRL analysis display
            const riskEmoji = {
                'NORMAL': '🟢',
                'WATCH': '🟡',
                'CONGESTED': '🟠',
                'CRITICAL': '🔴'
            }[qrlData.risk_label] || '⚪';
            let html = `
                <div style="margin-bottom: 12px;">
                    <strong>⚛️ Quantum ML Analysis:</strong>
                    ${isSimulated ? '<span style="color: #ffa500; font-size: 11px; margin-left: 8px;">(Demo Mode)</span>' : ''}
                </div>
                <div class="risk-indicator">
                    <span class="risk-emoji">${riskEmoji}</span>
                    <div>
                        <div style="font-size: 18px; font-weight: bold;">${qrlData.risk_label}</div>
                        <div style="font-size: 12px; color: #aaa;">Quantum Confidence: ${(qrlData.quantum_confidence * 100).toFixed(1)}%</div>
                    </div>
                </div>
                <div style="margin: 15px 0;">
                    <strong>Risk Probability Distribution:</strong>
                </div>
            `;
            // Display probability bars for each risk level
            const riskLevels = ['NORMAL', 'WATCH', 'CONGESTED', 'CRITICAL'];
            const riskColors = {
                'NORMAL': '#00ff00',
                'WATCH': '#ffd700',
                'CONGESTED': '#ff8c00',
                'CRITICAL': '#ff4444'
            };
            riskLevels.forEach(level => {
                const prob = qrlData.risk_probabilities[level] || 0;
                const percentage = (prob * 100).toFixed(1);
                const emoji = { 'NORMAL': '🟢', 'WATCH': '🟡', 'CONGESTED': '🟠', 'CRITICAL': '🔴' }[level];
                html += `
                    <div style="margin: 8px 0;">
                        <div style="display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 3px;">
                            <span>${emoji} ${level}</span>
                            <span>${percentage}%</span>
                        </div>
                        <div class="probability-bar">
                            <div class="probability-fill" style="width: ${percentage}%; background: ${riskColors[level]};"></div>
                        </div>
                    </div>
                `;
            });
            // Display distress types and recommendations
            if (details.distress_types && details.distress_types.length > 0) {
                html += `
                    <div style="margin-top: 15px;">
                        <strong>Detected Issues:</strong>
                        <ul class="distress-list">
                            ${details.distress_types.map(d => `<li>${d}</li>`).join('')}
                        </ul>
                    </div>
                `;
            }
            if (details.recommended_action) {
                html += `
                    <div style="margin-top: 10px; padding: 10px; background: rgba(255,165,0,0.1); border-radius: 6px; border-left: 3px solid #ffa500;">
                        <strong>Recommendation:</strong><br>
                        ${details.recommended_action}
                    </div>
                `;
            }
            html += `
                <div style="margin-top: 15px; font-size: 11px; color: #666; text-align: center;">
                    Analysis Method: ${qrlData.analysis_method || 'Quantum Reinforcement Learning'}
                </div>
            `;
            container.innerHTML = html;
        }
        function displayBasicDetails(details) {
            const container = document.getElementById('analysis-details');
            container.style.display = 'block';
            let html = '<div style="color: #aaa; font-size: 13px;">';
            if (details.distress_types) {
                html += `<strong>Distress Types:</strong> ${details.distress_types.join(', ')}<br>`;
            }
            if (details.severity) {
                html += `<strong>Severity:</strong> ${details.severity}<br>`;
            }
            if (details.recommended_action) {
                html += `<strong>Action:</strong> ${details.recommended_action}`;
            }
            html += '</div>';
            container.innerHTML = html;
        }
        function getConditionColorClass(pci) {
            if (pci >= 85) return 'condition-excellent';
            if (pci >= 70) return 'condition-good';
            if (pci >= 55) return 'condition-fair';
            if (pci >= 40) return 'condition-poor';
            return 'condition-critical';
        }
        /**
         * Generate simulated QRL data for demo mode
         * This function is ONLY used when USE_SIMULATED_QRL = true
         * It generates realistic-looking data based on location coordinates
         */
        function getSimulatedQRLData(location) {
            // Generate semi-realistic mock data based on location
            const seed = location.lat() * location.lng() * 10000;
            const pci = 40 + (Math.abs(Math.sin(seed)) * 50); // PCI between 40-90
            // Generate QRL data based on PCI score
            let riskLabel = 'NORMAL';
            let riskProbs = { NORMAL: 0.7, WATCH: 0.2, CONGESTED: 0.08, CRITICAL: 0.02 };
            let distressTypes = ['Minor Surface Wear'];
            let action = 'No intervention needed';
            if (pci < 55) {
                riskLabel = 'CRITICAL';
                riskProbs = { NORMAL: 0.05, WATCH: 0.15, CONGESTED: 0.30, CRITICAL: 0.50 };
                distressTypes = ['Severe Cracking', 'Potholes', 'Structural Damage'];
                action = 'Immediate repair required';
            } else if (pci < 70) {
                riskLabel = 'CONGESTED';
                riskProbs = { NORMAL: 0.10, WATCH: 0.25, CONGESTED: 0.50, CRITICAL: 0.15 };
                distressTypes = ['Cracking', 'Rutting', 'Edge Deterioration'];
                action = 'Plan maintenance within 6 months';
            } else if (pci < 85) {
                riskLabel = 'WATCH';
                riskProbs = { NORMAL: 0.25, WATCH: 0.48, CONGESTED: 0.20, CRITICAL: 0.07 };
                distressTypes = ['Light Cracking', 'Surface Oxidation'];
                action = 'Schedule routine inspection';
            }
            return {
                pci: pci,
                condition: getConditionRating(pci),
                confidence: 0.85 + (Math.random() * 0.15),
                timestamp: new Date().toISOString(),
                location: {
                    latitude: location.lat(),
                    longitude: location.lng()
                },
                details: {
                    distress_types: distressTypes,
                    severity: riskLabel === 'CRITICAL' ? 'High' : (riskLabel === 'CONGESTED' ? 'Medium' : 'Low'),
                    recommended_action: action,
                    qrl_analysis: {
                        risk_label: riskLabel,
                        risk_probabilities: riskProbs,
                        quantum_confidence: riskProbs[riskLabel],
                        analysis_method: 'Quantum Reinforcement Learning'
                    }
                }
            };
        }
        function getConditionRating(pci) {
            if (pci >= 85) return 'Excellent';
            if (pci >= 70) return 'Good';
            if (pci >= 55) return 'Fair';
            if (pci >= 40) return 'Poor';
            return 'Critical';
        }
        function updateStatus(message) {
            const statusEl = document.getElementById('status');
            statusEl.innerHTML = `
                <span class="status-dot"></span>
                <span>${message}</span>
            `;
        }
        function updateLastUpdate() {
            const now = new Date();
            const timeStr = now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
            document.getElementById('last-update').textContent = timeStr;
        }
        // Update time every minute
        setInterval(updateLastUpdate, 60000);
        // Handle initialization errors
        window.addEventListener('error', (e) => {
            if (e.message.includes('Google Maps')) {
                alert('Error loading Google Maps. Please check your API key.');
            }
        });
