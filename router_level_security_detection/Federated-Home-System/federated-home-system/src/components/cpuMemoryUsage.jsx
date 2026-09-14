import React, { useState, useEffect } from 'react';

const CpuMemoryUsage = () => {
  const [cpuData, setCpuData] = useState({});
  const [memoryData, setMemoryData] = useState({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchCpuMemory = async () => {
      try {
        const response = await fetch('http://127.0.0.1:5000/api/cpu_memory'); // Flask API endpoint
        const data = await response.json();

        if (data.status === 'Success') {
          setCpuData(data.cpu);
          setMemoryData(data.memory);
        } else {
          console.error('Error fetching CPU and memory data:', data.error);
        }
      } catch (error) {
        console.error('Error:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchCpuMemory();
  }, []);

  return (
    <div className="mt-4">
      <h3>⚙️ CPU and Memory Usage</h3>
      <div className="card mt-4">
        <div className="card-body">
          {loading ? (
            <p>Loading CPU and memory data...</p>
          ) : (
            <>
              {/* CPU Usage Table */}
              <h5>CPU Usage</h5>
              <table className="table table-striped">
                <thead>
                  <tr>
                    <th>Type</th>
                    <th>Percentage</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(cpuData).map(([key, value], index) => (
                    <tr key={index}>
                      <td>{key}</td>
                      <td>{value}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {/* Memory Usage Table */}
              <h5>Memory Usage</h5>
              <table className="table table-striped">
                <thead>
                  <tr>
                    <th>Type</th>
                    <th>Value</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(memoryData).map(([key, value], index) => (
                    <tr key={index}>
                      <td>{key}</td>
                      <td>{parseInt(value).toLocaleString()} KB</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default CpuMemoryUsage;
