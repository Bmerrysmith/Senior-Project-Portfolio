import React, { useState, useEffect } from 'react';

const BandwidthUsage = () => {
  const [bandwidthData, setBandwidthData] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchBandwidth = async () => {
      try {
        const response = await fetch('http://127.0.0.1:5000/api/bandwidth'); // Flask API endpoint
        const data = await response.json();
        if (data.status === 'Success') {
          setBandwidthData(data.bandwidth);
        } else {
          console.error('Error fetching bandwidth data:', data.error);
        }
      } catch (error) {
        console.error('Error:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchBandwidth();
  }, []);

  return (
    <div className="mt-4">
      <div className="card mt-4">
        <div className="card-body">
          <h3>📡 Bandwidth Usage</h3>
          {loading ? (
              <p>Loading bandwidth data...</p>
          ) : (
              <div>
                <table className="table table-striped">
                  <thead>
                  <tr>
                    <th>Interface</th>
                    <th>Received Data (Bytes)</th>
                    <th>Transmitted Data (Bytes)</th>
                  </tr>
                  </thead>
                  <tbody>
                  {bandwidthData.map((data, index) => (
                      <tr key={index}>
                        <td>{data.interface}</td>
                        <td>{data.receive_bytes.toLocaleString()}</td>
                        <td>{data.transmit_bytes.toLocaleString()}</td>
                      </tr>
                  ))}
                  </tbody>
                </table>
              </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default BandwidthUsage;
