import React, { useState, useEffect } from 'react';

const DeviceList = () => {
  const [devices, setDevices] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchDevices = async () => {
      try {
        const response = await fetch('http://127.0.0.1:5000/api/devices'); // Flask API endpoint
        const data = await response.json();
        if (data.status === 'Success') {
          setDevices(data.devices);
        } else {
          console.error('Error fetching devices:', data.error);
        }
      } catch (error) {
        console.error('Error:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchDevices();
  }, []);

  if (loading) {
    return <p>Loading devices...</p>;
  }

  return (
    <div>
      <table className="table table-striped">
        <thead>
          <tr>
            <th>Lease Time</th>
            <th>MAC Address</th>
            <th>IP Address</th>
            <th>Hostname</th>
          </tr>
        </thead>
        <tbody>
          {devices.map((device, index) => (
            <tr key={index}>
              <td>{device.lease_time}</td>
              <td>{device.mac_address}</td>
              <td>{device.ip_address}</td>
              <td>{device.hostname}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default DeviceList;
