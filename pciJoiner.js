/**
 * PCI Data Joining - Pavement Condition Index integration
 * Spatially joins pavement condition data to road segments
 */

// Mock PCI dataset for FGCU area
const FGCU_PCI_DATA = [
    {
        id: 'pci_001',
        location: [-81.773, 26.463], // Ben Hill Griffin Parkway
        pci: 85,
        condition: 'Good',
        lastInspection: '2024-10-15',
        surface: 'Asphalt'
    },
    {
        id: 'pci_002', 
        location: [-81.773, 26.465], // FGCU Boulevard
        pci: 72,
        condition: 'Fair',
        lastInspection: '2024-09-20',
        surface: 'Concrete'
    },
    {
        id: 'pci_003',
        location: [-81.775, 26.464], // Campus Loop
        pci: 91,
        condition: 'Excellent', 
        lastInspection: '2024-11-01',
        surface: 'Asphalt'
    },
    {
        id: 'pci_004',
        location: [-81.771, 26.463], // Parking Access
        pci: 58,
        condition: 'Poor',
        lastInspection: '2024-08-10',
        surface: 'Asphalt'
    },
    {
        id: 'pci_005',
        location: [-81.772, 26.465], // Library Drive
        pci: 79,
        condition: 'Good',
        lastInspection: '2024-10-05',
        surface: 'Concrete'
    },
    {
        id: 'pci_006',
        location: [-81.774, 26.462], // South Campus Road
        pci: 67,
        condition: 'Fair',
        lastInspection: '2024-09-15',
        surface: 'Asphalt'
    }
];

class PCIJoiner {
    constructor() {
        this.pciData = FGCU_PCI_DATA;
        console.log('🛣️ PCIJoiner initialized with', this.pciData.length, 'PCI records');
    }

    // Calculate distance between two points in meters
    calculateDistance(lon1, lat1, lon2, lat2) {
        const R = 6371000; // Earth radius in meters
        const dLat = (lat2 - lat1) * Math.PI / 180;
        const dLon = (lon2 - lon1) * Math.PI / 180;
        const a = 
            Math.sin(dLat/2) * Math.sin(dLat/2) +
            Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
            Math.sin(dLon/2) * Math.sin(dLon/2);
        const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
        return R * c;
    }

    // Find nearest PCI record to a point
    findNearestPCI(lon, lat, maxDistanceMeters = 20) {
        let nearestPCI = null;
        let nearestDistance = maxDistanceMeters;

        for (const pci of this.pciData) {
            const distance = this.calculateDistance(
                lon, lat,
                pci.location[0], pci.location[1]
            );

            if (distance < nearestDistance) {
                nearestDistance = distance;
                nearestPCI = {
                    ...pci,
                    distance: Math.round(distance)
                };
            }
        }

        return nearestPCI;
    }

    // Join PCI data to road segments
    joinToRoads(roads) {
        console.log('🔗 Joining PCI data to roads...');
        
        let joinCount = 0;
        
        for (const road of roads) {
            // Use road midpoint for PCI matching
            const [lon, lat] = road.midpoint;
            const nearestPCI = this.findNearestPCI(lon, lat, 50); // 50m search radius

            if (nearestPCI) {
                road.metadata = road.metadata || {};
                road.metadata.pci = nearestPCI.pci;
                road.metadata.pciCondition = nearestPCI.condition;
                road.metadata.pciLastInspection = nearestPCI.lastInspection;
                road.metadata.pciSurface = nearestPCI.surface;
                road.metadata.pciDistance = nearestPCI.distance;
                
                joinCount++;
                console.log(`✅ Joined PCI ${nearestPCI.pci} to ${road.name} (${nearestPCI.distance}m away)`);
            } else {
                // Mark as unknown if no PCI data nearby
                road.metadata = road.metadata || {};
                road.metadata.pci = null;
                road.metadata.pciCondition = 'Unknown';
                console.log(`❓ No PCI data for ${road.name}`);
            }
        }

        console.log(`🔗 PCI join complete: ${joinCount}/${roads.length} roads matched`);
        return joinCount;
    }

    // Get PCI condition category
    static getPCICategory(pci) {
        if (pci === null || pci === undefined) return 'Unknown';
        if (pci >= 80) return 'Excellent';
        if (pci >= 70) return 'Good';
        if (pci >= 60) return 'Fair';
        return 'Poor';
    }

    // Get PCI color for visualization
    static getPCIColor(pci) {
        if (pci === null || pci === undefined) return '#888888'; // Gray
        if (pci >= 80) return '#00ff00'; // Green
        if (pci >= 70) return '#90ee90'; // Light Green
        if (pci >= 60) return '#ffd700'; // Yellow
        return '#ff4444'; // Red
    }

    // Generate synthetic PCI data for additional roads
    generateSyntheticPCI(road) {
        // Generate realistic PCI based on road type and location
        let basePCI = 75; // Default fair condition
        
        // Adjust based on road type
        if (road.kind === 'trunk' || road.kind === 'primary') {
            basePCI = 80; // Major roads better maintained
        } else if (road.kind === 'residential' || road.kind === 'service') {
            basePCI = 65; // Local roads may be lower
        }
        
        // Add some randomness
        const variation = (Math.random() - 0.5) * 20; // ±10 points
        const finalPCI = Math.max(40, Math.min(95, basePCI + variation));
        
        return {
            pci: Math.round(finalPCI),
            condition: PCIJoiner.getPCICategory(finalPCI),
            lastInspection: this.getRandomInspectionDate(),
            surface: Math.random() > 0.3 ? 'Asphalt' : 'Concrete',
            synthetic: true
        };
    }

    // Generate random inspection date within last year
    getRandomInspectionDate() {
        const now = new Date();
        const oneYearAgo = new Date(now.getTime() - 365 * 24 * 60 * 60 * 1000);
        const randomTime = oneYearAgo.getTime() + Math.random() * (now.getTime() - oneYearAgo.getTime());
        return new Date(randomTime).toISOString().split('T')[0];
    }

    // Ensure all roads have PCI data (generate synthetic if needed)
    ensureAllRoadsHavePCI(roads) {
        console.log('🔄 Ensuring all roads have PCI data...');
        
        let syntheticCount = 0;
        
        for (const road of roads) {
            if (!road.metadata || road.metadata.pci === null) {
                const syntheticPCI = this.generateSyntheticPCI(road);
                
                road.metadata = road.metadata || {};
                road.metadata.pci = syntheticPCI.pci;
                road.metadata.pciCondition = syntheticPCI.condition;
                road.metadata.pciLastInspection = syntheticPCI.lastInspection;
                road.metadata.pciSurface = syntheticPCI.surface;
                road.metadata.pciSynthetic = true;
                
                syntheticCount++;
            }
        }

        console.log(`🔄 Generated synthetic PCI for ${syntheticCount} roads`);
        return syntheticCount;
    }

    // Get statistics
    getStats() {
        const totalRecords = this.pciData.length;
        const conditions = this.pciData.reduce((acc, pci) => {
            acc[pci.condition] = (acc[pci.condition] || 0) + 1;
            return acc;
        }, {});
        
        const avgPCI = this.pciData.reduce((sum, pci) => sum + pci.pci, 0) / totalRecords;
        
        return {
            totalRecords,
            averagePCI: Math.round(avgPCI),
            conditions
        };
    }
}

// Global PCI joiner instance
const pciJoiner = new PCIJoiner();