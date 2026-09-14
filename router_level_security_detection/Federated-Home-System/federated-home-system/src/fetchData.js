// Function to fetch data from the Flask API
async function fetchData() {
    try {
        const response = await fetch('http://127.0.0.1:5000/api/data');
        const data = await response.json();
        console.log('Received from Flask:', data);

        // Optionally, display the data in the DOM
        const output = document.getElementById('output');
        output.textContent = JSON.stringify(data, null, 2);
    } catch (error) {
        console.error('Error fetching data:', error);
    }
}

// Attach event listeners to buttons
document.getElementById('fetchButton').addEventListener('click', fetchData);
