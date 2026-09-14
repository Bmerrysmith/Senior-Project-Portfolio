import React, { useState, useEffect } from 'react';

const ConsoleOutput = () => {
  const [logs, setLogs] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchLogs = async () => {
      try {
        const response = await fetch('http://127.0.0.1:5000/api/logs'); // Flask API endpoint
        const data = await response.json();
        if (data.status === 'Success') {
          setLogs(data.logs); // Set the logs received from the API
        } else {
          console.error('Error fetching logs:', data.error);
          setLogs('Error fetching logs. Please try again later.');
        }
      } catch (error) {
        console.error('Error:', error);
        setLogs('Failed to fetch logs. Please check your connection.');
      } finally {
        setLoading(false);
      }
    };

    fetchLogs();
  }, []);

  if (loading) {
    return <p>Loading logs...</p>;
  }

  return (
    <div className="card mb-4" style={{ maxHeight: '300px', overflowY: 'auto' }}>
      <div
        style={{
          backgroundColor: '#f8f9fa',
          border: '1px solid #dee2e6',
          padding: '10px',
          fontFamily: 'monospace',
          whiteSpace: 'pre-wrap',
          height: '100%',
        }}
      >
        {logs}
      </div>
    </div>
  );
};

export default ConsoleOutput;
